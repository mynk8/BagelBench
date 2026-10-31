#!/usr/bin/env python3
"""Create reproducible, parameterized AndroidWorld task instances.

This sampler freezes the upstream task name, generated parameters, natural-
language goal, seed, and AndroidWorld source version. It does not seed Android
state or apply mutations; those operations require a compatible AndroidWorld
checkout and a dedicated emulator adapter.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

CATALOG = (
    Path(__file__).resolve().parents[2] / "apps/research_ui/datasets/androidworld/case_catalog.json"
)


def normalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return normalize(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def androidworld_revision() -> str | None:
    try:
        import android_world
    except ImportError:
        return None
    root = Path(android_world.__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    try:
        return importlib.metadata.version("android_world")
    except importlib.metadata.PackageNotFoundError:
        return None


def get_task_types() -> dict[str, type]:
    try:
        from android_world import registry
    except ImportError as error:
        raise RuntimeError(
            "AndroidWorld is not installed. Clone google-research/android_world, "
            "install its requirements, and run this command in that environment."
        ) from error
    task_registry = registry.TaskRegistry()
    return task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY)


def generate(
    catalog: dict[str, Any], task_names: list[str], seed: int, repeats: int
) -> dict[str, Any]:
    task_types = get_task_types()
    definitions = {item["task_name"]: item for item in catalog["cases"]}
    missing = sorted(set(task_names) - definitions.keys())
    if missing:
        raise ValueError(f"Tasks are not in the selected catalog: {', '.join(missing)}")
    unregistered = sorted(name for name in task_names if name not in task_types)
    if unregistered:
        raise ValueError(
            f"Selected tasks are absent from this AndroidWorld revision: {', '.join(unregistered)}"
        )

    revision = androidworld_revision()
    instances = []
    for task_name in task_names:
        definition = definitions[task_name]
        for repeat in range(1, repeats + 1):
            case_seed = seed + repeat - 1
            random.seed(case_seed)
            try:
                import numpy as np

                np.random.seed(case_seed % (2**32))
            except ImportError:
                pass
            task_type = task_types[task_name]
            params = task_type.generate_random_params()
            task = task_type(params)
            normalized_params = normalize(params)
            identity = json.dumps(
                {
                    "task": task_name,
                    "seed": case_seed,
                    "params": normalized_params,
                    "revision": revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            case_hash = hashlib.sha256(identity.encode()).hexdigest()
            instances.append(
                {
                    "case_id": f"aw-{task_name}-{case_hash[:12]}",
                    "dataset": "android_world",
                    "dataset_revision": revision,
                    "task_name": task_name,
                    "app": definition["app"],
                    "state_kind": definition["state_kind"],
                    "seed": case_seed,
                    "repeat_index": repeat,
                    "goal": str(task.goal),
                    "params": normalized_params,
                    "oracle": {"method": "TaskEval.is_successful(env)", "expected_value": 1.0},
                    "mutation_candidates": definition["mutation_candidates"],
                    "mutation_status": "not_applied",
                    "visibility_review": "required_after_fault_injection",
                }
            )
    return {
        "schema_version": "artemis-androidworld-suite/v1",
        "catalog_version": catalog["schema_version"],
        "dataset_revision": revision,
        "root_seed": seed,
        "task_names": task_names,
        "repeat_count": repeats,
        "instances": instances,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tasks", help="Comma-separated selected task names; defaults to pilot tier."
    )
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--out", type=Path, help="Write canonical JSON to this path; stdout by default."
    )
    parser.add_argument(
        "--list", action="store_true", help="List selected tasks without requiring AndroidWorld."
    )
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if args.list:
        for case in catalog["cases"]:
            print(
                f"{case['tier']:>20}  {case['task_name']:<34} {case['app']} [{case['state_kind']}]"
            )
        return 0
    if args.repeats < 1 or args.repeats > 100:
        parser.error("--repeats must be between 1 and 100")
    tasks = (
        args.tasks.split(",")
        if args.tasks
        else [case["task_name"] for case in catalog["cases"] if case["tier"] == "pilot"]
    )
    try:
        suite = generate(catalog, tasks, args.seed, args.repeats)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    content = json.dumps(suite, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
