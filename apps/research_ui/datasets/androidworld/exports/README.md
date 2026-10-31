# Android QA verdict pilot specifications

This folder contains generated test specifications, not measured agent results.

- `pilot_v1.csv`: 60 rows, one planned trial per row. Suitable for Excel, Sheets, or browsing. `expected_fields` is a JSON object inside one CSV cell.
- `pilot_v1.jsonl`: the same 60 trials, including complete upstream task parameters, one JSON object per line.
- `../pilot_v1.json`: canonical versioned manifest containing 30 instances and their 60 scheduled variants.
- `osworld_android_qa_v1.jsonl`: the same 60 scheduled variants in an OSWorld-style task envelope. `agent_view` is the only portion intended for the actor/Checker; setup mutation and evaluator truth are orchestrator-only. This is an interchange profile, not an OSWorld-runner plugin.
- `../DATASET_CARD.md`: dataset purpose, counts, admission rules, status, and limits.
- `../families_v1.json`: QA family taxonomy separating current pilot coverage from proposed families.
- `../oracle_inventory/`: reproducible source audit of all 116 AndroidWorld task evaluator patterns; static audit only, not device results.
- `../osworld_profile.schema.json`: JSON Schema for the OSWorld-style records.
- `../../../../../docs/qa-pilot-protocol.md`: task definitions, admission rules, scoring formulas, and limitations.

There are three task families: calendar records, expenses, and recipes. Every instance has a correct-state control and a fault variant, with identical prompts. `expected_oracle_correct` is the intended fixture label. It is not an observed device result. All rows explicitly mark device validation as pending and agent results as uncollected. These statuses describe this export; later runs require a separately versioned results artifact.

Derived from Google Research AndroidWorld, commit `55ddaf5edc6f6c25673aed343907d5b9dca66f84`, using its parameter generators. Upstream: https://github.com/google-research/android_world (Apache License 2.0). Cite and retain upstream attribution when distributing derived material. The surrounding Artemis repository also includes its license and source notices.

Regenerate from the canonical manifest without model or device calls:

```sh
python apps/research_ui/scripts/export_pilot.py \
  apps/research_ui/datasets/androidworld/pilot_v1.json \
  --out-dir apps/research_ui/datasets/androidworld/exports
```

Regenerate the OSWorld-style task profile:

```sh
python apps/research_ui/scripts/export_osworld_profile.py \
  apps/research_ui/datasets/androidworld/pilot_v1.json \
  --out apps/research_ui/datasets/androidworld/exports/osworld_android_qa_v1.jsonl
```
