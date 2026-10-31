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

"""HTTP host for benchmark MCP endpoints and authenticated verifier records."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
import secrets
from typing import Any

from mcp.server.fastmcp import FastMCP

from bagel.benchmark.recording import RunRecorder, load_steps, load_verdict
from bagel.benchmark.slots import Slot
from bagel.benchmark.grading import label_run, reward_for
from bagel.device.conditions import Shell
from bagel.device.factory import adb_shell, device_actuator
from bagel.transports.mcp.benchmark import build_bench_server
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class BenchHost:
    """Serves ``/t/<slot>/mcp`` per slot on one device; one active run at a time."""

    def __init__(
        self,
        slots: dict[str, Slot],
        runs_dir: Path,
        actuator: Any,
        shell: Shell,
        verifier_token: str,
        public_hosts: list[str] | None = None,
    ):
        self.slots = slots
        self.runs_dir = Path(runs_dir)
        self.actuator = actuator
        self.shell = shell
        self.verifier_token = verifier_token
        self.public_hosts = list(public_hosts or [])
        self._active: str | None = None
        self._lock = asyncio.Lock()

    def run_dir(self, slot_id: str) -> Path:
        return self.runs_dir / slot_id

    async def _start(self, slot: Slot) -> None:
        async with self._lock:
            if (
                self._active not in (None, slot.slot_id)
                and not RunRecorder(self.run_dir(self._active)).verdict_submitted
            ):
                raise RuntimeError("The device is busy with another run; try again later.")
            for argv in slot.setup:
                try:
                    proc = await asyncio.create_subprocess_exec(*argv, cwd=slot.setup_cwd)
                    status = await proc.wait()
                except OSError:
                    logger.error(f"Private Android setup could not start for slot {slot.slot_id}.")
                    raise RuntimeError(
                        "Android setup failed before the test could start."
                    ) from None
                if status != 0:
                    logger.error(f"Private Android setup failed for slot {slot.slot_id}.")
                    raise RuntimeError("Android setup failed before the test could start.")
            self._active = slot.slot_id
            logger.info(f"Bench slot {slot.slot_id} started ({slot.case_id}, {slot.build}).")

    def server_for(self, slot: Slot) -> FastMCP:
        recorder = RunRecorder(self.run_dir(slot.slot_id))
        return build_bench_server(
            self.actuator,
            recorder,
            self.shell,
            app_package=slot.app_package,
            step_budget=slot.step_budget,
            public_hosts=self.public_hosts,
            on_first_call=lambda: self._start(slot),
        )

    def app(self) -> Any:
        """A Starlette app mounting every slot's MCP endpoint plus the record route."""
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route

        servers = {slot_id: self.server_for(slot) for slot_id, slot in self.slots.items()}

        async def record(request: Request) -> JSONResponse:
            auth = request.headers.get("authorization", "")
            if not secrets.compare_digest(auth, f"Bearer {self.verifier_token}"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            slot_id = request.path_params["slot"]
            if slot_id not in self.slots:
                return JSONResponse({"error": "unknown slot"}, status_code=404)
            run_dir = self.run_dir(slot_id)
            return JSONResponse({"steps": load_steps(run_dir), "verdict": load_verdict(run_dir)})

        async def reward(request: Request) -> JSONResponse:
            auth = request.headers.get("authorization", "")
            if not secrets.compare_digest(auth, f"Bearer {self.verifier_token}"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            slot = self.slots.get(request.path_params["slot"])
            if slot is None:
                return JSONResponse({"error": "unknown slot"}, status_code=404)
            if slot.signature is None:
                return JSONResponse({"error": "no grading signature"}, status_code=409)
            run_dir = self.run_dir(slot.slot_id)
            label = label_run(
                slot.build, load_steps(run_dir), load_verdict(run_dir), slot.signature
            )
            return JSONResponse({"reward": reward_for(label), "label": label, "build": slot.build})

        @contextlib.asynccontextmanager
        async def lifespan(_app: Any):
            async with contextlib.AsyncExitStack() as stack:
                for server in servers.values():
                    await stack.enter_async_context(server.session_manager.run())
                yield

        routes: list[Any] = [Route("/t/{slot}/record", record), Route("/t/{slot}/reward", reward)]
        for slot_id, server in servers.items():
            routes.append(Mount(f"/t/{slot_id}", app=server.streamable_http_app()))
        return Starlette(routes=routes, lifespan=lifespan)


def serve(
    slots: dict[str, Slot],
    runs_dir: Path,
    serial: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    verifier_token: str,
    public_hosts: list[str] | None = None,
) -> None:
    """Run the bench host for ``serial`` until interrupted."""
    import uvicorn

    actuator = device_actuator(serial)
    host_app = BenchHost(
        slots,
        runs_dir,
        actuator,
        adb_shell(actuator.ctx.adb_client, serial),
        verifier_token,
        public_hosts=public_hosts,
    ).app()
    uvicorn.run(host_app, host=host, port=port)
