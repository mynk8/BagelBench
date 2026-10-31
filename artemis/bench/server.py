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

"""The benchmark device server: the one interface every agent uses.

``build_bench_server`` exposes a UI-only tool set over an actuator:

- device actions from the canonical manifest (tap, long press, type, swipe, keys,
  launch/stop app, wait) -- no ``open_link``, no shell;
- ``observe_screen``: the indexed UI element list plus a screenshot;
- mobile-condition tools (:mod:`artemis.bench.conditions`);
- ``submit_verdict``: the run's single final answer.

Every call is a numbered step. After each one the harness records the screen it
sees (foreground activity, element list, screenshot) in the run record, which is
what grading reads; the agent's own account is never used.

The same server object is used in-process by the Flash reference agent and over
streamable HTTP by external harnesses (Claude Code, Codex, ... via Harbor's
``[[environment.mcp_servers]]``), so every agent has identical powers.

``BenchHost`` serves one MCP endpoint per task *slot* at ``/t/<slot>/mcp``. Slot
ids are opaque, so the URL an agent sees reveals nothing about the case or build.
A slot's first tool call runs its setup commands (reset the emulator, install the
build, seed state) and opens a fresh run record. Verifiers fetch the record from
``/t/<slot>/record`` with a bearer token the agent never sees.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ImageContent, TextContent

from artemis.bench.conditions import DeviceConditions, Shell, foreground_activity
from artemis.bench.recorder import RunRecorder, Screen, Step, VerdictAlreadySubmitted
from artemis.mcp.action_specs import make_wire_handler, wire_dialects
from artemis.mcp.action_types import ActionCode, ActionResult, ObserveResult
from artemis.mcp.observation import observe as observe_impl
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

#: Device actions an agent may take: the same set Flash declares, so the reference
#: agent and external harnesses get one surface. Excluded: ``open_link`` (reaches
#: the web), ``wait_for_text`` (a search helper) and the wire-only text helpers
#: ``erase_one_char`` / ``focus_and_clear_text`` (``input_text`` clears a field).
BENCH_ACTIONS = frozenset(
    {
        "click",
        "click_sequence",
        "long_press",
        "input_text",
        "swipe",
        "press_key",
        "manage_app",
        "wait_for_delay",
    }
)

CONDITION_TOOLS = (
    "rotate",
    "background_app",
    "kill_app_process",
    "set_network",
    "set_permission",
    "set_font_scale",
    "set_dark_mode",
)

INSTRUCTIONS = (
    "You are testing an Android app on a real device. Act only through these tools."
    " Every tool result starts with its step number. Call observe_screen to see the"
    " screen. When you are done, call submit_verdict exactly once: DEFECT with the"
    " step whose screen shows the defect, NO_DEFECT, or INCONCLUSIVE."
)


def _text_result(message: str, *, error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], isError=error)


def _prefix(step: int, result: CallToolResult) -> CallToolResult:
    content = list(result.content)
    if content and isinstance(content[0], TextContent):
        content[0] = TextContent(type="text", text=f"[step {step}] {content[0].text}")
    else:
        content.insert(0, TextContent(type="text", text=f"[step {step}]"))
    structured = result.structuredContent
    if isinstance(structured, dict) and isinstance(structured.get("message"), str):
        structured = {**structured, "message": f"[step {step}] {structured['message']}"}
    return CallToolResult(content=content, structuredContent=structured, isError=result.isError)


def _wrap_action(res: ActionResult) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=res.message)],
        structuredContent=res.model_dump(mode="json"),
        isError=False,
    )


def _wrap_action_exception(action: str, exc: Exception) -> CallToolResult:
    return _wrap_action(ActionResult.failure(action, f"Error during {action}: {exc}"))


def _security(public_hosts: list[str] | None) -> TransportSecuritySettings:
    """DNS-rebinding protection that also admits the hosts agents use to reach us."""
    hosts = ["127.0.0.1", "localhost", "[::1]", *(public_hosts or [])]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{h}:*" for h in hosts] + list(hosts),
        allowed_origins=[f"http://{h}:*" for h in hosts],
    )


def build_bench_server(
    actuator: Any,
    recorder: RunRecorder,
    shell: Shell,
    *,
    app_package: str | None = None,
    settle_ms: int = 400,
    step_budget: int | None = None,
    public_hosts: list[str] | None = None,
    name: str = "android",
    on_first_call: Callable[[], Awaitable[None]] | None = None,
) -> FastMCP:
    """Builds the bench tool server over ``actuator``, recording into ``recorder``."""
    mcp = FastMCP(name, instructions=INSTRUCTIONS, transport_security=_security(public_hosts))
    conditions = DeviceConditions(shell, app_package)
    ctx: Any = getattr(actuator, "ctx", None)
    controller: Any = getattr(actuator, "controller", None)
    started = asyncio.Event()

    async def ensure_started() -> None:
        if not started.is_set():
            if on_first_call is not None:
                await on_first_call()
            started.set()

    async def snapshot(step: int, settle: int) -> tuple[Screen, Any]:
        """The harness's own view of the screen after ``step``."""
        screen = Screen()
        obs = None
        try:
            obs, image = await observe_impl(ctx, controller, settle_ms=settle)
            if obs.ok:
                screen.elements = obs.elements if obs.hierarchy_ok else []
                if image:
                    path = recorder.screenshot_path(step)
                    path.write_bytes(image)
                    screen.screenshot = str(path.relative_to(recorder.run_dir))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(f"Bench snapshot after step {step} failed: {exc}")
        with contextlib.suppress(Exception):
            screen.activity = await foreground_activity(shell)
        return screen, obs

    async def record(
        tool: str, args: dict[str, Any], ok: bool, message: str, settle: int = settle_ms
    ) -> tuple[int, Any]:
        step = recorder.next_step()
        screen, obs = await snapshot(step, settle)
        recorder.record_step(
            Step(
                step=step,
                timestamp=time.time(),
                tool=tool,
                args=args,
                ok=ok,
                message=message,
                screen=screen,
            )
        )
        return step, obs

    def refusal(*, action: bool = True) -> str | None:
        """Why the tool may not run, or None. Observing never spends the budget."""
        if recorder.verdict_submitted:
            return "This run is over: a verdict was already submitted."
        if action and step_budget is not None and recorder.action_count >= step_budget:
            return f"Action budget of {step_budget} used up. Call submit_verdict now."
        return None

    def closed(*, action: bool = True) -> CallToolResult | None:
        reason = refusal(action=action)
        return _text_result(reason, error=True) if reason else None

    async def unknown_package(args: dict[str, Any]) -> str | None:
        """manage_app takes an exact installed package, so no model resolves names."""
        name = str(args.get("app_name") or "")
        listing = await shell(["pm", "list", "packages"])
        installed = {line.removeprefix("package:").strip() for line in listing.splitlines()}
        if name in installed:
            return None
        return f"'{name}' is not an installed package. Pass the exact package name, e.g. org.tasks."

    # --- Device actions ------------------------------------------------------------
    for spec in wire_dialects():
        if spec.name not in BENCH_ACTIONS or spec.name not in actuator.capabilities():
            continue
        inner = make_wire_handler(spec, actuator, _wrap_action, _wrap_action_exception)

        def recorded(inner=inner, tool=spec.name):
            async def handler(**kwargs: Any) -> CallToolResult:
                if (reason := refusal()) is not None:
                    # Device tools declare an ActionResult output schema: refuse in kind.
                    return _wrap_action(ActionResult.failure(tool, reason))
                await ensure_started()
                if tool == "manage_app" and (reason := await unknown_package(kwargs)):
                    step, _ = await record(tool, kwargs, False, reason)
                    return _prefix(step, _wrap_action(ActionResult.failure(tool, reason)))
                result = await inner(**kwargs)
                payload = result.structuredContent or {}
                message = result.content[0].text if result.content else ""
                step, _ = await record(tool, kwargs, bool(payload.get("ok", True)), message)
                return _prefix(step, result)

            handler.__name__ = inner.__name__
            handler.__doc__ = inner.__doc__
            handler.__signature__ = inner.__signature__  # type: ignore[attr-defined]
            handler.__annotations__ = inner.__annotations__
            return handler

        mcp.add_tool(recorded(), name=spec.name, description=inner.__doc__ or "")

    # --- Observation -----------------------------------------------------------------

    @mcp.tool()
    async def observe_screen(include_image: bool = True, settle_ms: int = 400) -> CallToolResult:
        """Look at the screen: the indexed list of visible UI elements with their
        bounds and, by default, a screenshot. Bounds and every tap/swipe coordinate use
        the same 0-1000 normalized space (x left to right, y top to bottom). Observing
        does not use up the action budget."""
        if (reason := refusal(action=False)) is not None:
            refused = ObserveResult(
                ok=False, code=ActionCode.INVALID_ARGS, message=reason, hierarchy_ok=False
            )
            return CallToolResult(
                content=[TextContent(type="text", text=reason)],
                structuredContent=refused.model_dump(mode="json"),
                isError=True,
            )
        await ensure_started()
        settle = max(0, min(int(settle_ms), 3000))
        step, obs = await record(
            "observe_screen", {"include_image": include_image}, True, "", settle=settle
        )
        if obs is None or not obs.ok:
            failed = ObserveResult(
                ok=False,
                code=ActionCode.DEVICE_ERROR,
                message=f"[step {step}] Could not read the screen.",
                hierarchy_ok=False,
            )
            return CallToolResult(
                content=[TextContent(type="text", text=failed.message)],
                structuredContent=failed.model_dump(mode="json"),
                isError=True,
            )
        shot = recorder.screenshot_path(step)
        observed = obs.model_copy(
            update={
                "message": f"[step {step}] {obs.message}".rstrip(),
                "screenshot_path": str(shot) if shot.is_file() else obs.screenshot_path,
            }
        )
        content: list[Any] = [
            TextContent(
                type="text",
                text=(
                    f"[step {step}] Visible elements (bounds normalized 0-1000):\n"
                    f"{obs.elements_text or ''}"
                ),
            )
        ]
        if include_image and shot.is_file():
            import base64

            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(shot.read_bytes()).decode("ascii"),
                    mimeType="image/jpeg",
                )
            )
        return CallToolResult(
            content=content, structuredContent=observed.model_dump(mode="json"), isError=False
        )

    # --- Mobile conditions -----------------------------------------------------------

    async def apply(tool: str, args: dict[str, Any], run: Awaitable[Any]) -> CallToolResult:
        if (done := closed()) is not None:
            return done
        await ensure_started()
        try:
            outcome = await run
            ok, message = outcome.ok, outcome.message
        except Exception as exc:  # pylint: disable=broad-exception-caught
            ok, message = False, f"{tool} failed: {exc}"
        step, _ = await record(tool, args, ok, message)
        return _text_result(f"[step {step}] {message}", error=not ok)

    @mcp.tool()
    async def rotate(orientation: str) -> CallToolResult:
        """Rotate the device: portrait, landscape, reverse_portrait or reverse_landscape."""
        return await apply("rotate", {"orientation": orientation}, conditions.rotate(orientation))

    @mcp.tool()
    async def background_app() -> CallToolResult:
        """Send the current app to the background (go to the home screen)."""
        return await apply("background_app", {}, conditions.background_app())

    @mcp.tool()
    async def kill_app_process() -> CallToolResult:
        """Simulate process death of the app under test: background it, then kill its
        process, as Android does under memory pressure."""
        return await apply("kill_app_process", {}, conditions.kill_app_process())

    @mcp.tool()
    async def set_network(enabled: bool) -> CallToolResult:
        """Turn the device's network (Wi-Fi and mobile data) on or off."""
        return await apply("set_network", {"enabled": enabled}, conditions.set_network(enabled))

    @mcp.tool()
    async def set_permission(permission: str, granted: bool) -> CallToolResult:
        """Grant or revoke a runtime permission (e.g. android.permission.CAMERA) for
        the app under test."""
        return await apply(
            "set_permission",
            {"permission": permission, "granted": granted},
            conditions.set_permission(permission, granted),
        )

    @mcp.tool()
    async def set_font_scale(scale: float) -> CallToolResult:
        """Set the system font scale: 0.85, 1.0, 1.15, 1.3, 1.5 or 2.0."""
        return await apply("set_font_scale", {"scale": scale}, conditions.set_font_scale(scale))

    @mcp.tool()
    async def set_dark_mode(enabled: bool) -> CallToolResult:
        """Turn the system dark theme on or off."""
        return await apply("set_dark_mode", {"enabled": enabled}, conditions.set_dark_mode(enabled))

    # --- Final answer ----------------------------------------------------------------

    @mcp.tool()
    async def submit_verdict(
        verdict: str, flag_step: int | None = None, note: str = ""
    ) -> CallToolResult:
        """Submit your final answer, once. verdict: DEFECT, NO_DEFECT or INCONCLUSIVE.
        For DEFECT, flag_step is the step number whose screen shows the defect."""
        try:
            record_ = recorder.submit_verdict(verdict, flag_step, note)
        except (ValueError, VerdictAlreadySubmitted) as exc:
            return _text_result(str(exc), error=True)
        return _text_result(f"Verdict recorded: {record_['verdict']}. The run is over.")

    return mcp


# --- Device access ---------------------------------------------------------------------


def adb_shell(adb_client: Any, serial: str) -> Shell:
    """A :data:`Shell` over a ``adbutils``-style client for ``serial``."""

    async def run(argv: list[str]) -> str:
        device = adb_client.device(serial)
        return await asyncio.to_thread(device.shell, shlex.join(argv))

    return run


def device_actuator(serial: str, adb_host: str = "127.0.0.1", adb_port: int = 5037) -> Any:
    """An ``AdbActuator`` with its own context for ``serial`` (no agent run needed)."""
    from adbutils import AdbClient

    from artemis.clients.screen_client_factory import create_screen_client
    from artemis.context import ArtemisContext, DevicePlatform
    from artemis.mcp.actuators.adb import AdbActuator
    from artemis.platform import platform as host_platform
    from third_party.mobile_use.context import DeviceContext

    adb_client = AdbClient(host=adb_host, port=adb_port)
    try:
        width, height = adb_client.device(serial).window_size()
    except Exception:  # pylint: disable=broad-exception-caught
        width, height = 1080, 2400
    ctx = ArtemisContext(
        device=DeviceContext(
            host_platform=host_platform.os_type.name,
            mobile_platform=DevicePlatform.ANDROID,
            device_id=serial,
            device_width=width,
            device_height=height,
        ),
        adb_client=adb_client,
        ui_adb_client=create_screen_client(serial),
    )
    return AdbActuator(ctx)


# --- Slots and hosting ------------------------------------------------------------------


@dataclass
class Slot:
    """One exported benchmark task: a case on one build. Kept host-side only."""

    slot_id: str
    case_id: str
    build: str
    app_package: str | None = None
    setup: list[list[str]] = field(default_factory=list)
    """Host-side argv commands run before the agent's first call (reset, install, seed)."""
    step_budget: int | None = None


def new_slot_id() -> str:
    return secrets.token_urlsafe(12)


def load_slots(path: Path) -> dict[str, Slot]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["slot_id"]: Slot(**item) for item in data.get("slots", [])}


def save_slots(path: Path, slots: list[Slot]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"slots": [asdict(s) for s in slots]}, indent=2), encoding="utf-8")


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
                proc = await asyncio.create_subprocess_exec(*argv)
                if await proc.wait() != 0:
                    raise RuntimeError(f"Setup step failed: {shlex.join(argv)}")
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
            from artemis.bench.recorder import load_steps, load_verdict

            run_dir = self.run_dir(slot_id)
            return JSONResponse({"steps": load_steps(run_dir), "verdict": load_verdict(run_dir)})

        @contextlib.asynccontextmanager
        async def lifespan(_app: Any):
            async with contextlib.AsyncExitStack() as stack:
                for server in servers.values():
                    await stack.enter_async_context(server.session_manager.run())
                yield

        routes: list[Any] = [Route("/t/{slot}/record", record)]
        for slot_id, server in servers.items():
            routes.append(Mount(f"/t/{slot_id}", app=server.streamable_http_app()))
        return Starlette(routes=routes, lifespan=lifespan)


def serve(
    slots_file: Path,
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
        load_slots(slots_file),
        runs_dir,
        actuator,
        adb_shell(actuator.ctx.adb_client, serial),
        verifier_token,
        public_hosts=public_hosts,
    ).app()
    uvicorn.run(host_app, host=host, port=port)
