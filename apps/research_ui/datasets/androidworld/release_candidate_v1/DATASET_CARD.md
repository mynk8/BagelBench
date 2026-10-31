# Artemis Android QA evaluation PoC, v1

## Purpose

This proof of concept evaluates whether an Android agent can inspect app state and return a supported `PASS`, `FAIL`, or `INCONCLUSIVE` verdict. It derives valid task parameters and state-oracle contracts from Google Research AndroidWorld, then defines matched happy-path and fault-path inspection cases. AndroidWorld is the explicit source; Artemis contributes the testing prompts, controlled mutations, pair structure, and evaluation harness. This is not a general Android bug corpus or a drop-in OSWorld runner plugin.

## Expanded reference set

The expanded dataset has **600 matched pairs / 1,200 variants** across all nine QA buckets, derived from the same three AndroidWorld source tasks. It contains 147 app × bucket × mutation templates. Each reference control evaluates true and each reference fault evaluates false under the supplied offline predicate. UI bounds, transition keys, lifecycle snapshots, and feedback examples are authored reference artifacts; the declared live fixture adapters must supply actual observations before agent benchmarking.

| Bucket | Pairs | Variants |
|---|---:|---:|
| record integrity | 150 | 300 |
| persistence lifecycle | 60 | 120 |
| action effect side effects | 60 | 120 |
| navigation transitions | 60 | 120 |
| control reachability | 60 | 120 |
| visual layout | 60 | 120 |
| presentation consistency | 60 | 120 |
| permission state | 30 | 60 |
| success signal truth | 60 | 120 |

App totals are Calendar 220, Expense 190, and Broccoli 190 pairs. The 30 permission pairs use Calendar only, after checking the cached APK manifest. The original 150 record pairs are included in the 600; do not add their counts again.

Each pair has one primary QA bucket and is counted once. Protected-state checks can appear as secondary invariants in several buckets. The set reuses 150 unique source parameter sets; its 600 pairs and 147 app/bucket/mutation templates are separate coverage measures.

## Original record pilot and observed fixtures

| Item | Count/status |
|---|---:|
| AndroidWorld task templates | 3 (`ExpenseAddSingle`, `SimpleCalendarAddOneEvent`, `RecipeAddSingleRecipe`) |
| Showcase matched pairs | 150 (50 generated per source task template) |
| Showcase variants | 150 control + 150 fault |
| Runtime pilot schedule | 30 pairs / 60 variants |
| Recorded fixture setup observations | 5 observations from existing traces |
| Unique recorded app-state hashes | 3 |
| Apps | 3 (Pro Expense, Simple Calendar Pro, Broccoli) |
| Oracle | Exact target-field predicate plus preservation of preexisting rows |

The 150 fault paths have a fixed, reproducible operator mix:

| Fault operator | Matched pairs |
|---|---:|
| Change one value | 80 |
| Delete the target record | 30 |
| Truncate text | 30 |
| Shift calendar date | 10 |
| **Total** | **150** |

The 150 showcase pairs are generated from valid parameters emitted by AndroidWorld's pinned task generators. Each control state satisfies the source task's target-state predicate; each fault variant applies one declared deterministic mutation to a target field and is expected to violate the exact-field oracle. These are reproducible **case definitions**, not 150 separate device executions. `device_seed_observations_v1.csv` records five actual setup observations from existing emulator traces: three control observations and two fault observations; fault mutations and pre-run oracle results are recorded. These traces do not establish screen discoverability or agent verdicts. No agent outcomes are included in this package.

The generated fault variants include target deletion, value change, date shift, or text truncation. Each pair shares its prompt and generated source parameters. Variant and oracle labels are evaluator metadata and must not be placed in actor or Checker context.

## Relationship to AndroidWorld and OSWorld

AndroidWorld supplies the source task templates, valid generated parameters, app setup patterns, and task state evaluators. We derive the correct and faulty paths from those states and use exact field checks as the verifier. Artemis owns the derived QA scenario, fault declaration, execution record, and scoring. The dataset is derived from AndroidWorld **state/task data**, not from a claim that AndroidWorld itself includes these QA faults. Navigation traces are recorded by Artemis during runs and need separately authored expected-transition annotations.

The JSONL uses the recognizable OSWorld task envelope: `task_id`, `instruction`, `source`, `config`, `evaluator`, and `related_apps`. `artemis_qa` carries the paired-verdict fields. It is an interchange profile, not directly executable by OSWorld: environment setup, AndroidWorld seeding, hidden oracle access, and scoring need the Artemis adapters.

## File map

- `expanded_v1/` — full 600-pair reference catalog, reference artifacts, distributions, iteration log, quality report, and permission manifest audit.
- `pilot_showcase_v1.json` — expanded source-derived showcase pool (150 pairs / 300 variants).
- `pilot_v1.json` — canonical 30-pair runtime pilot schedule.
- `device_seed_observations_v1.csv` — actual fixture setup observations currently present in local traces.
- `case_catalog.json` — selected AndroidWorld source templates and mutation candidates.
- `families_v1.json` — QA family taxonomy with current coverage status and source candidates.
- `verifier_contracts_v1.json` — machine-readable contracts and implementation status for all nine buckets; all buckets have an offline reference predicate; the record bucket also has the existing SQLite device fixture adapter.
- `RUNBOOK.md` — execution, human review, scoring, and admission instructions for the current pilot.
- `oracle_inventory/` — static source audit of all 116 registered AndroidWorld task templates, evaluator implementations, and oracle categories.
- `osworld_profile.schema.json` — JSON Schema for exported OSWorld-style records.
- `exports/osworld_android_qa_v1.jsonl` — one OSWorld-style task record per scheduled variant.
- `exports/pilot_v1.csv` and `exports/pilot_v1.jsonl` — compact analysis exports.
- `reference/android-qa-evaluation-method.md` — verifier design, case admission, scoring, and research basis.
- `reference/independent-checks-research.md` — oracle inventory and AndroidWorld source-task mapping.

Regenerate the OSWorld-style profile without calling a model or device:

```sh
python apps/research_ui/scripts/export_osworld_profile.py \
  apps/research_ui/datasets/androidworld/pilot_v1.json \
  --out apps/research_ui/datasets/androidworld/exports/osworld_android_qa_v1.jsonl
```

## Case admission and scoring

A scheduled case is eligible only after the harness confirms reset/setup, correct control truth, fault truth, protected-state invariants, discoverability in the recorded screen/tree, and valid pre/post oracle reads. A setup or oracle failure is an infrastructure exclusion, not an agent `INCONCLUSIVE`.

The expected verdict is `PASS` for control and `FAIL` for a confirmed fault. Score a false PASS only when the independent pre-run oracle establishes the fault and the agent returns PASS. Preserve `INCONCLUSIVE` as abstention. Report false PASS, false FAIL, inconclusive, decisive coverage, paired correctness (control PASS and fault FAIL), protected-state changes, and excluded infrastructure runs separately.

For evidence about misleading success, record app feedback exposure separately from durable state. A screenshot or accessibility tree may establish that a toast was shown; SQLite/provider/file state establishes whether the write persisted. The expanded reference set contains 60 success-signal pair definitions; a live app hook or patched build still has to enact the declared fault and exposure.

## Taxonomy and limits

`families_v1.json` maps nine useful QA families to independent oracles and candidate AndroidWorld workflows. The source audit finds 116 executable `is_successful` evaluators: 109 state/API-backed patterns and 7 UI/activity-state patterns. That demonstrates broad deterministic *outcome-check* infrastructure, not that these tasks are already QA cases or that they cover real bug prevalence. All nine buckets have generated reference pairs and offline predicates. Record integrity has the current SQLite device adapter. Other domains still require their declared live fixture and capture paths:

- AndroidWorld's state evaluators can ground record contents, action effects, and system settings.
- Its normal workflows can seed navigation-path candidates, but they do not provide controlled Back/cancel/navigation defects.
- Its screen-variation wrapper supplies device profiles, not known overlap/clipping defects.
- Permission-state checks can use Android package and AppOps queries; account and membership scenarios are out of scope for this PoC.
- False-success needs an app hook or patched APK that separates the success signal from the durable write.

Do not claim a percentage of real app flows from this task count. Report template count, admitted case count, app-flow coverage, bug-symptom coverage, and oracle coverage as separate quantities. The related research and case-construction methods are summarized with primary-source links in `docs/android-qa-evaluation-method.md` and `docs/independent-checks-research.md`; see especially the Android functional bug dataset, MDroid+ fault operators, Stoat/DroidBot transition models, DDLDroid lifecycle faults, Nighthawk visual defect checks, AndroidWorld, and OSWorld.

## Provenance and license

Source task parameters were generated from Google Research AndroidWorld at revision `55ddaf5edc6f6c25673aed343907d5b9dca66f84`. AndroidWorld is Apache-2.0. Retain attribution and the upstream license when redistributing derived task parameters. Artemis-specific prompts, pair IDs, and schema are project additions. The output contains no user data or measured model traces.

## Answer-key confidence

The verifier registry assigns confidence at the read level. A case inherits its weakest required read tier: A for independent deterministic state, B for code-verified UI evidence, C when perception or human judgment is needed, and X when a conflict remains unresolved after adjudication. X cases are excluded and counted. The package defines the tier protocol, but tier accuracy, reviewer Cohen's κ, and error bounds require a sampled human calibration study and are not claimed as measured results. Agent-reported confidence is stored separately from answer-key confidence.

For the success-signal study, capture transient toast events through accessibility or instrumentation, or use a persistent Snackbar. Record whether the signal reached an observation supplied to the agent. Report missed exposures, and compare false PASS only when exposure is established.

## What the PoC can claim

The task source and revision are explicit, the generated source parameters are valid outputs of the pinned AndroidWorld task generators, and each pair has a declared state predicate and mutation path. Five fixture setup observations are included as direct evidence that the adapter can produce and pre-oracle-read both correct and fault states on the emulator. They represent two unique paired scenarios plus one repeated control setup; they are not the full 150-pair pool. The current package has no agent verdict outcomes and no completed human screen-discoverability review. Keep those as separate claims and fields. For benchmark results, execute the desired cases, retain pre/post oracle reads and app/device build identifiers, assign read tiers, and review that each test criterion is discoverable in the UI.
