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

"""Join per-trial rewards back to cases and compute the benchmark score."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bagel.benchmark.grading import NO_ANSWER, benchmark_score


def collect_runs(tasks: list[dict[str, Any]], results_dir: Path) -> list[dict[str, Any]]:
    """Finds each native task's ``reward.json`` under ``results_dir``.

    A reward file belongs to the slot whose id appears in its path (Harbor names
    trial directories after the task). A task with no reward file counts as
    ``no_answer``: a missing trial is never silently dropped.
    """
    by_slot = {task["slot_id"]: task for task in tasks}
    labels: dict[str, str] = {}
    for reward_file in Path(results_dir).rglob("reward.json"):
        slot_id = next((part for part in reward_file.parts if part in by_slot), None)
        if slot_id is None:
            slot_id = next(
                (
                    slot
                    for slot, task in by_slot.items()
                    if any(
                        part.startswith(task["task_name"][:32].rstrip("_-") + "__")
                        for part in reward_file.parts
                    )
                ),
                None,
            )
        if slot_id is None:
            continue
        if slot_id in labels:
            raise ValueError(
                "Multiple rewards for one scheduled task; use one Harbor attempt per task."
            )
        try:
            labels[slot_id] = json.loads(reward_file.read_text(encoding="utf-8"))["label"]
        except (ValueError, KeyError):
            labels[slot_id] = NO_ANSWER
    return [
        {
            **task,
            "label": labels.get(task["slot_id"], NO_ANSWER),
            "graded": task["slot_id"] in labels,
        }
        for task in tasks
    ]


def score_results(tasks: list[dict[str, Any]], results_dir: Path) -> dict[str, Any]:
    runs = collect_runs(tasks, results_dir)
    report = benchmark_score(runs)
    report["missing_trials"] = sum(1 for run in runs if not run["graded"])
    guidance = {str(run["guidance"]) for run in runs if run.get("guidance")}
    report["guidance_level"] = guidance.pop() if len(guidance) == 1 else sorted(guidance)
    return report
