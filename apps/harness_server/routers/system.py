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

"""System readiness, device selection and server lifecycle routes."""

import ipaddress
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from artemis.core.diagnostics import readiness_engine
from artemis.core.diagnostics.schema import SystemReadinessReport

router = APIRouter(prefix="/api/system", tags=["system"])


def _require_loopback_request(request: Request, detail: str) -> None:
    """Reject requests whose TCP peer is not the local machine."""
    client_host = request.client.host if request.client else None
    try:
        is_loopback = bool(client_host and ipaddress.ip_address(client_host).is_loopback)
    except ValueError:
        is_loopback = bool(client_host and client_host.lower() == "localhost")
    if not is_loopback:
        raise HTTPException(status_code=403, detail=detail)


def _require_local_lifecycle_request(request: Request) -> None:
    """Authorize a process-lifecycle request from the local CLI only."""
    _require_loopback_request(request, "Server lifecycle controls are local-only.")

    expected = getattr(request.app.state, "lifecycle_token", None)
    supplied = request.headers.get("x-artemis-lifecycle-token")
    if not (
        isinstance(expected, str)
        and isinstance(supplied, str)
        and secrets.compare_digest(expected, supplied)
    ):
        raise HTTPException(status_code=403, detail="Invalid server lifecycle token.")


class SelectDeviceRequest(BaseModel):
    """Payload to select an active target Android device."""

    serial: str = Field(description="Serial number or identifier of the Android device to select")


@router.get("/readiness", response_model=SystemReadinessReport)
async def get_system_readiness(force: bool = False) -> SystemReadinessReport:
    """Execute all diagnostic probes and return a comprehensive system readiness report."""
    return await readiness_engine.run_all(force_refresh=force)


@router.post("/devices/select")
async def select_active_device(request: SelectDeviceRequest):
    """Select the active Android device or emulator for subsequent automated tasks."""
    serial = request.serial.strip()
    if not serial:
        raise HTTPException(status_code=400, detail="Device serial cannot be empty.")

    readiness_engine.set_probe_target_serial(serial)
    # Return updated readiness
    report = await readiness_engine.run_all(force_refresh=True)
    return {
        "status": "success",
        "selected_serial": serial,
        "report": report,
    }


@router.get("/server-status")
async def get_server_runtime_status():
    """Retrieve runtime status, PID, port, and uptime of the Artemis server.

    Answers from in-process state. ``server_lifecycle.get_server_status`` is
    not used here: it runs ``lsof``/``fuser``, which can take over a second and
    is too slow for the ``is_artemis_daemon`` probe.
    """
    import os
    import time

    from artemis.runtime.process_probe import pid_is_alive
    from artemis.runtime.server_lifecycle import read_server_info

    try:
        from apps.harness_server.core.state import state
    except ImportError:
        from harness_server.core.state import state

    port = getattr(state, "port", 8000)
    current_pid = os.getpid()
    pids = {current_pid}
    started_at = None

    info = read_server_info()
    if info and info.get("port") == port:
        saved_pid = info.get("pid")
        if isinstance(saved_pid, int) and saved_pid != current_pid and pid_is_alive(saved_pid):
            pids.add(saved_pid)
        if isinstance(info.get("started_at"), (int, float)):
            started_at = float(info["started_at"])
    if started_at is None:
        try:
            import psutil

            started_at = psutil.Process(current_pid).create_time()
        except Exception:  # pylint: disable=broad-exception-caught
            # psutil is optional; uptime is best-effort.
            started_at = None

    uptime_seconds = max(0.0, time.time() - started_at) if started_at is not None else None
    # Explicit DTO: the raw metadata file additionally holds the lifecycle
    # token, cmdline, and filesystem paths, none of which belong on the wire.
    return {
        "running": True,
        "port": port,
        "pids": sorted(pids),
        "active_pid": current_pid,
        "uptime_seconds": uptime_seconds,
        "url": f"http://localhost:{port}",
        "current_pid": current_pid,
    }


@router.post("/shutdown", status_code=202)
async def shutdown_server_endpoint(request: Request):
    """Request a graceful shutdown of the Artemis server."""
    import asyncio

    try:
        from apps.harness_server.core.state import state
    except ImportError:
        from harness_server.core.state import state

    _require_local_lifecycle_request(request)
    server = getattr(request.app.state, "uvicorn_server", None)
    if server is None:
        raise HTTPException(status_code=503, detail="Server lifecycle controller is unavailable.")

    async def _shutdown_after_response() -> None:
        # Let Starlette flush the accepted response before Uvicorn leaves its
        # main loop and invokes the FastAPI shutdown lifecycle.
        await asyncio.sleep(0.05)
        state.is_shutting_down = True
        state.shutdown_event.set()
        server.should_exit = True

    asyncio.create_task(_shutdown_after_response())

    return {
        "status": "shutting_down",
        "message": "Artemis server is shutting down.",
        "pid": os.getpid(),
    }
