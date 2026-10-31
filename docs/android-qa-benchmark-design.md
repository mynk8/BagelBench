# Android QA agent benchmark: design

Status: proposed benchmark design, 2026-10-30. This document defines the target benchmark; it does not claim that all listed families are implemented or validated.

## Objective

Measure whether an Android agent can perform a natural-language QA check, detect a seeded or controlled defect, report the correct result, support that result with evidence, and avoid changing unrelated state.

This is different from measuring whether an agent can complete a user task. The agent is the tester. It must inspect an app, decide whether a stated behavior is correct, and report a finding. For faulty cases it should not repair the app unless the test explicitly asks for a repair.

AndroidWorld is the starting environment and source of app/task setup patterns, not the whole contribution. Its tasks establish that parameterized natural-language Android interactions can be evaluated with durable state checks. Our benchmark adds a test oracle task: the agent must distinguish correct behavior from controlled incorrect behavior and produce a supported QA verdict.

## Research basis and scope

The benchmark taxonomy draws on three complementary sources:

- Terminal-Bench's task package separates English instruction, isolated environment, reference solution, and tests; its harness runs the agent and verifies resulting state. [Terminal-Bench framework](https://www.tbench.ai/news/announcement), [repository task format](https://github.com/harbor-framework/terminal-bench-1)
- OSWorld uses a task instruction, setup configuration, and custom execution-based evaluator over a reproducible desktop environment. [OSWorld benchmark](https://os-world.github.io/), [task example format](https://timothyxxx.github.io/OSWorld/user_guides/task_example_explanation.html)
- ISTQB's mobile testing syllabus covers functional test types, mobile device and OS interactions, connectivity, compatibility, usability, and test environments. This provides the QA-work coverage frame, not a prevalence estimate. [ISTQB CT-MAT](https://istqb.org/certifications/certified-tester-mobile-application-testing-ct-mat/)
- Android's quality guidelines give concrete checks for navigation/back behavior, state preservation, orientation, notifications, visual quality, accessibility, and functionality. These map naturally to observable mobile checks. [Android core app quality](https://developer.android.com/docs/quality-guidelines/core-app-quality)
- An empirical study of 399 functional Android bugs groups symptoms into display issues (structure/content) and interaction issues (incorrect logic, no effect, unresponsive controls). This supports including text/content, navigation/interaction, and persistence faults. It is one mined dataset, not a universal frequency distribution. [ISSTA 2023 study](https://tingsu.github.io/files/ISSTA23-functional-bugs.pdf)
- AndroidWorld demonstrates the value of task-specific initialization, state-based success checks, and teardown, and uses UI checks when system state is impractical. It intentionally uses apps without login/authentication, so account and membership cases need another environment or a purpose-built fixture. [AndroidWorld paper](https://arxiv.org/abs/2405.14573)
- OWASP MASTG documents authentication, authorization, and session checks such as logout/session termination. Those are relevant QA families, but they require controlled accounts and often a backend oracle. [OWASP MASTG authentication and session testing](https://mas.owasp.org/MASTG/0x04e-Testing-Authentication-and-Session-Management/)

The listed categories are a **coverage plan**, not claims about how often each bug occurs in production. Report measured benchmark coverage and outcomes; do not infer real-world prevalence from the constructed suite.

## Benchmark unit: a verifiable check

Every benchmark case is one frozen, reproducible QA check. It contains:

1. **Scenario and task text:** the natural-language instruction given to the agent, with an explicit acceptance criterion and allowed actions.
2. **App/environment build:** APK/version, Android version, device profile, locale, clock, network state, and required account fixture.
3. **Setup state:** deterministic preconditions, seed, account/role if relevant, and a setup readback.
4. **Expected behavior:** a machine-readable predicate over named state and/or observable behavior.
5. **Variant assignment:** correct control or faulty variant, plus the fault operator and exact target.
6. **Oracle:** versioned, independent check of the expected predicate. The oracle result and mutation details are hidden from the agent and Checker.
7. **Evidence contract:** what a reviewer should be able to observe (screen, UI tree, persisted state, navigation transition, system event, or backend fixture).
8. **Protected state:** records/accounts/settings that must not change.
9. **Durability boundary:** when the behavior is considered committed, such as after reopen, process restart, relaunch, or reconnect.
10. **Scoring labels:** expected verdict, applicable detection/localization/evidence/safety rubric fields, and exclusion conditions.

A case is admitted only if setup is confirmed, the intended fault is confirmed, the oracle works on both control and fault variants, the criterion is discoverable through the allowed UI, and the pre/post oracle can distinguish the variants. Otherwise it is a harness failure, not an agent error.

## Task package and run loop

Follow the useful structure shared by Terminal-Bench and OSWorld: a human-readable instruction, a reproducible starting environment, an isolated run, and an execution-based verifier. Terminal-Bench packages tasks with their environment, instruction, reference solution, and test suite; OSWorld packages an instruction with setup configuration and a task-specific evaluator. Artemis should preserve that separation while making the hidden fault/oracle explicit for testing research.

Suggested case bundle:

```text
case-id/
  case.yaml              # version, app/build, family, seed, oracle contract, labels
  instruction.md         # natural-language QA request shown to the agent
  environment/            # APK/build references, emulator profile, local service fixtures
  setup/                  # reset and seed correct state
  variants/               # control/fault mutator; visible only to the harness
  evaluator/               # pre/post oracle and evidence checks; hidden from agent
  reference/               # human-verified execution notes and expected findings
  tests/                   # verifier self-checks on control, fault, and invalid setup
```

The run loop is:

1. Start a clean emulator/app snapshot and apply the case's setup seed.
2. Apply the assigned control/fault condition; verify it with the independent oracle before the agent starts.
3. Give the agent only the task instruction and normal app observations. Keep condition labels, mutation details, expected verdict, and oracle output out of actor and Checker context.
4. Record UI actions, screenshots/tree, app-origin feedback, execution errors, verdict, and cited evidence.
5. Capture post-run state and run the oracle again; compare protected state and check whether the assigned condition remained valid.
6. Score only if setup, fault, execution, oracle, and discoverability checks pass. Save infrastructure exclusions separately.

`reference/` is a curator guide, not a required action sequence. Accept any path that reaches the right QA result without violating scope. The verifier checks the behavior and evidence contract, not whether the agent copied a demonstration.

### Example case, concept only

**Instruction given to the agent:** “In Pro Expense, find the expense named ‘Health Insurance’. Check that its amount is $171.27 and that the category is Health Care. Do not edit anything. Return PASS only if both fields match; return FAIL if you establish a mismatch; otherwise return INCONCLUSIVE.”

**Hidden case state:** a control row matches both fields; a fault row has a changed amount while all other rows remain unchanged.

**Oracle:** read the expense row before and after; assert the exact amount/category and protected-row hash. **Visible-evidence check:** confirm the relevant details can be reached in the UI and captured. **Score:** verdict against oracle; whether the cited evidence is from the target record; protected-state changes; and whether the Checker relied only on actor-authored text. This mirrors the current state-inspection pilot. It does not test whether the app falsely claimed a save succeeded; that requires a separate write-workflow case.

The example uses a particular task to show the package boundaries. A released benchmark should include a mix of task families and report coverage by family rather than overstate one record-inspection pattern as general Android QA ability.

### Canonical outcome

Let `P(s)` be the frozen acceptance predicate for app state `s`. Control state must satisfy `P=1`; faulty state must satisfy `P=0`. For behavior that cannot be represented by durable state, define a separate observable predicate over a captured event/UI transition and validate it against positive and negative controls.

Use agent verdicts `PASS`, `FAIL`, or `INCONCLUSIVE`:

| Oracle outcome | Agent verdict | Label |
| --- | --- | --- |
| Correct (`P=1`) | PASS | correct approval |
| Correct (`P=1`) | FAIL | false alarm / false FAIL |
| Faulty (`P=0`) | FAIL | detected fault |
| Faulty (`P=0`) | PASS | false PASS |
| Either known state | INCONCLUSIVE | abstention |
| Oracle/setup/execution unavailable | any | excluded infrastructure outcome, never relabeled as INCONCLUSIVE |

If a test asks the agent to locate or explain a defect, also score finding localization against the seeded fault label. A correct verdict alone does not count as a correct diagnosis.

## Coverage model: QA work × oracle strength

Use two axes. The first says what work the tester performs. The second says what evidence can verify the result. Do not collapse them into one taxonomy.

### QA work families

| Family | Typical QA job | Example check | Candidate controlled faults |
| --- | --- | --- | --- |
| A. Data correctness and persistence | Verify create/read/update/delete and durable state | “Edit the event title, reopen it, and confirm the new title remains.” | missing write, stale value, wrong field, truncation, duplicate, lost update, accidental collateral change |
| B. Search, filtering, and text/content correctness | Check that user-visible content matches the requested data and filters | “Search for the exact phrase; confirm the matching note appears and unrelated notes do not.” | wrong displayed text, stale index, case/diacritic mismatch, incorrect filter, wrong sort, result omitted/duplicated |
| C. Workflow and navigation logic | Follow multi-screen paths and verify transitions/back behavior | “Open an item, cancel deletion, return, and confirm it remains.” | wrong destination, broken Back, cancel still commits, action applies to wrong row, control unresponsive, workflow dead end |
| D. Input validation and boundary behavior | Exercise valid/invalid/edge inputs and check acceptance/rejection | “Enter an invalid amount; confirm it is rejected and the prior value remains.” | invalid accepted, valid rejected, boundary off-by-one, parse/rounding error, validation message inconsistent with persisted result |
| E. Lifecycle and recovery | Verify behavior across pause/resume, rotation, process/app restart, connectivity restoration | “Draft a note, background and relaunch the app, then verify the draft is intact.” | unsaved state loss, duplicate submission on retry, stale screen after resume, broken restore, inconsistent state after reconnect |
| F. Device/OS integration | Check permissions, notifications, links, hardware/software interaction | “Deny notification permission, then verify the app handles the disabled state and does not claim a notification was sent.” | permission ignored, feature falsely reported successful, notification missing/wrong action, deep link opens wrong screen, orientation breaks control |
| G. Account, role, entitlement, and session | Verify identity and authorization state through app flows | “With the basic account, confirm the premium export is unavailable; with the member account, confirm it is available.” | role leak, wrong membership displayed, entitlement not applied/revoked, logout leaves private data accessible, account switch shows stale data |
| H. Destructive/externally visible side effects | Check that actions affect only the intended target and occur once | “Cancel sending; confirm no message was queued. Then inspect the intended draft.” | wrong recipient, duplicate send, action despite cancel, unrelated record deleted, side effect occurs without confirmation |
| I. Visual/accessibility quality (later track) | Inspect presentation and accessibility properties against a stated criterion | “Confirm the primary action is reachable and has an accessible label on this screen size.” | clipped/missing content, unreadable contrast, missing label, inaccessible target, layout overlap |
| J. Reliability/performance (later track) | Observe crash, hang, loading, or latency against a threshold | “Open the saved item; it must render within the declared limit without a crash.” | crash, infinite loading, timeout, intermittent failure |

Initial benchmark should emphasize A–H where exact outcomes can be frozen. Add I and J only as separate tracks with validated criteria and repeat protocols; visual style and perceived performance are easy to score inconsistently.

### Oracle tiers

| Tier | Oracle | Suitable checks | Limitation |
| --- | --- | --- | --- |
| O1: durable state | App database, file, Android provider, system setting, local service state | record fields, membership fixture, queued side effects, persistence | A DB row can be correct while UI is stale or misleading |
| O2: behavior/event | Instrumented app event, local mock backend request log, notification/event store, lifecycle trace | submit/cancel, permission behavior, duplicate sends, network recovery | Requires instrumentation and strict event definitions |
| O3: rendered UI | Screenshot plus accessibility/UI tree and deterministic visual assertions | visible text, screen destination, control presence, layout bounds | UI can look correct while durable state is wrong; OCR/vision must not silently become the truth oracle |
| O4: human adjudication | Blinded reviewers using frozen protocol and saved evidence | discoverability, usability/accessibility judgments, ambiguous bug reproduction | Not a fully automatic reward; report agreement and adjudication procedure |

Prefer O1/O2 for outcome labels and use O3 to establish what the agent could see. For a toast hypothesis, record the app-origin toast as exposure evidence while O1/O2 independently determine whether the write succeeded. A synthetic overlay tests a different condition and must be labeled as such.

## Mutation and condition design

Mutations represent controlled defects. They must be small, targeted, reversible, and independently confirmed. Store their implementation and state hashes in the run record, but never send mutation identity to the agent.

### Mutation operators

1. **Record operators:** delete target, change one field, truncate text, duplicate target, shift date/time, flip a flag, archive/hide target.
2. **Transaction operators:** drop write, persist only a subset of fields, commit late, replay a write, apply update to wrong row, preserve success feedback while write is rejected.
3. **Query/render operators:** stale search index, wrong sort/filter, stale cached display, mismatched label/value, format/unit/time-zone conversion error.
4. **Workflow operators:** cancel does not cancel, Back commits or discards incorrectly, action routes to a neighboring item, confirmation dialog reports success without effect.
5. **Environment operators:** deny a permission, toggle connectivity at a frozen point, rotate/background/restart, expire a session, change account role/entitlement in a controlled fixture.
6. **Side-effect operators:** duplicate or suppress a local queued event, change recipient/target, mutate a disposable local sink. Never use live external services or accounts.

Avoid arbitrary database corruption that bypasses normal UI semantics unless the case specifically evaluates detection of inconsistent persisted state. The fault should correspond to a recognizable defect class and have a clear UI symptom or explicit “stored-only” label.

### Experimental controls

- **State pairs:** same task and parameters, correct vs faulted app state.
- **Signal pairs:** same faulty durable outcome with app-origin success feedback shown vs suppressed. Record assigned condition and actual exposure separately.
- **Claim pairs:** same saved trace with actor summary included vs removed from Checker input.
- **Evidence-policy pairs:** same case with the pre-registered evidence source/policy changed.
- **Repetition:** reset from the same frozen seed; repeat indices are new observations, not new independent cases.

Do not cross all factors immediately. Start with one case family and one intervention; expand after oracle and reset reliability are established.

## Scoring rubric

Publish a scorecard, not just one aggregate. The benchmark's primary result is verdict correctness under known outcomes.

### Primary outcome metrics

- **Fault detection (mutation score):** `FAIL on faulty cases / admitted faulty cases`.
- **False PASS:** `PASS on faulty cases / admitted faulty cases`.
- **False FAIL:** `FAIL on correct cases / admitted correct cases`.
- **Abstention:** `INCONCLUSIVE / all admitted cases`.
- **Decisive coverage:** `(PASS + FAIL) / all admitted cases`.
- **Paired check success:** fraction of complete correct/fault pairs where control is PASS and fault is FAIL.

Report denominators, exclusions, and 95% intervals. Do not reward an always-INCONCLUSIVE policy as accurate; show abstention and decisive coverage next to error rates.

### Diagnostic rubric, reported separately

| Dimension | Scoring rule |
| --- | --- |
| Detection | Verdict matches the oracle label on the case |
| Localization | Correctly identifies affected feature/record/field and fault family from a frozen label set |
| Evidence support | Cites at least one recorded post-action observation that directly bears on the acceptance criterion; self-report alone does not qualify |
| Verification behavior | Performs the required check at/after the durability boundary (for example, reopen or inspect durable state where permitted) |
| Safety / scope | Leaves protected state unchanged and does not perform forbidden repair or external side effects |
| Efficiency | Steps, elapsed time, model calls/tokens; never combined with correctness without the component measures |

For every case, capture action path, screenshots/tree, action results, app feedback, Checker input/output, oracle snapshots, mutation confirmation, and integrity hashes. Agent reasoning can be retained as model-reported text, but it is not the score oracle and does not prove why a verdict was reached.

### Inference

For matched shown/suppressed or claim-present/blind conditions, report paired risk differences in false PASS. Use exact McNemar only with one independent matched pair per case. With repeats or multiple variants per template, use case/template-clustered intervals or a paired cluster permutation. Do not count model calls on the same template as independent samples.

## Dataset construction plan

### Phase 1: Verifier-ready seed set

Keep the current 30-instance AndroidWorld pilot as an RQ1/pipeline slice for A (structured record inspection). Add selected AndroidWorld workflows that have state readers, then create controlled correct/fault pairs. Candidate apps include Calendar, Expense, Recipes, Contacts, and Markor, subject to actual setup/oracle validation. The existing suite is a seed, not a representative QA corpus.

For each added case, require:

1. Upstream task/setup and task oracle pinned to a commit.
2. A domain-specific assertion over the exact target and protected state.
3. At least one mutation that makes the assertion fail while leaving unrelated state unchanged.
4. UI discoverability review and evidence capture.
5. Repeatable reset/teardown and verification of the condition actually delivered.

### Phase 2: Workflow-fault cases

Add transaction, search/render, cancel/navigation, and lifecycle faults using local app builds or app-owned test hooks. For each case, preserve ordinary UI feedback unless the feedback is the experimental factor. This phase creates the core contribution: evaluating a QA agent, rather than asking a task-completion agent to create test data.

### Phase 3: Account and entitlement track

Do not imply AndroidWorld supplies login or membership coverage. Build this on a local deterministic service or demo app with synthetic accounts such as `basic`, `member`, expired membership, and logged-out. The service must expose a private evaluator API or event/state log to the harness only. Test login success/failure, account switching, entitlement gating, revocation, logout, and stale cached content. The benchmark must verify both server-side authorization and what the UI reports; client-only state is not enough for authorization claims.

### Phase 4: Wider mobile quality track

Add permissions/connectivity/device compatibility, accessibility, visual quality, and reliability checks where the environment and rubric can provide stable evidence. Keep human-adjudicated quality checks separate from deterministic functional scoring.

## Pilot selection rules

Score each candidate case before inclusion:

| Criterion | Admission question |
| --- | --- |
| Oracle validity | Can an independent check distinguish correct and faulty outcomes? |
| Mutation validity | Does the mutation model a coherent defect and change the intended predicate? |
| Discoverability | Can the agent encounter enough evidence through normal UI actions? |
| Reproducibility | Can setup, reset, fault, and cleanup be repeated from a frozen version/seed? |
| Safety | Are accounts and side effects isolated from real users/services? |
| Family coverage | Does it add a testing skill/fault family not already overrepresented? |
| Independence | Is it a distinct scenario/template rather than a cosmetic parameter change? |

The first benchmark release should prefer fewer independent, well-validated templates over a large count of generated values. Report both template count and parameterized instance count. A million parameters do not imply a million distinct testing skills.

## First benchmark slice recommendation

Build a **verifiable functional QA core** of roughly 4–6 families before widening:

1. Exact field/persistence mismatch (current pilot foundation).
2. Search/text/render mismatch with separately checked durable and visible values.
3. Workflow/cancel/navigation defect with a protected-state assertion.
4. Invalid input or boundary defect with accepted/rejected state predicate.
5. Lifecycle/reopen persistence defect.
6. False success feedback after a dropped local write (the toast study).

Then add an account/membership track on a deterministic local service; it is high-value but cannot be responsibly evaluated on the current AndroidWorld app set. This ordering keeps the initial suite close to the research question while creating a path toward broad mobile QA coverage.

## Current implementation mapping

| Capability | Existing state |
| --- | --- |
| Frozen natural-language state-inspection cases | `apps/research_ui/datasets/androidworld/pilot_v1.json`, 30 parameterized instances / 60 correct-fault trials |
| Exact record-state oracle and scorer | `docs/qa-pilot-protocol.md`, `apps/research_ui/scripts/score_pilot.py` |
| Candidate AndroidWorld app/task catalog | `apps/research_ui/datasets/androidworld/case_catalog.json` |
| App-origin success feedback experiment | Not implemented |
| Write-drop transaction fault preserving normal success feedback | Not implemented |
| Search/render, navigation, validation, lifecycle fault adapters | Not implemented as benchmark cases |
| Login, account roles, membership backend fixtures | Not implemented; AndroidWorld intentionally avoids login-dependent apps |
| Cross-family calibrated aggregate score | Not defined; component metrics above are the intended report |

Do not count planned families as benchmark coverage until the setup, mutation, oracle, and reviewer checks are implemented and validated.
