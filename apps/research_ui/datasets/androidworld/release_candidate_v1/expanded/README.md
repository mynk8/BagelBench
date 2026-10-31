# Android QA reference case set

600 matched pairs / 1200 variants across 9 QA buckets and 3 apps. AndroidWorld supplies 150 frozen record parameter sets; Artemis derives the QA contracts, lifecycle/transition examples, UI/reference artifacts, and mutations. There are 147 distinct app × bucket × mutation templates; parameter variations are not independent app workflows.

Every reference control evaluates true and every reference fault evaluates false under `generate_qa_buckets.py::verify`. `quality_report.json` and `generation_iterations.jsonl` record the generation/inspection loop. Run `python apps/research_ui/scripts/generate_qa_buckets.py` from the repository to regenerate. The generated data is deterministic; no model calls are made.

`pairs.jsonl` contains both full reference artifacts and exact contracts. `tasks.jsonl` has the OSWorld-shaped variant envelope. `pair_catalog.csv` is one row per pair; the distribution CSVs show bucket, app, and mechanism coverage. `permission_manifest_audit.json` records the actual Calendar APK permission declarations and hash.

Reference artifacts are authored examples. UI rectangles, screen fingerprints, feedback timestamps, and before/after effects in this set are not captures from running the apps. The existing SQLite adapter supports record seeding; the other domains require the named fixture hooks, locators, or patched builds before live execution. Keep these generated reference-pair counts separate from observed emulator fixture reads and agent verdicts. Case answer-key tiers are assigned from actual required reads at execution, and human calibration remains a separate study.

Offline replay from the release folder: `python scripts/generate_qa_buckets.py --replay-dir expanded`. This recomputes each predicate, contract ID, and artifact hash without a device or model call.

Coverage targets were set before the loop: 60 pairs in each of seven new multiapp buckets (3 apps × 5 mechanisms × 4 applicable source examples), 30 Calendar permission pairs (3 manifest-declared permission groups × 2 states × 5 lifecycle contexts), plus the existing 150 record pairs. New multiapp cases require at least two source distractor rows so wrong-target and collateral mutations are distinct. Expense and Broccoli have no dangerous runtime permission in the cached manifests, so they get no permission cases. Accounts are excluded.

Source: Google Research AndroidWorld at 55ddaf5edc6f6c25673aed343907d5b9dca66f84, Apache-2.0. The source parameters and upstream task identity are retained on every pair.
