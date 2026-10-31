# Android QA evaluation method

Status: proposed method, 2026-10-30. This specifies how to turn AndroidWorld task data and Android bug examples into reproducible QA evaluation cases. It does not claim the proposed cases are implemented.

## The evaluated behavior

AndroidWorld's core loop is: initialize a task, give its natural-language goal to an agent, then call `is_successful` to check whether the goal state was reached. That is a **task-completion** evaluation. Our benchmark uses the same environment setup and state-oracle pattern, but evaluates a different question:

> Given an app that is either correct or contains a controlled fault, can the agent inspect the app, return the right QA verdict, support it with recorded evidence, and avoid unrelated changes?

The agent receives a **test instruction**. It does not receive the `control`/`fault` label, injected fault, expected verdict, setup snapshot, or oracle output. It may navigate and perform allowed checks; it must not repair a fault unless the case explicitly asks it to.

AndroidWorld already supplies 116 parameterized task templates, app initialization, evaluators, and teardown patterns. Its task evaluators commonly inspect SQLite, files, Android providers, system state, or UI elements. The source code and task list are pinned for this project at `55ddaf5edc6f6c25673aed343907d5b9dca66f84`. [AndroidWorld paper](https://arxiv.org/abs/2405.14573), [pinned repository](https://github.com/google-research/android_world/tree/55ddaf5edc6f6c25673aed343907d5b9dca66f84)

## What prior evaluation work tells us

- **OSWorld / AndroidWorld task pattern:** a natural-language instruction plus deterministic setup and a task-specific execution-based evaluator. In AndroidWorld's code, that is implemented as task parameters, `initialize_task`, `is_successful`, and `tear_down`. We should preserve the separations and add explicit variant and QA-verdict fields. [OSWorld paper](https://arxiv.org/abs/2404.07972), [AndroidWorld task runner](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/minimal_task_runner.py)
- **Real bug examples:** the ISSTA 2023 study publishes a dataset of 399 Android functional bug reports with reproduction evidence and fixes; 265 were still reproducible during the study. Its paper classifies symptoms and oracle types and introduces RegDroid differential testing. This can source a curated real-bug validation split; it is separate from AndroidWorld's task templates. [ISSTA paper](https://doi.org/10.1145/3597926.3598138), [artifact repository](https://github.com/Android-Functional-bugs-study/home)
- **Fault seeding:** MDroid+ derives Android mutation operators from reported Android faults. Use its fault categories to guide seeded variants; reject mutants that crash at setup, do not violate the intended predicate, or are not discoverable. [MDroid+ paper](https://doi.org/10.1145/3106237.3106275)
- **Navigation coverage:** Stoat and DroidBot derive UI states and transitions and explore action sequences. We can use a curated state/action graph to check navigation behavior and report transition coverage; the graph is not itself proof that a screen behaved correctly. [Stoat](https://doi.org/10.1145/3106237.3106298), [DroidBot](https://doi.org/10.1109/ICSE-C.2017.8)
- **Lifecycle/persistence:** DDLDroid studies missing save/restore flows around activity restart and relaunch. Use those boundaries for durability tests (background, rotate, process restart, relaunch), with a state oracle before and after. [DDLDroid](https://doi.org/10.1145/3597926.3598089)
- **Visual defects:** Nighthawk detects/localizes display problems from screenshots, but visual models are tools for surfacing candidates, not authoritative labels for this benchmark. Use UI geometry checks and blinded human review for final visual defect labels. [Nighthawk](https://doi.org/10.1109/TSE.2022.3150876)

## Case definition: same check, correct and faulty variants

Create one *case template* from a reusable app workflow and one independently verifiable acceptance criterion. Generate two matched variants from the same seed:

- `control`: the app satisfies the criterion and the evaluator returns true;
- `fault`: one declared fault makes the criterion false while preserving unrelated state.

Use `expected_outcome: pass/fault` or similar internally. Avoid calling the app variants “PASS” and “FAIL,” because those are the agent's verdicts.

### Required case record

```yaml
case_id: expense.amount.readback.v1
family: content_correctness
app: Pro Expense
app_build: <pinned APK/build hash>
android_image: <pinned emulator image/API/device profile>
upstream_task: ExpenseAddSingle
upstream_revision: 55ddaf5edc6f6c25673aed343907d5b9dca66f84
parameters: <frozen generated target and distractor values>
instruction: <natural-language QA check shown to the agent>
allowed_actions: [navigate, search, open_record, inspect]
protected_state: <canonical snapshot/hash of non-target rows>
oracle:
  kind: sqlite_predicate
  version: exact-fields-preserve-before/v1
  acceptance_predicate: <exact row and protected-row assertions>
variants:
  control: <normal initialization>
  fault: <one mutation and mutation version>
discoverability: <review label and evidence references>
durability_boundary: reopen_record
expected_agent_verdict:
  control: PASS
  fault: FAIL
```

The manifest must store the actual generated parameters, source revision, evaluator version, APK/device identifiers, before/after oracle snapshots, mutation confirmation, and artifact hashes. The agent sees only `instruction`, allowed tools, and normal live device observations.

## Verifier: what it does and what it returns

Write the verifier as deterministic, case-specific setup and assertion code using AndroidWorld's `TaskEval` conventions. Do not use an LLM judge to decide ground truth. Model-based vision/OCR can annotate candidate UI evidence, but a verifier must resolve the label from deterministic state assertions or a reviewed visual rubric.

### Admission sequence

1. **Reset:** restore the pinned app/device fixture and seed the frozen parameters.
2. **Baseline assertion:** verify starting preconditions and snapshot protected state.
3. **Variant application:** apply no mutation for control or exactly one declared fault for fault.
4. **Fault assertion:** run the independent oracle before the agent starts. Control must satisfy the criterion; fault must violate it. Otherwise mark setup invalid and do not score the agent.
5. **Discoverability check:** confirm that the criterion can be investigated through the allowed UI and record the initial relevant screens. Unobservable cases are not benchmark cases yet.
6. **Agent execution:** provide the same natural-language test for both variants. Record every action, screenshot, accessibility tree, action result, model response and verdict.
7. **Post-run assertion:** read the oracle again, check the condition still applies, and compare protected state. A changed target state is an observed side effect; it is not automatically intent/tampering.
8. **Eligibility and scoring:** exclude setup, oracle, provider, emulator, or execution failures as infrastructure outcomes. Score agent `INCONCLUSIVE` only when the run executed but the agent could not establish the criterion.

### Verifier result schema

```json
{
  "setup_valid": true,
  "variant_valid": true,
  "oracle_available": true,
  "criterion_true_before_agent": false,
  "criterion_true_after_agent": false,
  "fault_confirmed": true,
  "discoverability_review": "discoverable",
  "protected_state_unchanged": true,
  "infrastructure_error": null,
  "eligible_for_scoring": true
}
```

The scorer then maps the app truth and the agent verdict:

| Independent app truth | Agent verdict | Result |
| --- | --- | --- |
| criterion true | PASS | correct approval |
| criterion true | FAIL | false FAIL |
| criterion false | FAIL | detected fault |
| criterion false | PASS | false PASS |
| either known truth | INCONCLUSIVE | abstention |
| truth/setup unavailable or run crashed | any | infrastructure exclusion; do not score as INCONCLUSIVE |

The Checker is part of the evaluated agent system. Its output is scored against the hidden oracle. The oracle must not be passed to the Checker.

## Evaluation recipe by check family

| Bucket | AndroidWorld data already available | Case prompt and control/fault scenario | Independent verifier | Remaining work to cover it |
| --- | --- | --- | --- | --- |
| **1. Content and persistence** | Markor create/edit/change/merge note tasks; Calendar/Expense/Recipe SQLite tasks; Contacts and file tasks. Existing pilot has 30 instances across Calendar, Expense, Recipe and a strict row predicate. | “Inspect record X; verify exact fields A/B; reopen and confirm persisted.” Control has all fields correct. Fault changes one field, drops one field, duplicates or deletes target. | Exact database/file/provider state before and after reopen; exact target uniqueness; hash all protected rows. Screenshot/tree shows the relevant data was reachable. | Extend from 3 SQLite apps to Markor files and Contacts provider; implement restart boundary; review discoverability. Existing pilot state oracle is the closest working vertical slice. |
| **2. Navigation and interaction logic** | AndroidWorld has multi-step delete, move, merge, cross-app import, reply, and system-composite tasks. Its action observations include screenshots and UI tree. | “Open item X, use Back, and check you return to list Y; cancel delete and check X remains.” Control follows expected transition. Fault is reproducible old/fixed APK, patched APK, or app-level hook that routes/commits incorrectly. | Normalize screen state from activity + UI-tree structure; assert expected next/previous screen and app state. Save transition/action trace. The evaluator checks required transition plus no forbidden state mutation. | AndroidWorld supplies paths, not seeded navigation defects. Curate actual bug reproductions or add fault hooks; label state graph nodes and expected transitions. Avoid inferring a defect only from the model's summary. |
| **3. Required controls and reachability** | AndroidWorld sends screenshot/UI hierarchy observations and screen configurations; no specific missing-control fault suite is supplied. | “On screen X, verify Save and Cancel are available. Do not save.” Control exposes both. Fault APK/layout hides, disables or occludes one target control. | UI Automator/accessibility hierarchy checks element existence, visible/enabled/clickable status, and bounds. Add a safe tapability check where the action is non-destructive. A human confirms the actual screen evidence is discoverable. | Need a stable screen-state identifier, case-specific required-element contract, and seeded APK/layout faults. Canvas/custom-drawn controls require image review or app test hooks because they may be absent from the accessibility tree. |
| **4. Visual/layout integrity** | AndroidWorld's robustness wrapper varies orientation and resolution; screens include forms, lists, timers, browser tasks. It does not ship defect labels for clipping/overlap. | “Check that the amount and Save control are readable, fully on-screen, and do not overlap in landscape.” Control uses baseline layout. Fault is an affected configuration or modified layout/build with clipping, overlap, wrong text, or missing imagery. | Rule checks on screenshot/UI bounds: required elements inside viewport, no forbidden overlap, text not clipped, expected content visible. Blinded reviewers adjudicate ambiguous visuals; preserve screenshot and UI tree. | Define geometry thresholds per criterion and verify inter-rater agreement. Do not use raw pixel equality alone; dynamic time/status/system bars and rendering differences cause false alarms. |
| **5. Action effectiveness and side effects** | AndroidWorld has create/delete/update-style task families with SQLite/file/provider/system-state evaluators; composite tasks combine multiple assertions. | “Change X and save; confirm X changed exactly once and Y stayed unchanged.” Control performs intended mutation. Fault is no-op, partial write, wrong target, duplicate effect, or collateral change. | Before/after exact state diff; assert intended delta and protected-state invariants. For systems actions query setting/provider/event log. For external sends use a local emulator sink only. | Build fault operators for each app/store; validate each mutation against both the positive and negative controls. Keep SMS/call effects isolated; do not use live accounts or networks. |

### Concrete example: one AndroidWorld task becomes a QA pair

Source template: `ExpenseAddSingle`, which generates a structured target expense and has a SQLite-backed success evaluator.

1. Generate a target expense and distractor rows using a frozen seed; save all generated parameters.
2. Create control and fault variants. Control contains the exact target. Fault changes only the target amount by a declared near-miss mutation; all other rows must hash identically.
3. Give both variants the same inspection instruction: “Find the expense named X. Verify its amount and category match the stated values. Do not edit it. Return PASS only if both match, FAIL if a mismatch is established, otherwise INCONCLUSIVE.”
4. Before the run, assert exactly one target exists, expected fields match in control, expected fields do not match in fault, and the UI can open the row.
5. After the run, rerun the exact SQLite predicate and protected-row check. Score the verdict and evidence independently. If the pre-run oracle failed, exclude the trial rather than calling the agent wrong.

This resembles AndroidWorld's deterministic task initialization/evaluator pattern, while converting the goal from “create expense” to “verify expense.” It also resembles benchmark case packaging in OSWorld and Terminal-Bench: instruction + environment/setup + evaluator + saved run record. [OSWorld](https://os-world.github.io/), [Terminal-Bench task structure](https://www.tbench.ai/news/announcement)

## Building a paired scenario dataset

Create a versioned **case template** and instantiate it into at least one matched control/fault pair. Keep one row per trial, with a shared `pair_id` and separate `variant_id`.

Minimum data columns:

```text
suite_version, case_id, pair_id, trial_id, family, app, app_build,
android_image, upstream_task, upstream_revision, parameter_seed,
variant_id, fault_family, mutation_version, task_instruction,
oracle_kind, oracle_version, expected_predicate, protected_state_hash,
pre_oracle_result, fault_confirmed, discoverability_label,
agent_verdict, cited_evidence_ids, post_oracle_result,
protected_state_changed, execution_status, exclusion_reason,
trace_bundle_hash
```

The same pair shares prompt, app version, parameters, initial state, and execution settings. Only the declared fault condition changes. Randomize which member of the pair runs first and reset independently before both. Do not treat repeats or different text values from one template as independent templates.

Report separate metrics:

- false PASS on faulty cases;
- fault detection (FAIL on faulty cases);
- false FAIL on correct controls;
- INCONCLUSIVE and decisive coverage;
- paired success (control PASS + fault FAIL for the same pair);
- evidence support and fault localization;
- protected-state changes and extra actions/cost;
- setup/oracle/discoverability exclusions.

## Recommended build sequence

1. **Finish and qualify current state-check slice:** use existing Expense/Calendar/Recipe cases; confirm reset, UI discoverability, pre/post oracle, and no protected-state changes. Keep this separate from the toast study.
2. **Add data-backed templates:** Markor files and Contacts provider. These give more independent data stores without needing a custom APK.
3. **Add no-op and wrong-target variants:** for existing SQLite/file actions, implement one fault operator per template and require deterministic state-diff assertions.
4. **Add transition cases:** pick two flows from MoveNote, DeleteSingle, and composite tasks. Record expected screens/transitions and use a real bug APK or controlled fault hook for the fault variant.
5. **Add visual cases:** choose one form and one list/detail screen; run baseline screen configurations and add only objective layout predicates plus reviewed bugged screens.
6. **Add real-bug validation set:** sample reproducible reports from the ISSTA artifact and a real-bug source corpus; preserve buggy/fixed APKs, steps, issue/patch link, and evaluator. Exclude cases that cannot be rebuilt or whose ground truth is ambiguous.
7. **Add the research-specific success-signal pair:** instrument a local app build so persistence can fail while the normal success feedback still appears; separately capture toast exposure and durable state.

At each step, a case enters the scoreable set only after its control passes, its fault fails the predicate, the evidence is discoverable, reset is repeatable, and a second person can review the case/evaluator alignment. The held-out split should separate task templates or fault mechanisms, not merely different generated names from the same template.

## Sources

- [AndroidWorld paper (ICLR 2025)](https://arxiv.org/abs/2405.14573)
- [AndroidWorld pinned source](https://github.com/google-research/android_world/tree/55ddaf5edc6f6c25673aed343907d5b9dca66f84)
- [ISSTA 2023 Android functional bug study](https://doi.org/10.1145/3597926.3598138)
- [ISSTA study artifact and 399-bug dataset](https://github.com/Android-Functional-bugs-study/home)
- [MDroid+ Android mutations (ESEC/FSE 2017)](https://doi.org/10.1145/3106237.3106275)
- [Stoat GUI testing (ESEC/FSE 2017)](https://doi.org/10.1145/3106237.3106298)
- [DroidBot (ICSE Companion 2017)](https://doi.org/10.1109/ICSE-C.2017.8)
- [DDLDroid (ISSTA 2023)](https://doi.org/10.1145/3597926.3598089)
- [Nighthawk (IEEE TSE)](https://doi.org/10.1109/TSE.2022.3150876)
- [OSWorld task benchmark](https://os-world.github.io/)
- [Terminal-Bench task structure](https://www.tbench.ai/news/announcement)
