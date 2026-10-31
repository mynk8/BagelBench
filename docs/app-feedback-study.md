# Trust the Toast? Study protocol

Status: research framing and implementation plan, 2026-10-30. This is not a report of measured outcomes. The frozen AndroidWorld state-inspection pilot remains unchanged.

## Framing

**Question:** When an LLM agent tests an Android app, how often does it issue a PASS contradicted by device state, and does a false app success signal increase that risk?

Provisional title: **Trusting the Toast: Measuring False PASS Verdicts of LLM Agents as Android App Testers**.

Plainer alternative: **Can LLM Agents Be Trusted as Mobile App Testers? A Fault-Seeded Study of False PASS Verdicts**.

The central claim is behavioral: a tester should verify the durable outcome rather than accept a success signal at face value. This work will not claim access to a model's internal reasoning or establish why a model acted as it did. Returned reasoning and trace-reader notes are diagnostic records, not causal evidence.

The novelty claim is a hypothesis to verify against related work, not an established fact. Nearby studies already examine self-report leakage, false completion signals, deceptive mobile UI, and persistent-effect verification. The proposed distinction is a controlled QA study that varies app-origin success feedback while holding the durable fault and test criterion fixed.

## Research questions

| RQ | Question | Primary measure |
| --- | --- | --- |
| RQ1 | How often do tester agents issue incorrect verdicts on seeded correct and faulty Android states? | False PASS, false FAIL, and INCONCLUSIVE rates against independent device state |
| RQ2 | Does a false app success signal increase false PASS? | Matched risk difference for signal shown versus suppressed on the same fault case and durable state |
| RQ3 | Which case properties are associated with false PASS? | Descriptive breakdown by visible versus stored-only fault, test length, app, and model |
| RQ4 | Which verification policy reduces false PASS, and what does it cost? | False PASS, false FAIL, inconclusive, decisive coverage, extra steps, latency, and tokens |

RQ2 is the primary contribution. RQ1 is the baseline and remains useful if the signal effect is small. RQ3 is exploratory unless sample size supports pre-registered comparisons. For RQ4, use at least claim-blind Checker and outcome-specific evidence-required PASS; report PASS guard separately until its evidence rule is strengthened.

## What the current harness supports

The artifact `apps/research_ui/datasets/androidworld/pilot_v1.json` is frozen. Its protocol is in `docs/qa-pilot-protocol.md`.

| Capability | Current state | What it supports |
| --- | --- | --- |
| AndroidWorld state setup and independent readback | Implemented for Calendar, Pro Expense, and Broccoli recipes | Correct/faulty structured-record controls |
| Frozen natural-language, read-only inspection tasks | Implemented: 30 parameterized instances, each with control and fault variant | 60 trials per condition and repeat |
| Before/after state snapshots and checksums | Implemented for the selected app data | State-based verdict scoring and change detection |
| Checker conditions | Implemented: probes off, claim-blind, PASS guard, tree-only, screenshot-only | Evidence-policy ablations on the current inspection tasks |
| Repeats, named conditions, trace export, deterministic scoring | Implemented | Reproducible baseline workflow |
| Successful-action post-screenshot capture | Added in source; the running service must reload before new runs contain it | Before/after visual evidence for subsequent runs |
| App-origin success signal shown/suppressed | **Not implemented** | RQ2 cannot yet be measured |
| Save workflow with fault injected after success feedback | **Not implemented** | The current seeded record is faulty before inspection; it does not test a failed save that looked successful |
| Outcome-specific evidence-required PASS | **Not implemented as a strict policy** | Existing PASS guard only rejects empty evidence or `history_summary`/`none`; it does not prove a fresh durable-state observation |
| Per-run model selection and inferential paired analysis | **Not implemented** | The current UI uses the configured model; the scorer's intervals are descriptive |

The current pilot is therefore a useful **RQ1 measurement-pipeline pilot**, not evidence for the toast hypothesis. Do not describe its 60 trials as 60 save workflows or as 60 false-success cases.

### Important control mapping

- The **Jev checkbox** controls whether actor-authored text is included in a retrospective action-choice comparison. Jev is not the Checker and does not change the run's verdict.
- The **claim-blind Checker** condition (`ARTEMIS_CHECKER_CLAIM_BLIND=1`) removes Operator summaries from Checker history. This is the relevant self-report intervention.
- The **PASS guard** (`ARTEMIS_PASS_GUARD=1`) is currently a weak citation-presence guard, not proof of independent verification. Do not call it “evidence-required PASS” until it requires a fresh, outcome-specific observation after the task's durability boundary.
- “No probes,” “tree-only,” and “screenshot-only” alter Checker evidence access. They do not hide or alter app feedback shown to the Operator.

## Target case design

Start with 30 parameterized workflows across apps whose state reader can verify the target and protected records. Keep the current three AndroidWorld apps as candidates; add more only after setup, reset, signal exposure, and oracle checks work end-to-end. The existing pilot supports Calendar, Pro Expense, and Broccoli recipes. It does not currently support Settings as a seeded oracle.

Prioritize two fault families:

1. **Saved wrong:** the durable row exists with an incorrect declared value.
2. **Success shown, not saved:** a controlled app-side persistence failure drops the write while the app still displays its normal success feedback; the expected durable row is absent at a predeclared reopen/restart boundary.

Each case must freeze the natural-language task, expected fields, allowed changes, protected records, mutation operator, durability boundary, app version, setup seed, and independent oracle predicate. The app's normal UI feedback must be recorded as **app-origin**. A harness overlay is not an app-origin toast; if used during engineering, label it as a synthetic feedback intervention and validate later with an app-owned hook or modified APK. Rolling a database row back after a successful save/toast tests a later persistence mismatch; by itself it does not establish that the app reported success for a failed write. The confirmatory case needs a persistence-layer fault hook (or a real bug) that drops the write while the normal success signal still appears.

The signal comparison must hold the exact durable state, task text, model, and Checker policy fixed. Randomize shown/suppressed order and restore the same initial state for each matched run. Record assigned signal condition separately from actual signal exposure in the screenshots/model input. Do not analyze only runs where the agent appeared to notice the toast.

Use matched workflow prompts for short and long variants. A longer prompt must preserve the same target predicate and not add unrelated work. Mark a fault visible only after review of the relevant before/after app screen or accessible UI evidence; stored-only faults require a separate label.

## Timing and scoring rules

Record timestamps for action completion, feedback appearance and dismissal, fault injection, app reopen/restart, each screenshot/tree/state read, each Checker request, and final verdict. The fault must be present before the observation that is supposed to verify persistence. A verdict issued before the fault is injected cannot be scored as a false PASS for that fault.

Truth comes from the independent AndroidWorld/app-state reader, never from the agent, Checker, or trace reader. A run with failed setup, failed fault confirmation, missing signal exposure, state-read failure, or execution/provider error is **not scored**. Keep INCONCLUSIVE for a functioning evaluator that cannot establish the criterion; keep infrastructure errors in a separate exclusion count.

The primary signal estimand on faulty runs is:

`Delta_signal = mean_i[PASS_i(signal shown) - PASS_i(signal suppressed)]`.

The claim-channel estimand is separate:

`Delta_claim = mean_i[PASS_i(claim present) - PASS_i(claim blind)]`.

Report false PASS on faulty cases, false FAIL on correct controls, INCONCLUSIVE and decisive coverage separately. For remedies, also report unauthorized/protected-state changes, extra UI steps, latency, and token cost. Never combine these into a single accuracy score without showing the components.

Pre-register app-signal and one verification-policy comparison. Use exact McNemar on matched binary pairs when there is one valid pair per independent case. With repeats or multiple generated variants sharing a workflow template, use case/template-clustered intervals or paired cluster permutation; do not treat repeated model calls as independent cases. Publish denominators, exclusions, matched risk differences, and 95% intervals. The current Wilson intervals are descriptive and do not address clustering.

## Run-count planning

The current state-inspection pilot is 30 instances × 2 states = 60 trials per condition/repeat. The proposed toast study is larger:

| Design | Runs, before exclusions |
| --- | ---: |
| 30 cases × 2 states × 2 lengths × 2 repeats × 3 models | 720 |
| Same plus reasoning on/off | 1,440 |
| 30 cases × 2 states × 2 signal conditions × 2 repeats × 3 models | 720 |
| Same plus claim present/blind | 1,440 |
| Same plus baseline and two verification policies | 4,320 |

Do not cross every factor at once. First run a small engineering slice (for example, 4 cases × 2 states × 2 signal conditions × 1 model = 16 runs) to validate resets, signal manipulation, actual exposure logging, and scoring. Then estimate discordant-pair rates and API cost before fixing the confirmatory sample. Reasoning on/off and test length are secondary until RQ2 works.

## Implementation gates

1. Keep and complete `pilot_v1` as the state-inspection pipeline validation. Do not edit its manifest or reinterpret it as a toast study.
2. Reload the backend after the post-action screenshot change and confirm new runs persist both screenshots; prior records cannot be reconstructed.
3. Add an app-feedback intervention with explicit `shown`/`suppressed` assignment, actual exposure capture, and a sham control for any overlay-based prototype. Add a persistence fault hook that makes the write fail while preserving the app's normal success path. Prefer native app feedback control for the confirmatory study.
4. Add post-feedback fault injection at the named durability boundary, then independently verify the intended fault and protected state before admitting the run.
5. Implement an outcome-specific PASS policy: require a Checker-cited, fresh observation tied to the target field and made after the durability boundary. Keep raw evidence and citation links in the ledger.
6. Add a dedicated toast-study suite version, scorer fields for assigned/exposed feedback and injection timing, and matched analysis. Freeze prompts, mutations, app builds, and oracle versions before confirmatory runs.

## Related-work boundary

These papers overlap with parts of the motivation; their existence means the paper must avoid a broad “first agent honesty” claim:

- [Claim Laundering](https://arxiv.org/abs/2610.25947) studies agents favoring self-authored records over observations.
- [Self-Report Leakage in GUI-Agent Completion Judging](https://arxiv.org/abs/2610.29609) studies the effect of self-reports in completion judgments, including mobile testing contexts.
- [False Success in LLM Agents](https://arxiv.org/abs/2606.09863) studies false completion signals.
- [AgentHazard / Hijacking JARVIS](https://arxiv.org/abs/2507.04227) studies manipulations of mobile-agent screen content.
- [EffectMatch](https://arxiv.org/abs/2609.31301) studies validation of persistent outcomes.

Before making a novelty claim, compare their experimental conditions and estimands directly with the app-origin feedback intervention proposed here. The safest claim is the measured result and released cases, not “nobody has measured this.”

## Abstract template

Fill the brackets only after the confirmatory runs and scorer reproduce the values from saved records:

> LLM agents are increasingly proposed as automated testers for mobile apps, yet a verdict is useful only if it reflects the app's actual state. We study false PASS verdicts: cases where an agent approves behavior contradicted by device state. We build a fault-seeded Android QA harness that records independent state before and after each run and varies whether app-origin success feedback is exposed while holding the durable fault fixed. Across [N] admitted runs on [K] apps and [M] models, agents issued false PASS verdicts in [X]% of faulty runs. The false-PASS rate was [A]% with the success signal shown and [B]% when suppressed ([paired difference and interval]). [Policy] changed false PASS by [C] points and changed inconclusive verdicts by [D] points. We release the harness, versioned cases, and replayable traces.

If the signal effect is small or uncertain, report that result directly. Use the plainer title and emphasize the fault-seeded baseline and verification-policy trade-off.
