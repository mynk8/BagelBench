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

"""Model-free grading of benchmark runs (docs/benchmark-task-recipe.md §0.6).

Standard library only: the Harbor exporter copies this file into each task's
``tests/`` directory, where it runs inside the verifier container.

A *run* is one agent attempt on one build (``faulty`` or ``correct``) and is
labelled from its recorded final answer and the screen the harness recorded at
the flagged step. A *case* passes a repeat when its faulty run is a ``catch``
and its correct run is a ``correct_clear``.

Signature format (hidden from the agent)::

    {
      "screen": {"activity": "org.tasks/.MainActivity",
                 "anchors": [{"resource_id": "org.tasks:id/toolbar"}]},
      "faulty_state": [{"match": {"text": "Quarterly report"}, "present": false}],
      "known_issues": [{"screen": {...}, "faulty_state": [...], "id": "KI-1"}]
    }

``screen.activity`` and every anchor must match the flagged screen; every
``faulty_state`` item must hold there. A ``match`` is a dict of element fields
(``text``, ``resource_id``, ``class``) compared exactly; ``text_contains`` matches
a substring. ``present`` says whether a matching element must be on screen.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FAULTY = "faulty"
CORRECT = "correct"

CATCH = "catch"
WRONG_CATCH = "wrong_catch"
MISS = "miss"
FALSE_ALARM = "false_alarm"
CORRECT_CLEAR = "correct_clear"
ABSTAIN = "abstain"
NO_ANSWER = "no_answer"
KNOWN_ISSUE = "known_issue"
"""A flag that matches a listed pre-existing defect: neither credit nor penalty."""

RIGHT = {CATCH, CORRECT_CLEAR}


def _element_matches(element: dict[str, Any], match: dict[str, Any]) -> bool:
    for key, expected in match.items():
        if key == "text_contains":
            if str(expected) not in str(element.get("text") or ""):
                return False
        elif element.get(key) != expected:
            return False
    return True


def screen_matches(screen: dict[str, Any] | None, signature: dict[str, Any]) -> bool:
    """True when ``screen`` (a recorded step screen) satisfies ``signature``."""
    if not screen:
        return False
    elements = screen.get("elements") or []
    expected_screen = signature.get("screen") or {}
    activity = expected_screen.get("activity")
    if activity and screen.get("activity") != activity:
        return False
    for anchor in expected_screen.get("anchors") or []:
        if not any(_element_matches(e, anchor) for e in elements):
            return False
    for condition in signature.get("faulty_state") or []:
        present = any(_element_matches(e, condition.get("match") or {}) for e in elements)
        if present != bool(condition.get("present", True)):
            return False
    return True


def _screen_at(steps: list[dict[str, Any]], step_number: int) -> dict[str, Any] | None:
    for step in steps:
        if step.get("step") == step_number:
            return step.get("screen")
    return None


def label_run(
    build: str,
    steps: list[dict[str, Any]],
    verdict: dict[str, Any] | None,
    signature: dict[str, Any],
) -> str:
    """One run's outcome label."""
    if not verdict or verdict.get("verdict") not in ("DEFECT", "NO_DEFECT", "INCONCLUSIVE"):
        return NO_ANSWER
    answer = verdict["verdict"]
    if answer == "INCONCLUSIVE":
        return ABSTAIN
    if answer == "NO_DEFECT":
        return MISS if build == FAULTY else CORRECT_CLEAR
    flag_step = verdict.get("flag_step")
    taken = {s.get("step") for s in steps}
    if not isinstance(flag_step, int) or flag_step not in taken:
        return NO_ANSWER
    screen = _screen_at(steps, flag_step)
    if any(screen_matches(screen, issue) for issue in signature.get("known_issues") or []):
        return KNOWN_ISSUE
    if build == CORRECT:
        return FALSE_ALARM
    return CATCH if screen_matches(screen, signature) else WRONG_CATCH


def reward_for(label: str) -> float:
    return 1.0 if label in RIGHT else 0.0


def load_record(record_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Reads a run record: a directory (steps.jsonl, verdict.json) or a JSON export."""
    if record_path.is_dir():
        steps_file = record_path / "steps.jsonl"
        steps = (
            [
                json.loads(line)
                for line in steps_file.read_text(encoding="utf-8").splitlines()
                if line
            ]
            if steps_file.is_file()
            else []
        )
        verdict_file = record_path / "verdict.json"
        verdict = (
            json.loads(verdict_file.read_text(encoding="utf-8")) if verdict_file.is_file() else None
        )
        return steps, verdict
    data = json.loads(record_path.read_text(encoding="utf-8"))
    return data.get("steps") or [], data.get("verdict")


# --- Aggregate scoring ---------------------------------------------------------------


def case_scores(runs: list[dict[str, Any]]) -> dict[str, float]:
    """Mean pass over repeats per case.

    ``runs`` items: ``{"case_id", "app", "repeat", "build", "label"}``. A repeat
    passes only when both of its builds were graded right.
    """
    by_case: dict[str, dict[int, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    for run in runs:
        by_case[run["case_id"]][int(run["repeat"])][run["build"]] = run["label"]
    scores = {}
    for case_id, repeats in by_case.items():
        passes = [
            pair.get(FAULTY) == CATCH and pair.get(CORRECT) == CORRECT_CLEAR
            for pair in repeats.values()
        ]
        scores[case_id] = sum(passes) / len(passes)
    return scores


def benchmark_score(
    runs: list[dict[str, Any]], *, resamples: int = 2000, seed: int = 0
) -> dict[str, Any]:
    """App-weighted mean case score with an app-then-case bootstrap 95% interval."""
    scores = case_scores(runs)
    app_of = {run["case_id"]: run["app"] for run in runs}
    by_app: dict[str, list[float]] = defaultdict(list)
    for case_id, score in scores.items():
        by_app[app_of[case_id]].append(score)
    if not by_app:
        return {"score": None, "ci95": None, "apps": 0, "cases": 0}

    def app_weighted(groups: list[list[float]]) -> float:
        return sum(sum(g) / len(g) for g in groups) / len(groups)

    groups = list(by_app.values())
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        sampled = [rng.choice(groups) for _ in groups]
        draws.append(app_weighted([[rng.choice(g) for _ in g] for g in sampled]))
    draws.sort()
    labels = [run["label"] for run in runs]
    faulty = [run["label"] for run in runs if run["build"] == FAULTY]
    correct = [run["label"] for run in runs if run["build"] == CORRECT]
    return {
        "score": app_weighted(groups),
        "ci95": [draws[int(0.025 * (resamples - 1))], draws[int(0.975 * (resamples - 1))]],
        "apps": len(groups),
        "cases": len(scores),
        "detection_rate": faulty.count(CATCH) / len(faulty) if faulty else None,
        "false_alarm_rate": correct.count(FALSE_ALARM) / len(correct) if correct else None,
        "abstain_rate": {
            FAULTY: faulty.count(ABSTAIN) / len(faulty) if faulty else None,
            CORRECT: correct.count(ABSTAIN) / len(correct) if correct else None,
        },
        "labels": {label: labels.count(label) for label in sorted(set(labels))},
    }


def main(argv: list[str] | None = None) -> int:
    """Grade one run and write a Harbor-style reward file."""
    parser = argparse.ArgumentParser(description="Grade one benchmark run without a model.")
    parser.add_argument("--record", required=True, type=Path, help="Run directory or JSON export.")
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--build", required=True, choices=(FAULTY, CORRECT))
    parser.add_argument("--out", required=True, type=Path, help="reward.json to write.")
    args = parser.parse_args(argv)

    steps, verdict = load_record(args.record)
    signature = json.loads(args.signature.read_text(encoding="utf-8"))
    label = label_run(args.build, steps, verdict, signature)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"reward": reward_for(label), "label": label, "build": args.build}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"label": label, "reward": reward_for(label)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
