#!/usr/bin/env python3
"""Inventory deterministic evaluator implementations in a pinned AndroidWorld checkout.

This is a static corpus audit. It imports task classes but does not initialize an
emulator, run an agent, or call task evaluators against device state.
"""
from __future__ import annotations

import argparse
import collections
import csv
import inspect
import json
import sys
from pathlib import Path
from typing import Any


def classify(task_class: type, evaluator_file: str) -> tuple[str, str, str]:
    path = evaluator_file.replace("\\", "/")
    module = task_class.__module__
    if path.endswith("common_validators/sqlite_validators.py"):
        return "structured_data", "sqlite_row_predicate", "generic reusable state oracle; add QA mutation and protected-state checks"
    if path.endswith("information_retrieval/information_retrieval.py"):
        return "state_retrieval", "seeded_state_answer_match", "deterministic answer matcher over a seeded state; adapt to inspect task and keep target hidden"
    if path.endswith("common_validators/file_validators.py") or module.endswith(("single.markor", "single.files")):
        return "file_state", "filesystem_predicate", "generic or app-specific filesystem oracle; add paired QA mutations"
    if path.endswith("common_validators/contacts_validators.py"):
        return "provider_state", "contacts_provider_predicate", "provider oracle; isolate synthetic contacts and add fault pair"
    if path.endswith("common_validators/sms_validators.py"):
        return "provider_state", "sms_provider_predicate", "provider oracle; restrict to emulator-local messages and add fault pair"
    if module.endswith("single.sms"):
        return "provider_state", "sms_provider_predicate", "SMS provider oracle; restrict to emulator-local messages and add fault pair"
    if module.endswith("single.contacts"):
        return "ui_state", "accessibility_tree_and_activity_predicate", "draft-presence UI oracle; pair with Contacts provider query to verify saved state"
    if path.endswith("single/system.py"):
        return "system_state", "adb_system_or_launcher_predicate", "direct system/launcher oracle; define target and protected settings"
    if path.endswith("single/clock.py"):
        return "ui_state", "activity_and_accessibility_tree_predicate", "deterministic UI-tree predicate; add geometry/visibility review for QA claims"
    if path.endswith("single/browser.py"):
        return "ui_state", "activity_and_success_text_sentinel", "deterministic but narrow UI sentinel; needs independent page/task-state oracle for broader claims"
    if "/composite/" in path:
        return "composite_state", "composed_task_predicates", "deterministic component evaluators; split into individual assertions and test collateral state"
    if module.endswith("single.osmand"):
        return "app_state", "favorite_file_or_app_state_predicate", "task-specific stored-state oracle; inspect exact predicate before reuse"
    if module.endswith(("single.audio_recorder", "single.camera", "single.simple_gallery_pro")):
        return "file_state", "media_artifact_predicate", "filesystem/media artifact predicate; does not verify rendered media correctness"
    if module.endswith(("single.retro_music", "single.vlc")):
        return "app_state", "media_app_state_predicate", "task-specific media state oracle; inspect exact predicate and side effects"
    if module.endswith("single.simple_draw_pro"):
        return "app_state", "drawing_artifact_predicate", "task-specific artifact oracle; visual correctness needs a separate rubric"
    return "app_state", "task_specific_predicate", "manual source review required before QA reuse"


def build_inventory(androidworld_root: Path) -> list[dict[str, Any]]:
    sys.path.insert(0, str(androidworld_root))
    from android_world import registry

    metadata_path = androidworld_root / "android_world" / "task_metadata.json"
    metadata = {row["task_name"]: row for row in json.loads(metadata_path.read_text(encoding="utf-8"))}
    task_registry = registry.TaskRegistry()
    classes = task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY)
    rows = []
    def project_relative(path: str) -> str:
        resolved = Path(path).resolve()
        try:
            return str(resolved.relative_to(androidworld_root.resolve()))
        except ValueError:
            return "generated_class_without_source_file"

    for name, task_class in sorted(classes.items()):
        evaluator = task_class.is_successful
        evaluator_file = str(Path(inspect.getsourcefile(evaluator) or "").resolve())
        source = str(Path(inspect.getsourcefile(task_class) or evaluator_file).resolve())
        if not Path(source).resolve().is_relative_to(androidworld_root.resolve()):
            source = evaluator_file
        family, oracle_type, reuse_note = classify(task_class, evaluator_file)
        meta = metadata.get(name, {})
        rows.append({
            "task_name": name,
            "task_template": meta.get("task_template", getattr(task_class, "template", "")),
            "difficulty": meta.get("difficulty"),
            "tags": meta.get("tags", []),
            "optimal_steps": meta.get("optimal_steps"),
            "app_names": list(getattr(task_class, "app_names", ()) or ()),
            "source_file": project_relative(source),
            "evaluator_method": evaluator.__qualname__,
            "evaluator_file": project_relative(evaluator_file),
            "oracle_family": family,
            "oracle_type": oracle_type,
            "deterministic_evaluator_present": True,
            "qa_reuse_note": reuse_note,
            "status": "source_audited_not_device_executed",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--androidworld-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.androidworld_root.resolve()
    rows = build_inventory(root)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "oracle_inventory_v1.jsonl"
    jsonl.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    csv_path = out / "oracle_inventory_v1.csv"
    columns = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    counts = collections.Counter(row["oracle_family"] for row in rows)
    summary = {
        "schema_version": "artemis-androidworld-oracle-audit/v1",
        "source_revision": "55ddaf5edc6f6c25673aed343907d5b9dca66f84",
        "scope": "registered ANDROID_WORLD_FAMILY task classes and their is_successful implementation source",
        "method": "static introspection; no emulator/evaluator execution",
        "task_count": len(rows),
        "all_have_deterministic_evaluator_method": all(row["deterministic_evaluator_present"] for row in rows),
        "oracle_family_counts": dict(sorted(counts.items())),
        "task_records": jsonl.name,
    }
    (out / "oracle_inventory_v1_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for family, count in sorted(counts.items()):
        print(f"{family}: {count}")
    print(f"total: {len(rows)} tasks; wrote {jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
