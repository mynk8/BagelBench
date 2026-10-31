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

"""MCP tools for the benchmark device surface.

Builds one tool server over an actuator, records every action and observation,
enforces the action budget, and accepts the final verdict. HTTP slot hosting
lives in bagel.transports.http.benchmark; device construction lives in
bagel.device.factory.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ImageContent, TextContent

from bagel.benchmark.policy import BENCH_ACTIONS, CONDITION_TOOLS
from bagel.device.conditions import DeviceConditions, Shell, foreground_activity
from bagel.benchmark.recording import RunRecorder, Screen, Step, VerdictAlreadySubmitted
from bagel.transports.mcp.specs import make_wire_handler, wire_dialects
from bagel.device.results import ActionCode, ActionResult, ObserveResult
from bagel.device.observation import observe as observe_impl
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

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
