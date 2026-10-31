# Run the Android QA pilot

## Scope

This v1 is a **record-integrity diagnostic PoC**, not a complete mobile QA benchmark. The showcase contains 150 matched control/fault pairs (300 variants) generated from valid parameters emitted by three pinned AndroidWorld task templates. A separate runtime schedule contains 30 pairs / 60 variants. Five actual fixture setup observations from existing emulator traces are exported separately; they record pre-run state-oracle evidence for correct and fault states. The remaining eight QA buckets are verifier designs without case suites; see `verifier_contracts_v1.json`.

## Before a run

Use the Artemis research UI and a dedicated AndroidWorld emulator. The Artemis backend launches the isolated AndroidWorld adapter using the pinned AndroidWorld revision and its Python environment. Do not pass a complete JSONL task record to the agent. Pass only `agent_view` and live device observations; `config`, `evaluator`, mutation details, and ground truth are scorer-only.

In the experiment composer, choose **Frozen pilot · 60 trials**, select the target emulator and model/condition, then start the batch. The batch runner serializes trials on that device, resets and seeds the chosen control/fault state before each trial, records a pre-run oracle read, launches the agent with the frozen natural-language inspection task, and records a post-run oracle read. Human discoverability review remains required before scoring.

The `record_integrity.sqlite_exact_preserve.v1` predicate is implemented in `scripts/qa_pilot.py::strict_oracle` and applied to device state by `scripts/androidworld_device.py`. It removes exact pre-existing rows from the post-run state, then requires exactly one target match per expected record across every required field, with no unmatched rows. Fault setup is rejected unless the mutation changes the predicate's truth value.

## Answer-key confidence and review

For each run, store every required oracle read with its method, artifact reference, and tier from `oracle_tier_guide.csv`. Assign the case tier as the weakest required read tier (A strongest, then B, then C). A read conflict that remains after adjudication receives X; exclude and count it. Agent-reported `agent_confidence` is a separate 0–1 value and does not set the answer-key tier.

Before publishing model rates, draw a random sample within each tier. Two reviewers independently label case truth without seeing the agent verdict. Report Cohen's κ from their initial labels, adjudicate disagreements, and report verifier accuracy (correct / reviewed) per tier. Use A–B cases for headline agent metrics; report C separately with measured accuracy and a false-PASS sensitivity interval computed by changing oracle labels in the worst direction up to the observed error allowance. Do not fill these metrics with expected or assumed values.

For success-message experiments, capture transient toasts with an accessibility event or instrumentation log, or replace the transient toast with a persistent Snackbar in the patched build. Track whether the signal was present in an observation delivered to the agent. Report the exposure miss rate and score the signal effect only for runs with established exposure.

## Score recorded runs

Download the run observations from the Artemis research endpoint `/api/research/pilot/observations?judge=agent` as `observations.jsonl`, then run from the Artemis repository root:

```sh
python apps/research_ui/scripts/score_pilot.py \
  apps/research_ui/datasets/androidworld/pilot_v1.json \
  observations.jsonl \
  --out scores.json \
  --csv scores.csv
```

The scorer excludes setup/oracle errors, unreviewed discoverability, criterion mismatch, and protected-state changes. It reports false PASS only when the pre-run oracle established a faulty state and the agent said PASS; it reports false FAIL only when the pre-run oracle established a correct state and the agent said FAIL. INCONCLUSIVE is reported separately. Use paired results and report exclusions; do not treat missing or invalid trials as agent failures.

The observation format returned by that endpoint is described by `schemas/pilot_observation.schema.json`. `schemas/run_result.schema.json` is the richer per-run archival record; it is not the scorer's input format.

## Rebuild package files

From the Artemis repository root:

```sh
python apps/research_ui/scripts/package_android_qa.py
```

The exporter, device adapter, verifier/scorer, schemas, source-derived task records, recorded fixture observations, bucket registry, upstream AndroidWorld source inventory, checksums, and ZIP are included in the PoC bundle. AndroidWorld and an emulator are required to generate fresh states or run trials; the exported suite is not a drop-in OSWorld runner plugin.

## Admission status

The current records are planned tasks until each seed is run and has valid pre/post oracle reads, confirmed mutation, screenshot/tree visibility review, reproducible reset, and no protected-state changes. The release contains no measured agent scores. Do not present the other eight verifier designs as covered benchmark buckets.
