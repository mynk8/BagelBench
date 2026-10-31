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

"""Wire the Flash reference agent to the bench device server.

Flash drives the same :func:`~artemis.bench.server.build_bench_server` object that
external harnesses reach over HTTP, through an in-process session installed on the
run context. Its tool set is therefore the bench set: the bench device actions, the
mobile-condition tools and ``submit_verdict`` (declared to Flash as actuator
extensions, executed by the bench server).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from artemis.bench.recorder import RunRecorder
from artemis.bench.server import BENCH_ACTIONS, adb_shell, build_bench_server
from artemis.mcp.action_manifest import ExtensionTool

RUN_DIR_ENV = "ARTEMIS_BENCH_RUN_DIR"
APP_PACKAGE_ENV = "ARTEMIS_BENCH_APP_PACKAGE"
STEP_BUDGET_ENV = "ARTEMIS_BENCH_STEP_BUDGET"


async def _served_by_bench_server(**_kwargs: Any) -> Any:
    raise RuntimeError("Bench tools are executed by the bench server, not the actuator.")


def _ext(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> ExtensionTool:
    return ExtensionTool(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": properties, "required": required},
        handler=_served_by_bench_server,
        targets=frozenset({"flash"}),
    )


BENCH_EXTENSIONS = (
    _ext(
        "rotate",
        "Rotate the device to test orientation handling and state preservation:"
        " portrait, landscape, reverse_portrait or reverse_landscape.",
        {
            "orientation": {
                "type": "string",
                "enum": ["portrait", "landscape", "reverse_portrait", "reverse_landscape"],
            }
        },
        ["orientation"],
    ),
    _ext(
        "background_app",
        "Send the current app to the background (home screen) to test resume behavior.",
        {},
        [],
    ),
    _ext(
        "kill_app_process",
        "Simulate process death of the app under test (background it, then kill its"
        " process, as Android does under memory pressure). Reopen it afterwards to check"
        " whether its state survived.",
        {},
        [],
    ),
    _ext(
        "set_network",
        "Turn the device's network (Wi-Fi and mobile data) on or off to test offline behavior.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _ext(
        "set_permission",
        "Grant or revoke a runtime permission (e.g. android.permission.CAMERA) for the"
        " app under test.",
        {"permission": {"type": "string"}, "granted": {"type": "boolean"}},
        ["permission", "granted"],
    ),
    _ext(
        "set_font_scale",
        "Set the system font scale (0.85, 1.0, 1.15, 1.3, 1.5 or 2.0) to test layout"
        " with large text.",
        {"scale": {"type": "number", "enum": [0.85, 1.0, 1.15, 1.3, 1.5, 2.0]}},
        ["scale"],
    ),
    _ext(
        "set_dark_mode",
        "Turn the system dark theme on or off to test theming and contrast.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _ext(
        "submit_verdict",
        "Submit your final answer, exactly once; the run ends. verdict: DEFECT,"
        " NO_DEFECT or INCONCLUSIVE. For DEFECT, flag_step is the step number (shown"
        " as [step N] in tool results) whose screen shows the defect.",
        {
            "verdict": {"type": "string", "enum": ["DEFECT", "NO_DEFECT", "INCONCLUSIVE"]},
            "flag_step": {"type": "integer"},
            "note": {"type": "string"},
        },
        ["verdict"],
    ),
)


class BenchActuator:
    """Presents a device actuator to Flash with exactly the bench tool surface."""

    def __init__(self, inner: Any):
        self._inner = inner

    def capabilities(self) -> frozenset[str]:
        return frozenset(self._inner.capabilities()) & BENCH_ACTIONS

    def extensions(self) -> list[ExtensionTool]:
        return list(BENCH_EXTENSIONS)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@dataclass(frozen=True)
class BenchRun:
    """Where Flash records a benchmark run, read from the environment."""

    run_dir: Path
    app_package: str | None = None
    step_budget: int | None = None

    @classmethod
    def from_env(cls) -> BenchRun | None:
        run_dir = os.environ.get(RUN_DIR_ENV)
        if not run_dir:
            return None
        budget = os.environ.get(STEP_BUDGET_ENV)
        return cls(
            run_dir=Path(run_dir),
            app_package=os.environ.get(APP_PACKAGE_ENV) or None,
            step_budget=int(budget) if budget else None,
        )

    @classmethod
    def for_session(cls, ctx: Any) -> BenchRun:
        """The default run directory: ``bench/`` inside the session's trace folder."""
        engine = getattr(ctx, "data_engine", None)
        base = getattr(engine, "base_dir", None) if engine else None
        if base is None:
            from artemis.config import TRACES_PATH

            base = Path(TRACES_PATH) / f"run-{os.getpid()}"
        return cls(run_dir=Path(base) / "bench")


async def install_bench_session(ctx: Any, run: BenchRun) -> None:
    """Routes this run's device access through a recording bench server."""
    from artemis.mcp.action_session import ActionSession
    from artemis.mcp.actuators.adb import AdbActuator

    device = AdbActuator(ctx)
    serial = getattr(ctx.device, "device_id", None)
    if not serial:
        raise RuntimeError("A bench run needs a device: the run context has no device id.")
    server = build_bench_server(
        device,
        RunRecorder(run.run_dir),
        adb_shell(ctx.adb_client, serial),
        app_package=run.app_package,
        step_budget=run.step_budget,
    )
    session = ActionSession(server)
    await session.start()
    ctx.actuator = BenchActuator(device)
    ctx.action_session = session
