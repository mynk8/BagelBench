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

"""Android contract for native Harbor task directories.

Harbor owns task.toml, instruction.md, environment/ and tests/. Public Android
settings extend metadata.android. Private build, pairing, setup and validation
records live in tests/android.toml. There is no intermediate case format.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib
from typing import Any
from urllib.parse import urlsplit

from bagel.benchmark.slots import Slot

GUIDANCE_LEVELS = ("directed", "feature_hint", "open")
PUBLIC_FIELDS = {"version", "app", "app_package", "guidance", "action_budget"}
PRIVATE_FIELDS = {"version", "case_id", "build", "repeat", "validated", "setup", "provenance"}
TOKEN_REFERENCE = "${BAGEL_BENCH_VERIFIER_TOKEN}"


@dataclass(frozen=True)
class AndroidTask:
    """One native Harbor task and its host-only Android settings."""

    path: Path
    slot: Slot
    app: str
    guidance: str
    repeat: int
    instruction: str

    def score_entry(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot.slot_id,
            "task_name": self.path.name,
            "case_id": self.slot.case_id,
            "app": self.app,
            "build": self.slot.build,
            "repeat": self.repeat,
            "guidance": self.guidance,
            "step_budget": self.slot.step_budget,
        }


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def load_task(path: Path) -> AndroidTask:
    """Read Android extensions from an existing native Harbor task."""
    path = path.resolve()
    config = _read(path / "task.toml")
    public = config.get("metadata", {}).get("android", {})
    private = _read(path / "tests" / "android.toml")
    if public.get("version") != 1 or private.get("version") != 1:
        raise ValueError(f"{path.name}: Android contract version must be 1.")
    if set(public) - PUBLIC_FIELDS:
        raise ValueError(
            f"{path.name}: unsupported public Android metadata; keep oracle data in tests/."
        )
    if set(private) - PRIVATE_FIELDS:
        raise ValueError(f"{path.name}: unsupported private Android field.")
    if private.get("validated") is not True:
        raise ValueError(f"{path.name}: the build pair has not been validated.")
    app = public.get("app")
    package = public.get("app_package")
    guidance = public.get("guidance")
    budget = public.get("action_budget")
    if not isinstance(app, str) or not app or not isinstance(package, str) or not package:
        raise ValueError(f"{path.name}: app and app_package are required.")
    if guidance not in GUIDANCE_LEVELS or type(budget) is not int or budget < 1:
        raise ValueError(f"{path.name}: guidance and a positive action_budget are required.")
    case_id, build = private.get("case_id"), private.get("build")
    repeat = private.get("repeat", 1)
    if not isinstance(case_id, str) or not case_id or build not in ("correct", "faulty"):
        raise ValueError(f"{path.name}: private case_id and build are required.")
    if type(repeat) is not int or repeat < 1:
        raise ValueError(f"{path.name}: repeat must be a positive integer.")
    setup = private.get("setup", [])
    if not isinstance(setup, list) or any(
        not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv)
        for argv in setup
    ):
        raise ValueError(f"{path.name}: setup must contain argv lists.")
    servers = config.get("environment", {}).get("mcp_servers", [])
    android = [server for server in servers if server.get("name") == "android"]
    if len(android) != 1 or android[0].get("transport") != "streamable-http":
        raise ValueError(f"{path.name}: declare one android streamable-http MCP server.")
    endpoint = urlsplit(android[0].get("url", ""))
    match = re.fullmatch(r"/t/([A-Za-z0-9_-]+)/mcp", endpoint.path)
    if (
        endpoint.scheme not in ("http", "https")
        or not endpoint.hostname
        or not match
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError(f"{path.name}: Android MCP URL must end in /t/<opaque-id>/mcp.")
    slot_id = match.group(1)
    verifier = config.get("verifier", {})
    if verifier.get("environment_mode") != "separate":
        raise ValueError(f"{path.name}: use Harbor's separate verifier environment.")
    verifier_env = verifier.get("env", {})
    reward_url = endpoint._replace(path=f"/t/{slot_id}/reward").geturl()
    if verifier_env.get("BENCH_REWARD_URL") != reward_url:
        raise ValueError(f"{path.name}: verifier reward URL must address the same Android task.")
    if verifier_env.get("BENCH_VERIFIER_TOKEN") != TOKEN_REFERENCE:
        raise ValueError(f"{path.name}: verifier token must use its environment reference.")
    signature = json.loads((path / "tests" / "signature.json").read_text(encoding="utf-8"))
    if not isinstance(signature, dict) or not signature:
        raise ValueError(f"{path.name}: a nonempty hidden signature is required.")
    instruction = (path / "instruction.md").read_text(encoding="utf-8")
    if not instruction.strip() or not (path / "tests" / "test.sh").is_file():
        raise ValueError(f"{path.name}: instruction.md and tests/test.sh are required.")
    return AndroidTask(
        path=path,
        slot=Slot(
            slot_id=slot_id,
            case_id=case_id,
            build=build,
            app_package=package,
            setup=setup,
            step_budget=budget,
            setup_cwd=str(path),
            signature=signature,
        ),
        app=app,
        guidance=guidance,
        repeat=repeat,
        instruction=instruction,
    )


def load_tasks(root: Path) -> list[AndroidTask]:
    """Read a native Harbor dataset and validate its correct/faulty pairs."""
    configs = (
        [root / "task.toml"] if (root / "task.toml").is_file() else sorted(root.glob("*/task.toml"))
    )
    if not configs:
        raise ValueError("No native Harbor tasks found.")
    tasks = [load_task(config.parent) for config in configs]
    if len({task.guidance for task in tasks}) != 1:
        raise ValueError("Run and score one guidance level per dataset.")
    trial_names = [task.path.name[:32].rstrip("_-") for task in tasks]
    if len(set(trial_names)) != len(trial_names):
        raise ValueError("Task directory names must remain distinct in Harbor trial names.")
    slots = [task.slot.slot_id for task in tasks]
    if len(set(slots)) != len(slots):
        raise ValueError("Every task needs a distinct Android MCP slot.")
    groups: dict[tuple[str, str, int], list[AndroidTask]] = defaultdict(list)
    for task in tasks:
        groups[(task.slot.case_id, task.guidance, task.repeat)].append(task)
    for pair in groups.values():
        if len(pair) != 2 or {task.slot.build for task in pair} != {"correct", "faulty"}:
            raise ValueError("Each case/guidance/repeat needs one correct and one faulty task.")
        a, b = pair
        if (a.instruction, a.app, a.slot.app_package, a.slot.step_budget, a.slot.signature) != (
            b.instruction,
            b.app,
            b.slot.app_package,
            b.slot.step_budget,
            b.slot.signature,
        ):
            raise ValueError(
                "Paired tasks must share their instruction, app, budget and signature."
            )
    return tasks
