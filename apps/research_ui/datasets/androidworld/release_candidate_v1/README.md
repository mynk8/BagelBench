# Artemis Android QA evaluation dataset — PoC v1

The expanded reference set contains 600 matched pairs / 1200 variants across nine QA buckets. All controls satisfy their offline predicate and all faults violate it. These are authored reference contracts derived from AndroidWorld values. See `expanded/README.md` for fixture requirements and `expanded/bucket_distribution.csv` for coverage.

This is a transparent proof-of-concept evaluation package. The source-backed showcase pool contains 150 matched pairs / 300 task variants generated from the pinned AndroidWorld task parameter generators. A separate 30-pair / 60-variant runtime pilot uses the same verifier and fixture path. The package also includes 5 recorded AndroidWorld fixture setup observations with pre-run state-oracle results. Agent verdicts and screen-discoverability reviews are separate run artifacts.

## Contents

- `expanded/`: 600 full reference pairs, 1,200 OSWorld-shaped variant records, case/app/bucket/mutation CSVs, permission APK audit, and generation-loop quality reports.
- `presentation/`: the presentation workbook when generated in the workspace.
- `tasks.jsonl`: OSWorld-shaped task records, one per control/fault variant.
- `planned_trials.csv`: 30-pair runtime pilot schedule (60 variants).
- `showcase_tasks.jsonl`, `showcase_trials.csv` / `.jsonl`: expanded AndroidWorld-derived source pool.
- `device_seed_observations.csv`: recorded emulator fixture setups and independent pre/post state-oracle reads; these are the actual fixture observations currently available.
- `evaluation_buckets.csv`: QA classes, case patterns, independent verifier, source material, status, and admission evidence.
- `verifier_contracts.json`: machine-readable verifier contracts and implementation status for all buckets.
- `verifier_contracts.csv`: spreadsheet view of the verifier registry.
- `oracle_tier_guide.csv`: read-level answer-key confidence methods and rules.
- `OWNERSHIP.md`: domain boundaries and source-of-truth ownership across dataset, fixture, agent, review, scoring, orchestration, and UI.
- `androidworld_oracles.csv` / `.jsonl`: source audit of every registered AndroidWorld task template.
- `schemas/`: schemas for task records, run results, scorer observations, and verifier contracts; `run_results_template.csv` is the flat results template.
- `evaluation_design.md`: benchmark unit, verifier pipeline, admission criteria, scoring, and release method.
- `research_basis.md`: packaging patterns reviewed from AndroidWorld, OSWorld, and Terminal-Bench.
- `RUNBOOK.md`: pilot execution, artifact handling, admission, and scoring instructions.
- `visual/evaluation-map.html`: overview of the evaluation flow and bucket readiness.
- `data-tables.html`: browser view of the CSV tables for quick inspection.
- `source/`: canonical pilot manifest, selected source-task catalog, and upstream notice.

## Counts and provenance

- Runtime pilot: 30 generated pair instances and 60 scheduled variants.
- Showcase pool: 150 source-generated pairs and 300 variants across three AndroidWorld app task templates.
- 5 recorded emulator fixture setup observations, with correct-state and fault-state oracle reads.
- 116 upstream AndroidWorld task templates source-audited at `55ddaf5edc6f6c25673aed343907d5b9dca66f84`.
- Nine offline reference predicates; the record bucket has the existing SQLite device fixture adapter. Eight live fixture/capture adapters are still required.
- AndroidWorld source license: Apache-2.0; preserve `THIRD_PARTY_NOTICES.md`.

## Pair semantics

Each pair shares the natural-language inspection instruction and frozen parameters. One variant begins with the criterion true; the other applies one declared mutation. The runtime exposes only `agent_view` and live device observations. Setup details, mutation, expected truth, and evaluator fields stay in the harness.

## Regenerate

From the Artemis repository root, run `python apps/research_ui/scripts/package_android_qa.py`. To regenerate the AndroidWorld source inventory, use the AndroidWorld environment: `python apps/research_ui/scripts/audit_androidworld_oracles.py --androidworld-root /path/to/android_world --out-dir apps/research_ui/datasets/androidworld/oracle_inventory`.

See `DATASET_CARD.md` for scope and provenance. The showcase records are derived task specifications; device fixture observations and agent outcomes are separately identified. Do not report agent benchmark scores until runs are collected.
