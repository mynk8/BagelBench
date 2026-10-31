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

"""Run the Flash reference agent over an exported benchmark.

The reference agent gets what a Harbor agent gets -- the task's ``instruction.md``
and the bench tool surface -- and its runs are graded by the same grader into the
same ``<results>/<slot>/verifier/reward.json`` layout, so ``artemis bench score``
reads reference and Harbor results the same way. The model under test is the
``operator`` node in ``artemis.jsonc``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from artemis.bench.flash import APP_PACKAGE_ENV, RUN_DIR_ENV, STEP_BUDGET_ENV
from artemis.bench.grading import label_run, load_record, reward_for
from artemis.bench.server import load_slots


def run_reference(
    export_dir: Path,
    serial: str,
    runs_dir: Path,
    results_dir: Path,
    *,
    only: set[str] | None = None,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    """Runs every (or each selected) exported slot once, then grades it."""
    tasks = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))["tasks"]
    slots = load_slots(export_dir / "slots.json")
    labels: dict[str, str] = {}
    for task in tasks:
        slot_id = task["slot_id"]
        if only and slot_id not in only:
            continue
        reward_file = results_dir / slot_id / "verifier" / "reward.json"
        if reward_file.is_file():
            continue  # already graded; rerun by deleting its results directory
        slot = slots[slot_id]
        run_dir = runs_dir / slot_id
        if run_dir.exists():
            raise RuntimeError(f"{run_dir} already holds a run; remove it to rerun the slot.")
        for argv in slot.setup:
            subprocess.run(argv, check=True)

        env = {
            **os.environ,
            RUN_DIR_ENV: str(run_dir),
            STEP_BUDGET_ENV: str(slot.step_budget or ""),
            APP_PACKAGE_ENV: slot.app_package or "",
        }
        instruction = (export_dir / "tasks" / slot_id / "instruction.md").read_text(
            encoding="utf-8"
        )
        cmd = [
            sys.executable,
            "-m",
            "artemis.main",
            "run",
            instruction,
            "--device-serial",
            serial,
            "--standalone",
            "--test-name",
            f"bench-{slot_id}",
        ]
        try:
            subprocess.run(cmd, env=env, timeout=timeout_sec, check=False)
        except subprocess.TimeoutExpired:
            pass  # graded as whatever the record holds; usually no answer

        steps, verdict = load_record(run_dir) if run_dir.exists() else ([], None)
        signature = json.loads(
            (export_dir / "tasks" / slot_id / "tests" / "signature.json").read_text(
                encoding="utf-8"
            )
        )
        label = label_run(slot.build, steps, verdict, signature)
        reward_file.parent.mkdir(parents=True, exist_ok=True)
        reward_file.write_text(
            json.dumps(
                {"reward": reward_for(label), "label": label, "build": slot.build}, indent=2
            ),
            encoding="utf-8",
        )
        labels[slot_id] = label
    return {"graded": len(labels), "labels": labels}
