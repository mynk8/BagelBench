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

"""Export benchmark cases as Harbor tasks, so any Harbor agent can be scored.

Harbor (the Terminal-Bench harness) runs pre-integrated agents such as
``claude-code`` and ``codex`` against tasks laid out as::

    <task>/instruction.md        the prompt shown to the agent
    <task>/task.toml             timeouts, network policy, MCP servers, verifier env
    <task>/environment/Dockerfile
    <task>/tests/test.sh         writes /logs/verifier/reward.json

Each exported task declares the device server under ``[[environment.mcp_servers]]``
with an opaque slot URL, so the agent's only route to the phone is the bench tool
set. ``tests/`` holds the hidden signature and the stdlib grader; Harbor does not
show it to the agent. The build (faulty or correct) appears only in ``tests/`` and
in the host-side files written next to the export:

- ``slots.json``: what the device host serves (slot -> case, build, setup).
- ``manifest.json``: slot -> case, app, build, repeat, for aggregate scoring.

Neither belongs in a task directory.

Input cases (JSON list)::

    {"case_id": "tasks-readonly-delete", "app": "tasks", "app_package": "org.tasks",
     "prompts": {"directed": "...", "feature_hint": "...", "open": "..."},
     "signature": {...}, "builds": {"faulty": {"setup": [[...]]}, "correct": {...}},
     "step_budget": {"directed": 40, "feature_hint": 80, "open": 150}}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from artemis.bench import grading
from artemis.bench.grading import CORRECT, FAULTY
from artemis.bench.server import Slot, new_slot_id, save_slots

GUIDANCE_LEVELS = ("directed", "feature_hint", "open")

ANSWER_PROTOCOL = """
## How to work

You are testing an Android app on a real device through the `android` MCP tools.
They are your only way to reach the device: look with `observe_screen`, act with the
touch, typing and navigation tools, and change device conditions (rotation, process
death, network, permissions, font scale, dark mode) with their tools. Every tool
result starts with a step number.

You have at most {budget} steps.

## How to answer

Call `submit_verdict` exactly once:

- `DEFECT` with `flag_step` set to the step whose screen shows the defect,
- `NO_DEFECT` if the app behaves correctly,
- `INCONCLUSIVE` if you cannot tell.

Only the verdict and the screen at `flag_step` are graded.
"""

DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
"""

TEST_SH = """#!/bin/sh
# Fetch this run's record from the device host and grade it without a model.
set -eu
python3 - <<'PY'
import os, urllib.request
req = urllib.request.Request(
    os.environ["BENCH_RECORD_URL"],
    headers={{"Authorization": "Bearer " + os.environ["BENCH_VERIFIER_TOKEN"]}},
)
with urllib.request.urlopen(req, timeout=30) as resp, open("/tmp/record.json", "wb") as out:
    out.write(resp.read())
PY
python3 /tests/grade.py --record /tmp/record.json --signature /tests/signature.json \\
    --build {build} --out /logs/verifier/reward.json
"""


def _toml_str(value: str) -> str:
    return json.dumps(value)


def _task_toml(
    *,
    name: str,
    mcp_url: str,
    record_url: str,
    verifier_token: str,
    allowed_hosts: list[str],
    agent_timeout_sec: int,
    guidance: str,
    app: str,
) -> str:
    hosts = ", ".join(_toml_str(h) for h in allowed_hosts)
    return f"""schema_version = "1.4"

[task]
name = {_toml_str(name)}

[metadata]
category = "mobile-qa"
guidance_level = {_toml_str(guidance)}
app = {_toml_str(app)}

[agent]
timeout_sec = {float(agent_timeout_sec)}

[verifier]
timeout_sec = 120.0
env = {{ BENCH_RECORD_URL = {_toml_str(record_url)}, BENCH_VERIFIER_TOKEN = {_toml_str(verifier_token)} }}

[environment]
network_mode = "allowlist"
allowed_hosts = [{hosts}]

[[environment.mcp_servers]]
name = "android"
transport = "streamable-http"
url = {_toml_str(mcp_url)}
"""


def export_harbor(
    cases: list[dict[str, Any]],
    out_dir: Path,
    *,
    device_host_url: str,
    verifier_token: str,
    guidance: str = "directed",
    repeats: int = 3,
    extra_allowed_hosts: list[str] | None = None,
    agent_timeout_sec: int = 1800,
    dataset: str = "artemis-android-qa",
) -> dict[str, Any]:
    """Writes one Harbor task per (case, build, repeat) and the host-side files."""
    if guidance not in GUIDANCE_LEVELS:
        raise ValueError(f"guidance must be one of {', '.join(GUIDANCE_LEVELS)}")
    base = device_host_url.rstrip("/")
    device_host = base.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    allowed_hosts = [device_host, *(extra_allowed_hosts or [])]
    tasks_dir = out_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    grader_source = Path(grading.__file__)

    slots: list[Slot] = []
    manifest: list[dict[str, Any]] = []
    for case in cases:
        prompt = (case.get("prompts") or {}).get(guidance)
        if not prompt:
            raise ValueError(f"Case {case['case_id']} has no {guidance!r} prompt.")
        budget = int((case.get("step_budget") or {}).get(guidance, 60))
        for build in (FAULTY, CORRECT):
            build_cfg = (case.get("builds") or {}).get(build) or {}
            for repeat in range(1, repeats + 1):
                slot = Slot(
                    slot_id=new_slot_id(),
                    case_id=case["case_id"],
                    build=build,
                    app_package=case.get("app_package"),
                    setup=[list(map(str, argv)) for argv in build_cfg.get("setup") or []],
                    step_budget=budget,
                )
                task_dir = tasks_dir / slot.slot_id
                (task_dir / "environment").mkdir(parents=True, exist_ok=True)
                (task_dir / "tests").mkdir(parents=True, exist_ok=True)
                (task_dir / "instruction.md").write_text(
                    prompt.strip() + "\n" + ANSWER_PROTOCOL.format(budget=budget),
                    encoding="utf-8",
                )
                (task_dir / "task.toml").write_text(
                    _task_toml(
                        name=f"{dataset}/{slot.slot_id}",
                        mcp_url=f"{base}/t/{slot.slot_id}/mcp",
                        record_url=f"{base}/t/{slot.slot_id}/record",
                        verifier_token=verifier_token,
                        allowed_hosts=allowed_hosts,
                        agent_timeout_sec=agent_timeout_sec,
                        guidance=guidance,
                        app=str(case.get("app") or ""),
                    ),
                    encoding="utf-8",
                )
                (task_dir / "environment" / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
                shutil.copyfile(grader_source, task_dir / "tests" / "grade.py")
                (task_dir / "tests" / "signature.json").write_text(
                    json.dumps(case["signature"], indent=2), encoding="utf-8"
                )
                test_sh = task_dir / "tests" / "test.sh"
                test_sh.write_text(TEST_SH.format(build=build), encoding="utf-8")
                test_sh.chmod(0o755)
                slots.append(slot)
                manifest.append(
                    {
                        "slot_id": slot.slot_id,
                        "case_id": case["case_id"],
                        "app": case.get("app"),
                        "build": build,
                        "repeat": repeat,
                        "guidance": guidance,
                        "step_budget": budget,
                    }
                )

    save_slots(out_dir / "slots.json", slots)
    (out_dir / "manifest.json").write_text(
        json.dumps({"tasks": manifest}, indent=2), encoding="utf-8"
    )
    return {"tasks": len(manifest), "cases": len(cases), "out_dir": str(out_dir)}
