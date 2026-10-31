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

"""Append-only record of one benchmark run, written by the device server.

The record is the grader's only input besides the case's hidden signature, so it
is produced harness-side and never trusted from the agent:

- ``steps.jsonl``: one line per agent tool call -- step number, tool, arguments,
  outcome, and the screen the harness captured *after* the call (foreground
  activity, UI element list, screenshot file).
- ``verdict.json``: the agent's single final answer, written once.

Step numbers start at 1 and are returned to the agent with every tool result, so
``submit_verdict(flag_step=...)`` can only name a step the agent actually took.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STEPS_FILE = "steps.jsonl"
VERDICT_FILE = "verdict.json"
SCREENS_DIR = "screens"

VERDICTS = ("DEFECT", "NO_DEFECT", "INCONCLUSIVE")
OBSERVATION_TOOLS = frozenset({"observe_screen"})


@dataclass
class Screen:
    """What the harness saw on the device right after a step."""

    activity: str | None = None
    elements: list[dict[str, Any]] = field(default_factory=list)
    screenshot: str | None = None
    """Path relative to the run directory."""


@dataclass
class Step:
    step: int
    timestamp: float
    tool: str
    args: dict[str, Any]
    ok: bool
    message: str
    screen: Screen | None = None


class VerdictAlreadySubmitted(RuntimeError):
    """A run accepts exactly one final answer."""


class RunRecorder:
    """Writes one run's steps and verdict under ``run_dir``. Thread-safe."""

    def __init__(self, run_dir: Path | str):
        self.run_dir = Path(run_dir)
        (self.run_dir / SCREENS_DIR).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        existing = load_steps(self.run_dir)
        self._steps = len(existing)
        self._actions = sum(1 for s in existing if s.get("tool") not in OBSERVATION_TOOLS)

    @property
    def step_count(self) -> int:
        return self._steps

    @property
    def action_count(self) -> int:
        """Steps that acted on the device; observations are free."""
        return self._actions

    @property
    def verdict_submitted(self) -> bool:
        return (self.run_dir / VERDICT_FILE).is_file()

    def next_step(self) -> int:
        with self._lock:
            self._steps += 1
            return self._steps

    def screenshot_path(self, step: int) -> Path:
        return self.run_dir / SCREENS_DIR / f"step_{step:04d}.jpg"

    def record_step(self, step: Step) -> None:
        line = json.dumps(asdict(step), ensure_ascii=False, sort_keys=True)
        with self._lock, (self.run_dir / STEPS_FILE).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            if step.tool not in OBSERVATION_TOOLS:
                self._actions += 1

    def submit_verdict(self, verdict: str, flag_step: int | None, note: str = "") -> dict[str, Any]:
        """Stores the final answer; raises on a second submission or a bad flag step."""
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        if verdict == "DEFECT":
            if flag_step is None or not 1 <= int(flag_step) <= self._steps:
                raise ValueError(
                    f"DEFECT needs flag_step: a step you took (1..{self._steps})"
                    " whose screen shows the defect."
                )
            flag_step = int(flag_step)
        else:
            flag_step = None
        record = {
            "verdict": verdict,
            "flag_step": flag_step,
            "note": note,
            "steps_taken": self._steps,
            "timestamp": time.time(),
        }
        with self._lock:
            path = self.run_dir / VERDICT_FILE
            if path.exists():
                raise VerdictAlreadySubmitted("A verdict was already submitted for this run.")
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return record


def load_steps(run_dir: Path | str) -> list[dict[str, Any]]:
    path = Path(run_dir) / STEPS_FILE
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_verdict(run_dir: Path | str) -> dict[str, Any] | None:
    path = Path(run_dir) / VERDICT_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
