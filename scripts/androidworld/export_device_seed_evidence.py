#!/usr/bin/env python3
"""Export compact, source-linked facts from recorded AndroidWorld seed events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from qa_pilot import PROFILES


def export(traces_root: Path, output: Path) -> int:
    rows: list[dict] = []
    for path in sorted(traces_root.glob("*/ground_truth.jsonl")):
        trace_id = path.parent.name
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        pre = next(
            (
                record
                for record in records
                if record.get("phase") == "pre" and record.get("fixture") == "androidworld"
            ),
            None,
        )
        if pre is None or pre.get("target_satisfied") is None:
            continue
        task_name = pre.get("task_name")
        profile = PROFILES.get(task_name, {})
        post = next((record for record in reversed(records) if record.get("phase") == "post"), None)
        rows.append(
            {
                "trace_id": trace_id,
                "trial_id": pre.get("pilot_trial_id"),
                "pair_id": pre.get("pair_id"),
                "source_dataset": "Google Research AndroidWorld",
                "source_revision": pre.get("dataset_revision"),
                "task_template": task_name,
                "app": profile.get("app"),
                "seed": pre.get("seed"),
                "variant": pre.get("variant"),
                "mutation_operation": pre.get("operation"),
                "mutation_field": pre.get("field"),
                "oracle_version": pre.get("oracle_version"),
                "source_state_oracle_true": pre.get("target_satisfied"),
                "baseline_oracle_confirmed": pre.get("baseline_oracle_confirmed"),
                "fault_confirmed": pre.get("fault_confirmed"),
                "state_sha256": pre.get("state_sha256"),
                "screenshot_sha256": pre.get("screenshot_sha256"),
                "post_oracle_recorded": post is not None,
                "post_state_oracle_true": post.get("target_satisfied") if post else None,
                "discoverability_review": pre.get("visibility_status", "not_recorded"),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "trace_id",
        "trial_id",
        "pair_id",
        "source_dataset",
        "source_revision",
        "task_template",
        "app",
        "seed",
        "variant",
        "mutation_operation",
        "mutation_field",
        "oracle_version",
        "source_state_oracle_true",
        "baseline_oracle_confirmed",
        "fault_confirmed",
        "state_sha256",
        "screenshot_sha256",
        "post_oracle_recorded",
        "post_state_oracle_true",
        "discoverability_review",
    ]
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--traces-root", type=Path, default=Path(__file__).resolve().parents[2] / "traces"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(
        f"Exported {export(args.traces_root, args.out)} AndroidWorld fixture observations to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
