#!/usr/bin/env python3
"""Export the frozen Android QA pilot using an OSWorld-style task envelope.

This is an interchange format, not a drop-in OSWorld runner task: AndroidWorld
owns Android setup/evaluation and the Artemis fields carry QA pairing metadata.
No emulator or model calls are made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from qa_pilot import PROFILES, load_manifest

VERIFIER_BY_FAMILY = {
    "calendar.record_integrity": "record_integrity.sqlite_exact_preserve.v1",
    "expense.record_integrity": "record_integrity.sqlite_exact_preserve.v1",
    "recipe.record_integrity": "record_integrity.sqlite_exact_preserve.v1",
}


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export(manifest_path: Path, out_path: Path) -> int:
    manifest = load_manifest(manifest_path)
    instances = {item["pair_id"]: item for item in manifest["instances"]}
    rows = []
    for trial in manifest["trials"]:
        instance = instances[trial["pair_id"]]
        target = instance["params"]["row_objects"][0]
        expected_fields = {key: target[key] for key in instance["oracle_fields"]}
        is_fault = trial["variant"] == "fault"
        mutation = (
            {"operator": instance["operation"], "field": instance["field"]}
            if is_fault
            else {"operator": "identity", "field": None}
        )
        task_id = trial["trial_id"]
        rows.append({
            # Core fields follow OSWorld's JSON task convention: id,
            # instruction, source, related_apps, setup config array, evaluator.
            "id": task_id,
            "instruction": instance["test_prompt"],
            "agent_view": {
                "instruction": instance["test_prompt"],
                "platform": "android",
                "app": PROFILES[instance["task_name"]]["app"],
            },
            "source": f"Google Research AndroidWorld {instance['dataset_revision']} / {instance['task_name']}; Apache-2.0",
            "config": [
                {
                    "type": "androidworld_initialize_task",
                    "parameters": {
                        "platform": "android",
                        "app": PROFILES[instance["task_name"]]["app"],
                        "task_name": instance["task_name"],
                        "revision": instance["dataset_revision"],
                        "seed": instance["seed"],
                        "parameters": instance["params"],
                        "reset_policy": "reinitialize_from_frozen_parameters_before_each_trial",
                    },
                },
                {
                    "type": "apply_qa_variant",
                    "parameters": {
                        "variant": trial["variant"],
                        "mutation": mutation,
                        "device_profile": "must_be_pinned_at_execution",
                    },
                },
            ],
            "evaluator": {
                "func": "artemis_android_qa_paired_verdict",
                "result": {
                    "type": "androidworld_state_oracle",
                    "read_before_agent": True,
                    "read_after_agent": True,
                    "capture_agent_verdict": True,
                },
                "expected": {
                    "criterion_true_before_agent": not is_fault,
                    "agent_verdict": "PASS" if not is_fault else "FAIL",
                },
                "options": {
                    "verifier_id": VERIFIER_BY_FAMILY[instance["family"]],
                    "oracle_kind": "sqlite_exact_target_and_protected_rows",
                    "oracle_version": manifest["oracle_version"],
                    "target_fields": expected_fields,
                    "protected_state": "all_preexisting_rows_must_be_preserved",
                    "mutation_must_be_confirmed": is_fault,
                    "visibility_review_required": True,
                    "visibility_review_status": "pending",
                    "score_labels": ["PASS", "FAIL", "INCONCLUSIVE"],
                    "status": "source_state_generated_runtime_fixture_evidence_recorded_separately",
                },
            },
            "related_apps": [PROFILES[instance["task_name"]]["app"]],
            "artemis_qa": {
                "schema_version": "artemis-osworld-profile/v1",
                "suite_id": manifest["suite_id"],
                "case_id": instance["pair_id"],
                "pair_id": trial["pair_id"],
                "variant": trial["variant"],
                "family": instance["family"],
                "verifier_id": VERIFIER_BY_FAMILY[instance["family"]],
                "expected_agent_verdict": "PASS" if not is_fault else "FAIL",
                "agent_result_status": "not_collected",
                "device_validation_status": "source_generated_runtime_fixture_evidence_recorded_separately",
                "pair_control_and_fault_share_instruction": True,
                "ground_truth_hidden_from_actor_and_checker": True,
            },
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.manifest, args.out)} OSWorld-style Android QA task records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
