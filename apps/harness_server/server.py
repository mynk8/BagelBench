# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Artemis harness server.

Backend for the research harness: runs, traces, eval scoring and the research UI.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import signal
import sys
from types import FrameType

# Bootstrap sys.path to allow running from any CWD
_current_p = Path(__file__).resolve().parent
while _current_p != _current_p.parent:
    if (_current_p / "pyproject.toml").exists() or (_current_p / "artemis").is_dir():
        _workspace_root = _current_p
        break
    _current_p = _current_p.parent
else:
    _workspace_root = Path(__file__).resolve().parent.parent.parent

_apps_dir = _workspace_root / "apps"
_harness_server_dir = _apps_dir / "harness_server"

for _p in (str(_workspace_root), str(_apps_dir), str(_harness_server_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from artemis.runtime import (
    DeviceExecutionLock,
    clear_server_info,
    device_pool,
    shutdown_awake_service,
    start_awake_service,
    write_server_info,
)

from artemis.config import init_ls_address

try:
    from harness_server.core.security import SameOriginBoundaryMiddleware
    from harness_server.core.state import state
    from harness_server.database.repositories.session_repository import session_repo
    from harness_server.routers import media, research, sessions, stream, system, tasks
    from harness_server.services.ipc_service import ipc_service
    from harness_server.services.task_queue_service import task_queue_service
except ImportError:
    from apps.harness_server.core.security import SameOriginBoundaryMiddleware
    from apps.harness_server.core.state import state
    from apps.harness_server.database.repositories.session_repository import session_repo
    from apps.harness_server.routers import media, research, sessions, stream, system, tasks
    from apps.harness_server.services.ipc_service import ipc_service
    from apps.harness_server.services.task_queue_service import task_queue_service

# Initialize language server synchronization address
init_ls_address()


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """Start server resources and release them on shutdown."""
    await on_startup()
    try:
        yield
    finally:
        await on_shutdown()


# Initialize FastAPI application
app = FastAPI(title="Artemis Harness", lifespan=_lifespan)
LIFECYCLE_TOKEN = os.environ.get("ARTEMIS_LIFECYCLE_TOKEN") or secrets.token_urlsafe(32)
app.state.lifecycle_token = LIFECYCLE_TOKEN

# The research UI is served same-origin from this process, so no CORS grants
# exist at all; the boundary middleware rejects cross-origin browser traffic
# and unrecognized Host headers (DNS rebinding) instead.
app.add_middleware(SameOriginBoundaryMiddleware)


async def on_startup():
    """Startup lifecycle hooks."""
    state.is_shutting_down = False
    state.shutdown_event.clear()
    write_server_info(
        port=getattr(state, "port", 8000),
        host=getattr(state, "host", "127.0.0.1"),
        lifecycle_token=LIFECYCLE_TOKEN,
    )
    await asyncio.to_thread(start_awake_service)
    cleaned_device_locks = DeviceExecutionLock.cleanup_stale_locks()
    if cleaned_device_locks:
        print(f"[ServerStartup] Removed {cleaned_device_locks} stale device lock(s).")

    # Warm the adb server and complete one enumeration before requests are
    # served, so submissions in the first seconds never race an adb cold start
    # and get a false "no devices attached" rejection.
    try:
        adb_warmed = await device_pool.warm_up_async()
    except Exception as exc:
        adb_warmed = False
        print(f"[ServerStartup] ADB warm-up failed: {exc}")
    if not adb_warmed:
        print(
            "[ServerStartup] ADB warm-up did not confirm a responding adb server; "
            "device enumeration will retry on demand."
        )
    asyncio.create_task(asyncio.to_thread(task_queue_service.archive_older_replays_on_launch))

    cleaned = session_repo.cleanup_orphans_on_startup()
    if cleaned > 0:
        print(f"[ServerStartup] Marked {cleaned} orphaned running session(s) as failed.")
    # Workers killed together with a previous daemon never remuxed their
    # recordings; publish whatever raw files they left behind.
    asyncio.create_task(asyncio.to_thread(task_queue_service.recover_orphaned_recordings_on_launch))

    await ipc_service.start_server()
    state.worker_task = asyncio.create_task(task_queue_service.queue_worker())


async def on_shutdown():
    """Stop task and IPC children before the UI server exits."""
    state.is_shutting_down = True
    state.shutdown_event.set()
    task_queue_service._broadcast_event("server_shutdown", {"status": "stopping"})
    owned_session_ids = {
        str(item["session_id"])
        for item in state.queue_items
        if isinstance(item, dict) and item.get("status") == "running" and item.get("session_id")
    }

    worker = state.worker_task
    if worker is not None and not worker.done():
        worker.cancel()
        try:
            await asyncio.wait_for(worker, timeout=5.0)
        except (asyncio.CancelledError, TimeoutError):
            pass
    state.worker_task = None

    # Cancel in-flight run coroutines and wait for their finalizers (DB status,
    # session_ended broadcast, trace sync, recording recovery) to run.
    run_tasks = [t for t in list(task_queue_service._run_tasks) if not t.done()]
    for run_task in run_tasks:
        run_task.cancel()
    if run_tasks:
        try:
            await asyncio.wait_for(asyncio.gather(*run_tasks, return_exceptions=True), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    for run in list(state.active_runs.values()):
        run_proc = run.get("process")
        if run_proc is not None and run_proc.returncode is None:
            await task_queue_service._terminate_worker_process(run_proc)
    state.active_runs.clear()
    if state.current_process is not None and state.current_process.returncode is None:
        await task_queue_service._terminate_worker_process(state.current_process)
    for item in state.queue_items:
        if isinstance(item, dict):
            DeviceExecutionLock.cancel_reservation(item.get("queue_ticket"))
    DeviceExecutionLock.cleanup_stale_locks()
    state.current_process = None
    state.queue_items.clear()
    for session_id in owned_session_ids:
        session_repo.update_session_status(session_id, "cancelled")

    await ipc_service.stop_server()
    state.ipc_subscribers.clear()
    await asyncio.to_thread(shutdown_awake_service)
    clear_server_info(
        port=getattr(state, "port", 8000),
        lifecycle_token=LIFECYCLE_TOKEN,
    )


# Mount modular routers
app.include_router(stream.router)
app.include_router(media.router)
app.include_router(research.router)
app.include_router(sessions.router)
app.include_router(tasks.router)
app.include_router(system.router)


# ------------------------------------------------------------------------------
# Research UI (React) single-port static hosting
# ------------------------------------------------------------------------------
_research_dist = _workspace_root / "apps" / "research_ui" / "dist"


def _resolve_static_file(root: Path, relative_path: str) -> Path | None:
    """Return the requested file only when it truly lives under ``root``."""
    try:
        root = root.resolve()
        target = (root / relative_path).resolve()
    except (OSError, ValueError):
        return None
    if target.is_file() and target.is_relative_to(root):
        return target
    return None


@app.get("/", include_in_schema=False)
async def serve_research_root():
    return await serve_research_spa("")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_research_spa(full_path: str):
    if (
        full_path.startswith(("api/", "images/", "videos/"))
        or full_path in ("docs", "openapi.json")
        or full_path.startswith("redoc")
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Endpoint not found")

    clean_path = full_path.strip("/")
    if clean_path:
        target_file = _resolve_static_file(_research_dist, clean_path)
        if target_file is not None:
            return FileResponse(target_file)

    index_file = _research_dist / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<p>The research UI is not built. Run <code>make build-ui</code>, "
        "or <code>make dev</code> and open http://127.0.0.1:5173.</p>"
    )


class ArtemisUvicornServer(uvicorn.Server):
    """Notify application streams before Uvicorn waits for them to close."""

    @staticmethod
    def _task_is_active() -> bool:
        """Check task state without doing process I/O from a signal handler."""
        proc = state.current_process
        if proc is not None and proc.returncode is None:
            return True
        return any(
            isinstance(item, dict) and item.get("status") == "running" for item in state.queue_items
        )

    @staticmethod
    def _schedule_signal_report(message: str) -> None:
        """Defer console output so a signal cannot re-enter Colorama writes."""
        try:
            asyncio.get_running_loop().call_soon(print, message)
        except RuntimeError:
            try:
                os.write(2, f"{message}\n".encode(errors="replace"))
            except OSError:
                pass

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        try:
            signal_name = signal.Signals(sig).name
        except ValueError:
            signal_name = "UNKNOWN"
        frame_location = "unknown"
        if frame is not None:
            frame_location = f"{frame.f_code.co_filename}:{frame.f_lineno}"
        signal_report = (
            f"[ServerSignal] Received {signal_name} ({sig}); "
            f"server PID={os.getpid()}, parent PID={os.getppid()}, frame={frame_location}"
        )
        self._schedule_signal_report(signal_report)

        if sys.platform == "win32" and sig == signal.SIGINT and self._task_is_active():
            self._schedule_signal_report(
                "[ServerSignal] Ignored Windows SIGINT while a mobile task is active. "
                "Stop the task first, or press Ctrl+Break to force server shutdown."
            )
            return

        state.is_shutting_down = True
        state.shutdown_event.set()
        super().handle_exit(sig, frame)


def run_ui_server(host: str, port: int, reload: bool = False) -> None:
    """Run the UI server with bounded, signal-aware graceful shutdown."""
    state.host = host
    state.port = port
    write_server_info(port=port, host=host, lifecycle_token=LIFECYCLE_TOKEN)

    try:
        if reload:
            uvicorn.run(
                "apps.harness_server.server:app",
                host=host,
                port=port,
                reload=True,
                timeout_graceful_shutdown=5,
            )
            return

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            timeout_graceful_shutdown=5,
        )
        server = ArtemisUvicornServer(config)
        app.state.uvicorn_server = server
        server.run()
    finally:
        app.state.uvicorn_server = None
        clear_server_info(port=port, lifecycle_token=LIFECYCLE_TOKEN)


def main(argv: list[str] | None = None) -> None:
    """Parse the daemon/standalone server bind address and run Uvicorn."""
    parser = argparse.ArgumentParser(description="Run the Artemis harness server")
    parser.add_argument(
        "--host",
        default=os.environ.get("ARTEMIS_SERVER_HOST", "127.0.0.1"),
        help=(
            "Address to bind the HTTP server to. Defaults to loopback; expose "
            "remotely via a Tailscale/SSH tunnel rather than a wide bind."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT", "8000")),
        help="TCP port for the HTTP server.",
    )
    args = parser.parse_args(argv)
    run_ui_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
