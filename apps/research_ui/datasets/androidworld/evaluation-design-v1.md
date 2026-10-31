# Evaluation design and release format

Status: proof-of-concept package. The expanded reference set has 600 pairs / 1,200 variants across nine buckets, with 147 app × bucket × mutation templates and executable offline predicates. The source-derived record subset is included in that count. UI and transition artifacts are authored references; live adapters remain required for eight domains. The showcase has 150 generated matched pairs / 300 task variants from three pinned AndroidWorld task parameterizers. The separate runtime pilot schedule has 30 pairs / 60 variants. Five actual fixture setup observations are included; no agent verdicts are included.

## What we learned from existing benchmark formats

**OSWorld** makes each task a self-contained JSON record with an identifier, natural-language instruction, source, related applications, setup configuration, and evaluator. The evaluator fetches the observed result, compares it with an expected result, and can apply post-run setup before grading. We follow that packaging boundary: one instruction, versioned setup, and an execution-based evaluator per variant. We use an AndroidWorld setup adapter and an Artemis verifier function, so the records are recognizable in shape but are not executable by the OSWorld runner unchanged. [OSWorld task format](https://timothyxxx.github.io/OSWorld/user_guides/task_example_explanation.html), [OSWorld benchmark paper](https://arxiv.org/abs/2404.07972)

**AndroidWorld** gives us the environment side: 116 parameterized tasks across 20 apps, with task initialization, success checking, and teardown. Its reward comes from device state. We reuse task parameters, setup conventions, and state oracle patterns, then change the evaluated question from “did the agent make the target state?” to “did the tester correctly diagnose a known state?” [AndroidWorld paper](https://arxiv.org/abs/2405.14573), [pinned source revision](https://github.com/google-research/android_world/tree/55ddaf5edc6f6c25673aed343907d5b9dca66f84)

**Terminal-Bench** treats a task as an instruction, isolated environment, outcome tests, and a reference solution. Its tests check final state rather than the agent's command sequence. The benchmark reports human review of task correctness and uses oracle / no-op validation to catch broken or trivial tasks. We adopt the useful QA equivalents: test the actual app truth, show that a no-op tester fails to detect fault cases, ensure a correct control is accepted, and review instruction/evaluator agreement. [Terminal-Bench paper](https://arxiv.org/abs/2601.11868), [task contribution and verifier guidance](https://github.com/harbor-framework/terminal-bench/blob/main/CONTRIBUTING.md)

## Benchmark unit

The atomic case is a **matched pair**, not a single prompt:

1. Generate a known app state from a frozen AndroidWorld task and parameter seed.
2. Make a control that satisfies the criterion.
3. Clone that state and apply one declared fault to create the fault variant.
4. Give both variants the same natural-language inspection instruction and allowed observation/action tools.
5. Keep variant, mutation, expected outcome, and oracle data outside the actor and Checker view.
6. Before the agent starts, verify that control truth is true and fault truth is false. Reject the pair if either precondition fails.
7. Review whether the criterion is discoverable in the app. Retain a screenshot and accessibility tree; use human review where UI semantics are ambiguous.
8. After the agent finishes, re-read the oracle and protected state. A changed target is reported as an observed side effect; it does not by itself establish intent.
9. Score agent verdict against pre-run truth. Do not count setup, emulator, provider, or oracle failures as agent `INCONCLUSIVE`.

An app feedback signal is a separate exposure measurement. A screenshot can prove “Saved” appeared; SQLite/provider/file state proves whether the save persisted. The two are paired, not substituted for each other.

## Answer-key confidence and calibration

Assign a tier to every read that is required to decide the case truth. The case inherits the weakest required tier, ordered A → B → C. If required reads disagree and adjudication does not resolve the conflict, assign X, exclude the case from scored results, and report the exclusion count. Store the read-level tier, method, and artifact reference so the case tier can be recomputed from its evidence.

| Tier | Evidence method | Examples |
|---|---|---|
| A | Deterministic state read independent of the agent's observations | SQLite/file/provider query, permission or app-op state, persisted value after process restart |
| B | Deterministic UI predicate verified against the original app | Accessibility node and bounds, instrumented Snackbar/toast event, rendered text compared with stored value using a frozen normalizer |
| C | Perceptual method, thresholds, or model interpretation required | Pixel-diff severity, OCR-only reading, OmniParser output, human judgment of harmful overlap |
| X | Required evidence conflicts and adjudication cannot settle it | Unresolved oracle conflict; exclude and count |

The tier describes the answer-key evidence, not a subjective probability. Measure its empirical error instead. Randomly sample cases within each tier; two reviewers independently label the ground truth without seeing the model verdict. Report Cohen's κ for their initial labels. Adjudicate disagreements with a third review or documented discussion, then report the verifier's agreement with the settled labels as correct / reviewed for every tier. Keep unresolved cases in X. Do not publish tier-accuracy percentages before this review has been collected.

Headline model results use answer-key tiers A and B. Report full results for A, B, and C separately beside each tier's measured accuracy. For sensitivity analysis, flip oracle labels in the direction that most increases and decreases false-PASS rate, up to each tier's measured error allowance, then recompute the rate and its denominator. Report the resulting interval. If tier C can change a conclusion, optionally apply a documented misclassification correction (for example Rogan–Gladen) using measured sensitivity and specificity; do not substitute assumed accuracy.

Keep **answer-key confidence** separate from **agent confidence**. The agent may return a numeric confidence in [0, 1] with each PASS/FAIL/INCONCLUSIVE verdict. Preserve the raw value and evaluate calibration only when enough labeled outcomes exist; confident false PASS rate is a direct descriptive metric. Agent confidence must never affect the ground-truth tier.

### Current read-tier mapping

Assign tiers per case from the reads it actually needs. Persisted-state and permission queries are A. Accessibility-tree predicates and instrumented UI events are B when their locators and predicates are deterministic on the pinned build. OCR, pixel thresholds, and human judgments of visual harm are C. A visual-layout case that requires a perceptual judgment is therefore C even when its geometry read is B. A success-signal case is B when an instrumented event or persistent Snackbar confirms exposure, and C when screenshot/OCR interpretation is needed to establish what the agent saw. Record signal exposure and whether it appeared in an observation delivered to the agent; score the toast-effect comparison only when exposure is established, and report the miss rate separately.

### Accessibility and geometry evidence already captured by Artemis

Artemis already captures a screenshot and Android UI hierarchy during perception and persists the parsed hierarchy and OCR beside the screenshot in its local Data Engine. The parsed hierarchy is the agent-facing version: the Android driver filters nodes and may clip bounds for screen interaction. That representation is useful for action and text checks, but it can erase evidence needed to score clipping or off-screen layout faults. Therefore each recorded step now also preserves the raw Android hierarchy XML in step metadata as `raw_accessibility_hierarchy_xml`. This is tied to the exact step rather than only the screenshot hash, since identical screenshots may recur while the hierarchy changes.

Use the raw hierarchy as the deterministic source for node attributes and screen-coordinate rectangles. Use the saved screenshot for visual confirmation. OCR is a fallback for visible text absent from the tree; OmniParser is optional for screenshot-only icons or custom-drawn controls. Neither OCR nor OmniParser should replace the app-state oracle for correctness. A geometry check reports element bounds, viewport clipping fraction, and pairwise overlap; a reviewer labels whether measured overlap actually blocks a target. The agent can continue using the existing filtered tree. Experiments may give the Checker tree, screenshot, or both while the evaluator retains all captured modalities.

## Case record and release layout

The JSONL task record follows OSWorld's core field convention:

```json
{
  "id": "<trial id>",
  "instruction": "<natural-language inspection test>",
  "source": "AndroidWorld revision and source task",
  "related_apps": ["<app>"],
  "config": [
    {"type": "androidworld_initialize_task", "parameters": {"task_name": "...", "seed": 0}},
    {"type": "apply_qa_variant", "parameters": {"variant": "control|fault", "mutation": {}}}
  ],
  "evaluator": {
    "func": "artemis_android_qa_paired_verdict",
    "result": {"type": "androidworld_state_oracle", "read_before_agent": true, "read_after_agent": true},
    "expected": {"criterion_true_before_agent": true, "agent_verdict": "PASS"},
    "options": {"oracle_version": "...", "target_fields": {}, "protected_state": "..."}
  },
  "artemis_qa": {"pair_id": "...", "variant": "control", "family": "..."}
}
```

`config` and `evaluator` are orchestrator-only. The runtime passes `agent_view` plus live device observations to the agent. The expected label must not leak through prompts, logs, environment variables, file paths, UI state, or checker inputs.

Release contents in `artemis_android_qa_eval_poc_v1/`:

- `tasks.jsonl`: one task per scheduled variant in OSWorld-style shape.
- `planned_trials.csv`: filterable runtime pilot schedule of 60 task variants.
- `showcase_tasks.jsonl` and `showcase_trials.csv` / `.jsonl`: 150 matched source-derived pairs / 300 task variants.
- `device_seed_observations.csv`: five recorded fixture setup observations from existing emulator traces.
- `evaluation_buckets.csv`: family purpose, case patterns, verifier, source material, and current status.
- `verifier_contracts.json` / `.csv`: exact contract IDs, predicates, required artifacts, code pointer, and implementation status. Only record integrity has an executable verifier in this version.
- `androidworld_oracles.csv` / `.jsonl`: static source audit of all 116 registered AndroidWorld templates.
- `schemas/`: JSON schemas for task records, run results, scorer observations, and verifier contracts.
- `RUNBOOK.md`: how to run, review, score, and rebuild the pilot.
- `dataset_card.md`, `evaluation_design.md`, `research_basis.md`, and `README.md`.
- `bundle_manifest.json`: SHA-256 for each packaged file, excluding the manifest and zip itself.

The release has two separate notions of truth: (a) hidden benchmark ground truth, which the scorer needs, and (b) agent-produced verdict/evidence, which the benchmark measures. A run artifact should record model and provider version, system/app/emulator versions, switches, seed, setup/mutation logs, pre/post oracle snapshots, action sequence, model call IDs/responses, screenshots, accessibility trees, costs, exclusions, and checksums. Keep PII and credentials out; synthetic data only.

## Buckets, checks, and case forms

See `evaluation_buckets.csv` and `verifier_contracts.json` for the machine-readable family table and verifier registry. All nine buckets have generated reference pairs and an offline predicate in `generate_qa_buckets.py::verify`. Only record integrity currently has a device fixture adapter; eight other live fixture/capture adapters remain required. Reference predicates can check matching saved reads, but authored references alone do not constitute emulator evidence. Account and membership scenarios are out of scope. Keep Android runtime permission state as a separate, deterministic candidate bucket.

- **Data correctness:** exact field equality, target cardinality, and protected-row invariants. Use missing, near-miss, wrong-date, duplicate, and truncated-text cases.
- **Persistence:** apply an explicit lifecycle boundary and compare canonical state before/after. Use lost write, stale restore, and durable control pairs. Inject the fault at the lifecycle boundary (prefer a code-level save-path fault to editing state mid-run).
- **Action effects:** assert the intended delta occurred exactly once and unrelated state did not change. Include no-op, wrong-target, partial, duplicate, collateral, and cancel-commits variants. Maintain an app-specific ignore list for volatile fields such as timestamps, last-opened values, and sort order.
- **Navigation:** assert a screen fingerprint from the accessibility hierarchy and final data state. Do not rely on activity names for Compose screens. Each case needs a written expected Back/cancel/search transition contract and a faulted route/build.
- **Reachability and visual layout:** tree predicates can check presence, enabled/clickable state, viewport bounds, and mathematical rectangle overlap. Screenshot review verifies semantic obstruction, clipping, or missing visual content. Exclude intentional nesting/overlays; preserve ambiguous cases for human adjudication.
- **Presentation consistency:** compare stored values to rendered accessibility/OCR text through explicit locale/format rules.
- **Permissions:** use `dumpsys package` / AppOps as the deterministic permission-state oracle. Account, membership, and entitlement scenarios are excluded from this PoC because AndroidWorld apps are offline.
- **Success signal truth:** timestamp visible “success” feedback and compare with durable write state. For transient toasts, record an accessibility event or instrumentation log; alternatively use a persistent Snackbar in a patched app. Check whether the signal appeared in a screenshot/tree actually delivered to the agent. Report exposure misses and score the feedback comparison only when exposure is established.

For geometric overlap, preserve each relevant element's `[left, top, right, bottom]` rectangle and viewport. Compute intersection width/height as `max(0, min(rights) - max(lefts))` and `max(0, min(bottoms) - max(tops))`; report intersection area divided by the smaller element area so a small button mostly covered by a large surface is not diluted. Compute clipped fraction as off-viewport element area divided by element area. Each case freezes its target elements, allowable overlap, and clip threshold. Do not set one universal threshold before measuring benign nesting, touch targets, dialogs, and accessibility bounds; use screenshot review to decide if the measured intersection actually hides content or prevents interaction.

The current task format has case examples for value mismatch, missing row, date shift, and text truncation in the record-integrity family. The other families in `evaluation_buckets.csv` specify their case patterns but do not yet contain admitted task instances.

## Admission rules and quality review

Each case must pass all gates before contributing to results:

1. **Instruction completeness:** every required assertion is stated in the instruction and checked by the verifier; no hidden extra criterion.
2. **Oracle behavior:** the control satisfies the predicate; the fault violates it; the post-run oracle still resolves the result.
3. **Non-triviality:** a no-op or shallow response cannot pass fault cases; a correct control is not spuriously failed.
4. **Reset and replay:** repeat setup from the same seed and compare canonical state hashes.
5. **Discoverability:** the relevant evidence is available through allowed UI; retain screenshot and tree; a reviewer marks ambiguous visibility.
6. **State safety:** check protected records and isolate irreversible/external side effects.
7. **Hidden truth:** prove the actor and Checker only receive the declared agent view.
8. **Review:** two reviewers inspect the instruction, state mutation, oracle alignment, and failure-mode realism; track disagreements and adjudication.

For visual-only labels, report reviewer agreement and preserve raw screenshots. Automated geometry is a reproducible signal, but does not establish that an overlap is harmful without semantic context.

## Scoring

Score each eligible run with the confusion matrix:

| Hidden state truth | Agent verdict | Score label |
|---|---|---|
| Criterion true | PASS | Correct approval |
| Criterion true | FAIL | False FAIL |
| Criterion false | FAIL | Fault detected |
| Criterion false | PASS | False PASS |
| Either known truth | INCONCLUSIVE | Abstention |
| Truth/setup unavailable | Any | Infrastructure exclusion |

Report false PASS, false FAIL, INCONCLUSIVE, decisive coverage, paired correctness (control PASS + fault FAIL), evidence support, fault localization, protected-state changes, extra actions/cost, and infrastructure exclusions. Break down by bucket, app, fault mechanism, model, condition, framing, and device profile. Use paired confidence intervals and paired tests on matched variants; do not treat repeated parameterizations of one template as independent task templates.

## What this package can claim today

The source inventory shows reusable deterministic evaluator patterns across AndroidWorld. The package contains 600 authored reference pairs (including 150 source-derived record pairs), nine offline predicates, and five direct fixture setup observations. The observations cover correct and fault states and include independent pre-run state-oracle results; they are not 150 device executions. Screen discoverability reviews and agent verdict outcomes are not included. Eight live adapters remain to be built; deceptive success is defined in references and is not yet injected on-device. Account/membership cases are dropped; permission state remains a candidate. Oracle-tier accuracy, reviewer κ, and error bounds still need measurement and are not implied by a tier label. Do not present generated specifications as measured agent performance.

Suggested expansion: qualify the current record-integrity slice, then add file/provider state, lifecycle persistence, no-op/wrong-target effects, selected real transition faults, reviewed layout faults, and finally a patched-app success-toast case. Use the Android functional bug study and Android mutation-testing literature to select plausible fault operators, not to claim prevalence from synthetic mutants. [Android functional bug study](https://doi.org/10.1145/3597926.3598138), [MDroid+](https://doi.org/10.1145/3106237.3106275), [Stoat](https://doi.org/10.1145/3106237.3106298), [DDLDroid](https://doi.org/10.1145/3597926.3598089), [Nighthawk](https://doi.org/10.1109/TSE.2022.3150876)
