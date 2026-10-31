#!/usr/bin/env python3
"""Export frozen pilot specifications to CSV and JSONL. No device/model calls."""

import argparse
import csv
import json
from pathlib import Path
from qa_pilot import load_manifest


def export(manifest_path, destination):
    manifest = load_manifest(manifest_path)
    instances = {item["pair_id"]: item for item in manifest["instances"]}
    rows = []
    for index, trial in enumerate(manifest["trials"], 1):
        instance = instances[trial["pair_id"]]
        target = instance["params"]["row_objects"][0]
        rows.append(
            {
                "schedule_index": index,
                "suite_id": manifest["suite_id"],
                **trial,
                "upstream_task": instance["task_name"],
                "seed": instance["seed"],
                "test_prompt": instance["test_prompt"],
                "expected_oracle_correct": trial["variant"] == "control",
                "mutation_operation": instance["operation"]
                if trial["variant"] == "fault"
                else "none",
                "mutation_field": instance["field"] if trial["variant"] == "fault" else None,
                "expected_fields": {field: target[field] for field in instance["oracle_fields"]},
                "noise_record_count": len(instance["params"].get("noise_row_objects", [])),
                "oracle_version": manifest["oracle_version"],
                "upstream_revision": manifest["dataset_revision"],
                "source_state_status": "generated_by_pinned_androidworld_task_parameterizer",
                "fixture_execution_status": "see_separate_device_seed_observations; not_implied_for_each_generated_row",
                "discoverability_review_status": "separate_human_review_record",
                "agent_result_status": "not_collected",
                "parameters": instance["params"],
            }
        )
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "pilot_v1.csv"
    jsonl_path = destination / "pilot_v1.jsonl"
    columns = [key for key in rows[0] if key != "parameters"]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(row[key], ensure_ascii=False, sort_keys=True)
                    if isinstance(row[key], dict)
                    else row[key]
                    for key in columns
                }
            )
    jsonl_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return csv_path, jsonl_path, len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    csv_path, jsonl_path, count = export(args.manifest, args.out_dir)
    print(f"{count} trial specifications exported to {csv_path} and {jsonl_path}")
