#!/usr/bin/env python3
"""Build a checksum-manifested Android QA evaluation bundle and zip."""

from __future__ import annotations

import argparse
import csv
import html
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "apps/research_ui/datasets/androidworld"
SCRIPTS = ROOT / "apps/research_ui/scripts"
AW_ROOT = Path("/home/lucky11/workspace/android_world")


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_bucket_summary(out: Path, pilot: dict, showcase: dict, device_seed_count: int) -> None:
    with (DATA / "evaluation_buckets_v1.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    counts = json.loads((DATA / "oracle_inventory/oracle_inventory_v1_summary.json").read_text())
    expanded = json.loads((out / "expanded/quality_report.json").read_text())
    (out / "README.md").write_text(
        "# Artemis Android QA evaluation dataset — PoC v1\n\n"
        f"The expanded reference set contains {expanded['pair_count']} matched pairs / {expanded['variant_count']} variants across nine QA buckets. All controls satisfy their offline predicate and all faults violate it. These are authored reference contracts derived from AndroidWorld values. See `expanded/README.md` for fixture requirements and `expanded/bucket_distribution.csv` for coverage.\n\n"
        f"This is a transparent proof-of-concept evaluation package. The source-backed showcase pool contains {showcase['counts']['instances']} matched pairs / {len(showcase['trials'])} task variants generated from the pinned AndroidWorld task parameter generators. A separate {pilot['counts']['instances']}-pair / {len(pilot['trials'])}-variant runtime pilot uses the same verifier and fixture path. The package also includes {device_seed_count} recorded AndroidWorld fixture setup observations with pre-run state-oracle results. Agent verdicts and screen-discoverability reviews are separate run artifacts.\n\n"
        "## Contents\n\n"
        "- `expanded/`: 600 full reference pairs, 1,200 OSWorld-shaped variant records, case/app/bucket/mutation CSVs, permission APK audit, and generation-loop quality reports.\n"
        "- `presentation/`: the presentation workbook when generated in the workspace.\n"
        "- `tasks.jsonl`: OSWorld-shaped task records, one per control/fault variant.\n"
        "- `planned_trials.csv`: 30-pair runtime pilot schedule (60 variants).\n"
        "- `showcase_tasks.jsonl`, `showcase_trials.csv` / `.jsonl`: expanded AndroidWorld-derived source pool.\n"
        "- `device_seed_observations.csv`: recorded emulator fixture setups and independent pre/post state-oracle reads; these are the actual fixture observations currently available.\n"
        "- `evaluation_buckets.csv`: QA classes, case patterns, independent verifier, source material, status, and admission evidence.\n"
        "- `verifier_contracts.json`: machine-readable verifier contracts and implementation status for all buckets.\n"
        "- `verifier_contracts.csv`: spreadsheet view of the verifier registry.\n"
        "- `oracle_tier_guide.csv`: read-level answer-key confidence methods and rules.\n"
        "- `OWNERSHIP.md`: domain boundaries and source-of-truth ownership across dataset, fixture, agent, review, scoring, orchestration, and UI.\n"
        "- `androidworld_oracles.csv` / `.jsonl`: source audit of every registered AndroidWorld task template.\n"
        "- `schemas/`: schemas for task records, run results, scorer observations, and verifier contracts; `run_results_template.csv` is the flat results template.\n"
        "- `evaluation_design.md`: benchmark unit, verifier pipeline, admission criteria, scoring, and release method.\n"
        "- `research_basis.md`: packaging patterns reviewed from AndroidWorld, OSWorld, and Terminal-Bench.\n"
        "- `RUNBOOK.md`: pilot execution, artifact handling, admission, and scoring instructions.\n"
        "- `visual/evaluation-map.html`: overview of the evaluation flow and bucket readiness.\n"
        "- `data-tables.html`: browser view of the CSV tables for quick inspection.\n"
        "- `source/`: canonical pilot manifest, selected source-task catalog, and upstream notice.\n\n"
        "## Counts and provenance\n\n"
        f"- Runtime pilot: {pilot['counts']['instances']} generated pair instances and {len(pilot['trials'])} scheduled variants.\n"
        f"- Showcase pool: {showcase['counts']['instances']} source-generated pairs and {len(showcase['trials'])} variants across three AndroidWorld app task templates.\n"
        f"- {device_seed_count} recorded emulator fixture setup observations, with correct-state and fault-state oracle reads.\n"
        f"- {counts['task_count']} upstream AndroidWorld task templates source-audited at `{counts['source_revision']}`.\n"
        "- Nine offline reference predicates; the record bucket has the existing SQLite device fixture adapter. Eight live fixture/capture adapters are still required.\n"
        "- AndroidWorld source license: Apache-2.0; preserve `THIRD_PARTY_NOTICES.md`.\n\n"
        "## Pair semantics\n\n"
        "Each pair shares the natural-language inspection instruction and frozen parameters. One variant begins with the criterion true; the other applies one declared mutation. The runtime exposes only `agent_view` and live device observations. Setup details, mutation, expected truth, and evaluator fields stay in the harness.\n\n"
        "## Regenerate\n\n"
        "From the Artemis repository root, run `python apps/research_ui/scripts/package_android_qa.py`. To regenerate the AndroidWorld source inventory, use the AndroidWorld environment: `python apps/research_ui/scripts/audit_androidworld_oracles.py --androidworld-root /path/to/android_world --out-dir apps/research_ui/datasets/androidworld/oracle_inventory`.\n\n"
        "See `DATASET_CARD.md` for scope and provenance. The showcase records are derived task specifications; device fixture observations and agent outcomes are separately identified. Do not report agent benchmark scores until runs are collected.\n",
        encoding="utf-8",
    )


def write_data_tables(out: Path) -> None:
    from html import escape

    registry = json.loads((out / "verifier_contracts.json").read_text(encoding="utf-8"))
    verifier_columns = [
        "verifier_id",
        "bucket_id",
        "status",
        "implementation",
        "generated_reference_pair_count",
        "reference_implementation",
        "task_templates",
        "predicate",
        "required_artifacts",
    ]
    with (out / "verifier_contracts.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=verifier_columns)
        writer.writeheader()
        for item in registry["verifiers"]:
            writer.writerow(
                {
                    "verifier_id": item["verifier_id"],
                    "bucket_id": item["bucket_id"],
                    "status": item["status"],
                    "implementation": item.get("implementation") or "",
                    "generated_reference_pair_count": item.get("generated_reference_pair_count", 0),
                    "reference_implementation": item.get("reference_implementation", ""),
                    "task_templates": json.dumps(
                        item.get("task_templates", []), ensure_ascii=False
                    ),
                    "predicate": json.dumps(item.get("predicate", []), ensure_ascii=False),
                    "required_artifacts": json.dumps(
                        item.get("required_artifacts", item.get("input_artifacts", [])),
                        ensure_ascii=False,
                    ),
                }
            )

    definitions = [
        (
            "buckets",
            "Evaluation buckets",
            "evaluation_buckets.csv",
            [
                "bucket_id",
                "question",
                "generated_reference_pairs",
                "independent_verifier",
                "androidworld_source_material",
                "status",
            ],
        ),
        (
            "coverage",
            "Bucket coverage",
            "expanded/bucket_distribution.csv",
            [
                "bucket",
                "matched_pairs",
                "variants",
                "source_apps",
                "app_mechanism_templates",
                "reference_predicate_separation",
            ],
        ),
        (
            "pairs",
            "Expanded pair catalog",
            "expanded/pair_catalog.csv",
            [
                "pair_id",
                "bucket",
                "app",
                "mechanism",
                "source_seed",
                "test_case",
                "reference_control_truth",
                "reference_fault_truth",
                "fixture_requirement",
            ],
        ),
        (
            "pilot",
            "Runtime pilot schedule",
            "planned_trials.csv",
            [
                "schedule_index",
                "trial_id",
                "family",
                "variant",
                "mutation_operation",
                "mutation_field",
                "source_state_status",
                "expected_fields",
            ],
        ),
        (
            "showcase",
            "Generated showcase cases",
            "showcase_trials.csv",
            [
                "schedule_index",
                "trial_id",
                "family",
                "variant",
                "upstream_task",
                "mutation_operation",
                "mutation_field",
                "source_state_status",
                "expected_fields",
            ],
        ),
        (
            "seedruns",
            "Recorded fixture setup observations",
            "device_seed_observations.csv",
            [
                "trace_id",
                "task_template",
                "app",
                "seed",
                "variant",
                "mutation_operation",
                "source_state_oracle_true",
                "baseline_oracle_confirmed",
                "fault_confirmed",
                "post_oracle_recorded",
                "discoverability_review",
            ],
        ),
        ("verifiers", "Verifier contracts", "verifier_contracts.csv", verifier_columns),
        (
            "tiers",
            "Oracle confidence tiers",
            "oracle_tier_guide.csv",
            ["bucket_id", "read_id", "tier", "method", "required_for", "notes"],
        ),
        (
            "oracles",
            "AndroidWorld oracle audit",
            "androidworld_oracles.csv",
            [
                "task_name",
                "task_template",
                "app_names",
                "oracle_family",
                "oracle_type",
                "evaluator_method",
                "qa_reuse_note",
            ],
        ),
    ]
    sections = []
    for index, (key, title, filename, columns) in enumerate(definitions):
        with (out / filename).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
        visible_columns = [
            column for column in columns if reader.fieldnames and column in reader.fieldnames
        ]
        head = "".join(
            f"<th>{escape(col.replace('_', ' ').title())}</th>" for col in visible_columns
        )
        body = "".join(
            "<tr>"
            + "".join(f"<td>{escape(row.get(col, '') or '')}</td>" for col in visible_columns)
            + "</tr>"
            for row in rows
        )
        sections.append(
            f'<section id="panel-{key}" role="tabpanel" aria-labelledby="tab-{key}"{(" hidden" if index else "")}>'
            f"<h2>{escape(title)} <small>{len(rows)} rows · source: {escape(filename)}</small></h2>"
            f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>'
        )
    row_counts = {}
    for key, _title, filename, _columns in definitions:
        with (out / filename).open(encoding="utf-8", newline="") as stream:
            row_counts[key] = sum(1 for _ in csv.DictReader(stream))
    tabs = "".join(
        f'<button class="tab" id="tab-{key}" role="tab" aria-controls="panel-{key}" aria-selected="{str(index == 0).lower()}" type="button">{escape(title)} · {row_counts[key]}</button>'
        for index, (key, title, _filename, _columns) in enumerate(definitions)
    )
    out.joinpath("data-tables.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Android QA dataset tables</title>'
        "<style>:root{color-scheme:light;--ink:#17211f;--muted:#63716d;--line:#dce4e1;--paper:#f4f7f5;--card:#fff;--green:#18785e}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 Inter,system-ui,sans-serif}main{max-width:1360px;margin:auto;padding:28px clamp(14px,3vw,36px)}h1{margin:0 0 5px;font-size:28px;letter-spacing:-.03em}p{margin:0 0 20px;color:var(--muted)}nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.tab{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;cursor:pointer}.tab[aria-selected=true]{background:var(--green);border-color:var(--green);color:white}h2{font-size:17px;margin:20px 0 10px}h2 small{font-size:12px;font-weight:400;color:var(--muted)}.table-wrap{overflow:auto;max-height:74vh;border:1px solid var(--line);border-radius:10px;background:var(--card)}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line);min-width:105px;max-width:480px;white-space:pre-wrap;overflow-wrap:anywhere}th{position:sticky;top:0;background:#edf3f0;z-index:1;font-weight:650}td:first-child,th:first-child{min-width:60px}tr:last-child td{border-bottom:0}a{color:var(--green)}</style></head><body><main>"
        "<h1>Evaluation dataset tables</h1><p>AndroidWorld-derived task specifications and recorded fixture observations. No agent outcomes are included.</p>"
        f'<nav role="tablist" aria-label="Dataset tables">{tabs}</nav>'
        + "".join(sections)
        + "<script>document.querySelectorAll('[role=tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[role=tab]').forEach(tab=>tab.setAttribute('aria-selected',String(tab===button)));document.querySelectorAll('[role=tabpanel]').forEach(panel=>panel.hidden=panel.id!==button.getAttribute('aria-controls'))}));</script>"
        + "</main></body></html>\n",
        encoding="utf-8",
    )


def package(destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    (destination / "schemas").mkdir()
    (destination / "source").mkdir()
    (destination / "scripts").mkdir()
    (destination / "visual").mkdir()
    shutil.copytree(DATA / "expanded_v1", destination / "expanded")

    # Refresh the OSWorld-shaped task export directly from the checksummed
    # canonical pilot manifest before copying it into the bundle.
    sys.path.insert(0, str(SCRIPTS))
    from export_osworld_profile import export

    export(DATA / "pilot_v1.json", destination / "tasks.jsonl")
    export(DATA / "pilot_showcase_v1.json", destination / "showcase_tasks.jsonl")
    from export_device_seed_evidence import export as export_device_seeds

    device_seed_count = export_device_seeds(
        ROOT / "traces", destination / "device_seed_observations.csv"
    )
    from export_pilot import export as export_trials

    temporary_export = destination / ".showcase_export"
    export_trials(DATA / "pilot_showcase_v1.json", temporary_export)
    shutil.move(str(temporary_export / "pilot_v1.csv"), str(destination / "showcase_trials.csv"))
    shutil.move(
        str(temporary_export / "pilot_v1.jsonl"), str(destination / "showcase_trials.jsonl")
    )
    shutil.rmtree(temporary_export)
    pilot = json.loads((DATA / "pilot_v1.json").read_text(encoding="utf-8"))
    showcase = json.loads((DATA / "pilot_showcase_v1.json").read_text(encoding="utf-8"))

    files = {
        DATA / "exports/pilot_v1.csv": destination / "planned_trials.csv",
        DATA / "evaluation_buckets_v1.csv": destination / "evaluation_buckets.csv",
        DATA / "pilot_showcase_v1.json": destination / "source/showcase_manifest.json",
        DATA / "device_seed_observations_v1.csv": destination / "device_seed_observations.csv",
        DATA / "oracle_tier_guide_v1.csv": destination / "oracle_tier_guide.csv",
        DATA / "verifier_contracts_v1.json": destination / "verifier_contracts.json",
        DATA / "OWNERSHIP.md": destination / "OWNERSHIP.md",
        DATA / "evaluation-design-v1.md": destination / "evaluation_design.md",
        DATA / "RUNBOOK.md": destination / "RUNBOOK.md",
        DATA / "research-basis.md": destination / "research_basis.md",
        DATA / "DATASET_CARD.md": destination / "DATASET_CARD.md",
        DATA / "run_results_template.csv": destination / "run_results_template.csv",
        DATA / "run_results_v1.schema.json": destination / "schemas/run_result.schema.json",
        DATA / "oracle_calibration_v1.schema.json": destination
        / "schemas/oracle_calibration.schema.json",
        DATA / "oracle_calibration_summary_v1.schema.json": destination
        / "schemas/oracle_calibration_summary.schema.json",
        DATA / "pilot_observation_v1.schema.json": destination
        / "schemas/pilot_observation.schema.json",
        DATA / "osworld_profile.schema.json": destination / "schemas/task.schema.json",
        DATA / "reference_pair_v1.schema.json": destination / "schemas/reference_pair.schema.json",
        DATA / "verifier_registry_v1.schema.json": destination
        / "schemas/verifier_registry.schema.json",
        DATA / "oracle_inventory/oracle_inventory_v1.csv": destination / "androidworld_oracles.csv",
        DATA / "oracle_inventory/oracle_inventory_v1.jsonl": destination
        / "androidworld_oracles.jsonl",
        DATA / "oracle_inventory/oracle_inventory_v1_summary.json": destination
        / "androidworld_oracles_summary.json",
        DATA / "oracle_inventory/README.md": destination / "oracle_inventory_notes.md",
        DATA / "pilot_v1.json": destination / "source/pilot_manifest.json",
        DATA / "case_catalog.json": destination / "source/androidworld_task_catalog.json",
        DATA / "families_v1.json": destination / "source/families.json",
        DATA / "evaluation-map.html": destination / "visual/evaluation-map.html",
        SCRIPTS / "export_osworld_profile.py": destination / "scripts/export_osworld_profile.py",
        SCRIPTS / "audit_androidworld_oracles.py": destination
        / "scripts/audit_androidworld_oracles.py",
        SCRIPTS / "qa_pilot.py": destination / "scripts/qa_pilot.py",
        SCRIPTS / "generate_qa_buckets.py": destination / "scripts/generate_qa_buckets.py",
        SCRIPTS / "androidworld_device.py": destination / "scripts/androidworld_device.py",
        SCRIPTS / "androidworld_grpc.py": destination / "scripts/androidworld_grpc.py",
        SCRIPTS / "androidworld_mutations.py": destination / "scripts/androidworld_mutations.py",
        SCRIPTS / "androidworld_suite.py": destination / "scripts/androidworld_suite.py",
        SCRIPTS / "export_pilot.py": destination / "scripts/export_pilot.py",
        SCRIPTS / "score_pilot.py": destination / "scripts/score_pilot.py",
        SCRIPTS / "replay_report.py": destination / "scripts/replay_report.py",
        SCRIPTS / "export_device_seed_evidence.py": destination
        / "scripts/export_device_seed_evidence.py",
        ROOT / "docs/android-qa-evaluation-method.md": destination
        / "reference/android-qa-evaluation-method.md",
        ROOT / "docs/independent-checks-research.md": destination
        / "reference/independent-checks-research.md",
    }
    for source, target in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    presentation = ROOT / "outputs/android_qa_data_poc_20261030/Artemis_QA_Data_PoC.xlsx"
    if presentation.is_file():
        (destination / "presentation").mkdir()
        shutil.copyfile(presentation, destination / "presentation/Artemis_QA_Data_PoC.xlsx")

    card = (DATA / "DATASET_CARD.md").read_text(encoding="utf-8")
    card = card.replace(
        "../../../../docs/android-qa-evaluation-method.md",
        "reference/android-qa-evaluation-method.md",
    )
    card = card.replace(
        "../../../../docs/independent-checks-research.md",
        "reference/independent-checks-research.md",
    )
    card = card.replace("../../../../docs/qa-pilot-protocol.md", "evaluation_design.md")
    (destination / "DATASET_CARD.md").write_text(card, encoding="utf-8")

    visual = (DATA / "evaluation-map.html").read_text(encoding="utf-8")
    visual = visual.replace('href="evaluation_buckets_v1.csv"', 'href="../evaluation_buckets.csv"')
    visual = visual.replace(
        'href="release_candidate_v1/planned_trials.csv"', 'href="../planned_trials.csv"'
    )
    visual = visual.replace(
        'href="release_candidate_v1/showcase_trials.csv"', 'href="../showcase_trials.csv"'
    )
    visual = visual.replace(
        'href="release_candidate_v1/device_seed_observations.csv"',
        'href="../device_seed_observations.csv"',
    )
    visual = visual.replace(
        'href="release_candidate_v1/verifier_contracts.csv"', 'href="../verifier_contracts.csv"'
    )
    visual = visual.replace(
        'href="release_candidate_v1/androidworld_oracles.csv"', 'href="../androidworld_oracles.csv"'
    )
    visual = visual.replace('href="release_candidate_v1/tasks.jsonl"', 'href="../tasks.jsonl"')
    visual = visual.replace('href="evaluation-design-v1.md"', 'href="../evaluation_design.md"')
    visual = visual.replace('href="expanded_v1/', 'href="../expanded/')
    (destination / "visual/evaluation-map.html").write_text(visual, encoding="utf-8")

    write_data_tables(destination)

    license_file = AW_ROOT / "LICENSE"
    (destination / "THIRD_PARTY_NOTICES.md").write_text(
        "Derived task templates and parameterized instances originate from Google Research AndroidWorld at revision `55ddaf5edc6f6c25673aed343907d5b9dca66f84`. AndroidWorld is distributed under Apache License 2.0; the full license text is in `source/ANDROIDWORLD_LICENSE`. Artemis-specific QA prompts, fault pairings, task envelope, and evaluation taxonomy are additions.\n",
        encoding="utf-8",
    )
    shutil.copyfile(license_file, destination / "source/ANDROIDWORLD_LICENSE")
    write_bucket_summary(destination, pilot, showcase, device_seed_count)

    files_for_manifest = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file() and path.name != "bundle_manifest.json"
    )
    manifest = {
        "bundle_id": "artemis_android_qa_eval_poc_v1",
        "status": "poc_source_generated_cases_with_fixture_observations",
        "format": "OSWorld-shaped JSONL tasks plus CSV data tables and Artemis verifier schema",
        "task_count": sum(1 for _ in (destination / "tasks.jsonl").open(encoding="utf-8")),
        "runtime_pilot_variant_count": len(pilot["trials"]),
        "showcase_pair_count": showcase["counts"]["instances"],
        "showcase_variant_count": len(showcase["trials"]),
        "expanded_reference_pair_count": json.loads(
            (destination / "expanded/quality_report.json").read_text()
        )["pair_count"],
        "expanded_reference_variant_count": json.loads(
            (destination / "expanded/quality_report.json").read_text()
        )["variant_count"],
        "recorded_fixture_observation_count": device_seed_count,
        "files": {str(path.relative_to(destination)): sha256(path) for path in files_for_manifest},
    }
    (destination / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    zip_path = destination.parent / "artemis_android_qa_eval_poc_v1.zip"
    if zip_path.exists():
        zip_path.unlink()
    root_name = "artemis_android_qa_eval_poc_v1"
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(item for item in destination.rglob("*") if item.is_file()):
            arcname = Path(root_name) / path.relative_to(destination)
            info = zipfile.ZipInfo(str(arcname), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DATA / "release_candidate_v1")
    args = parser.parse_args()
    result = package(args.out_dir)
    print(f"Wrote dataset folder {args.out_dir}")
    print(f"Wrote zip {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
