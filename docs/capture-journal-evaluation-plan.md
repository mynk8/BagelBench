# Capture journal and evaluator plan

Status: plan, agreed direction, 2026-10-31. The proposed contracts and modules do not exist yet.

## Purpose

Bagel measures how well an external agent executes an Android QA test and reports the correct PASS/FAIL verdict.
The agent receives a natural-language test and the permitted Android tools.
Verified ground truth stays private.

The device service captures evidence during the run.
Evaluators inspect that evidence after the run.
The scorer compares the agent verdict with the verified outcome and the execution evidence.
Grading never calls a model.

```text
Native Harbor task
    -> reset, install, seed, verify initial conditions
    -> agent uses Android tools
        -> append actions, results, observations, and private captures to journal
    -> agent submits verdict, or the run ends without an answer
    -> seal journal and artifacts
    -> evaluators read journal + private expectations
    -> scorer grades agent verdict
    -> Harbor receives reward and result label
```

During the run, checkpoint hooks identify capture boundaries and collect evidence.
They do not determine rewards or disclose assertion results to the agent.
The final evaluator needs no live device.
It can repeat its work against the same journal and artifact bytes.

## Existing implementation and gaps

| Area | Current implementation | Planned work |
| --- | --- | --- |
| Agent execution | Harbor runs external agents | Preserve this boundary |
| Device journal | `steps.jsonl` stores actions, results, and screen captures | Add a versioned journal, capture provenance, and explicit capture status |
| Screen state | Screenshot, parsed UI elements, foreground activity | Preserve raw hierarchy, dimensions, timing, and observation delivery records |
| Private state | No general checkpoint collector | Add database, file, navigation, system, lifecycle, and event collectors |
| Verdict | `verdict.json`, submitted once | Preserve the original submission and record abnormal run termination |
| Evaluator | Screen-signature comparison in `benchmark/grading.py` | Add reusable assertions over recorded artifacts and checkpoint sequences |
| PASS credit | Correct build plus `NO_DEFECT` earns credit | Require the execution evidence declared by the case |
| Reset | Private setup commands before the first tool call | Add a reproducible baseline and recorded initial-condition verification |
| Case admission | Curator sets `validated=true` | Require reviewable evidence for both builds, reset, captures, and evaluator results |

Relevant code: [recorder](../bagel/benchmark/recording.py), [device tools](../bagel/transports/mcp/benchmark.py), and [current grader](../bagel/benchmark/grading.py).
No validated native Harbor task pairs are included yet.
Historical reference artifacts do not establish live device capture support for a bucket.

## Ownership and native Harbor tasks

Harbor owns agent execution, the agent environment, and verifier scheduling.
Bagel owns the external Android device, its reset, its journal, and its private evaluation.
A fresh Harbor container does not reset the external emulator.

Tasks retain the [native Harbor directory format](android-harbor-tasks.md).
Public instructions stay in `instruction.md`.
Private capture policies, assertions, ground truth, and reference artifacts belong under `tests/`.
The task loader must support these additions through a versioned Android contract.
The current loader does not accept the proposed additions.
There is no second task format or export step.

Proposed code ownership:

| Location | Responsibility |
| --- | --- |
| `bagel/benchmark/recording.py` | Journal format, artifact references, and readers |
| `bagel/device/capture/` | Read actual device state and report capture errors |
| `bagel/evaluation/` | Reusable assertions and case evaluators over recorded evidence |
| `bagel/benchmark/grading.py` | Combine execution, verified outcome, and agent verdict |
| `bagel/benchmark/scoring.py` | Aggregate results by case, app, family, tag, model, and harness |
| Existing transport adapters | Connect tool execution, private capture hooks, and verifier access |

Collectors can access the device. Evaluators cannot access the device or call models.
Task authors select reusable collectors and assertions.
New app-specific storage schemas can require a private adapter.
Benchmark users continue to supply natural-language tests rather than evaluator scripts.

## Reproducible environment lifecycle

Each attempt starts from a declared emulator baseline and a unique run directory.
The run record identifies the baseline, Android image, APK hashes, task revision, seed, and collector versions.
It also identifies the model, harness version, instruction, action budget, and capture policy.

The setup stage restores the baseline, installs the selected build, seeds fixtures, and applies declared device conditions.
Initial-condition checks verify the installed build, fixture contents, starting screen, and relevant permissions or settings.
Setup evidence stays private and becomes part of the run record.
A setup error prevents agent execution and produces an environment error.

The host reserves the device through final capture and journal sealing.
The next attempt cannot reset that device before required captures finish.
Timeouts, agent crashes, and missing verdicts still produce explicit run-end records.
Correct and faulty twins use the same public instruction, fixture seed, budget, and capture policy.

Open questions:

- Will each attempt use a fresh emulator clone or restore a named baseline snapshot?
- How will Harbor wait for Android setup readiness before agent execution begins?
- Which baseline artifacts and emulator settings require hashes or exact version pins?
- Which app state survives reinstall, including external files, providers, and system-owned data?
- Which clock, locale, timezone, display, animation, keyboard, and network settings must each task declare?
- How will fixtures replace external services whose state cannot reset reliably?
- How many repeated resets and readbacks establish case admission?

## Capture policy and checkpoint boundaries

A checkpoint identifies a stage in the test, such as a Save attempt, a restart boundary, or a reopened record.
The harness detects that stage from recorded actions and observed state.
An agent statement alone cannot establish checkpoint arrival.
Checkpoint rules allow different valid routes through the UI.

Default captures cover initial state, action boundaries, explicit observations, and final state.
Private task policies request additional state at relevant checkpoints.
Continuous or buffered event capture covers transient signals that can disappear between tool calls.

Capture triggers must preserve failed transitions.
For a navigation case, the source screen and navigation attempt trigger capture of the actual destination.
A trigger that requires the expected destination can hide the navigation defect.
The same principle applies to failed saves and missing success signals.

Each capture records its start and end times, triggering action, collector version, source, and status.
Wall time supports review. A monotonic clock establishes order and duration.
Screenshots, hierarchy, database reads, and activity reads are separate measurements.
Their timestamps describe the capture interval rather than imply one atomic device snapshot.

The journal records the observations actually delivered to the agent.
A private capture alone does not prove that the agent received an observation of the symptom.
Case admission requires a symptom that the permitted interface can expose.

Open questions:

- Which boundaries need captures before an action, after an action, or both?
- How will a trigger identify semantic screens and records across both builds?
- How will repeated visits receive distinct checkpoint identifiers?
- Which collector can observe a failed action that leaves no expected UI element?
- What settling rule and maximum delay apply to asynchronous saves and transitions?
- What capture overhead is acceptable, and how will that overhead enter the run record?
- Which transient events need a ring buffer, video, accessibility events, or app instrumentation?

## Proposed journal and artifact contract

The following layout is a proposal. Existing runs still use `steps.jsonl`, `verdict.json`, and `screens/`.

```text
run/
├── run.json                 Schema, task, environment, seed, and version identifiers
├── journal.jsonl            Ordered events and artifact references
├── verdict.json             Original agent submission
├── artifacts/
│   ├── screens/
│   ├── ui/
│   ├── storage/
│   ├── navigation/
│   ├── system/
│   └── events/
└── evaluation/
    └── <evaluation-id>/
        ├── checks.json      Assertion results and supporting evidence
        └── grade.json       Execution status, outcome, verdict grade, and reward
```

The journal is append-only during capture.
Sealing records the terminal event and artifact hashes.
Each evaluation records its evaluator version, private contract hash, journal hash, and artifact hashes.
A new evaluator version produces a new evaluation record and preserves earlier results.

| Record | Required content |
| --- | --- |
| Run manifest | Schema version, unique attempt ID, original instruction, task revision, environment identity, seed, and capture policy |
| Action event | Sequence ID, step ID, tool, arguments, start/end times, result, and error classification |
| Capture event | Capture ID, checkpoint occurrence, source step, collector version, time interval, status, and artifact references |
| Artifact reference | Relative path, content hash, media type, encoding, source, and schema version |
| Delivery event | Observation ID, source captures, delivery time, and exact content supplied to the agent |
| Terminal event | Completion reason, final capture status, and verdict presence |

Capture status distinguishes complete, partial, unavailable, and error results.
Missing hierarchy must not become a valid empty hierarchy.
Capture failure must not become a fabricated image or default device value.
Evaluators use required evidence only after its status and provenance pass their input checks.

Raw artifacts preserve source evidence.
Normalized records identify the raw inputs and normalizer version.
Database comparisons use declared fields, identities, and permitted differences.
Generated IDs, timestamps, row order, and other volatile fields need explicit rules.

Private artifacts, build assignments, assertions, and evaluator outputs stay outside every agent input.
The device host stores them separately from the agent environment.
Only the authenticated verifier can retrieve them or their computed grade.

Open questions:

- Will the new journal replace `steps.jsonl`, or will a compatibility projection preserve it?
- Which schema versions will readers support, and how will unsupported versions fail?
- Will storage captures retain consistent database backups, logical row exports, or both?
- How will artifact size limits and retention rules affect replay completeness?
- How will sealing handle an interrupted process or a partially written artifact?
- How will the verifier retrieve artifact bytes for offline evaluation?

## Evaluator contract and scoring

An evaluator receives a sealed journal, its artifacts, and the private case contract.
The contract selects checkpoint occurrences, expected values, permitted differences, and required execution evidence.
These expectations are fixed before the benchmark run.

Each assertion produces `satisfied`, `violated`, or `unknown`.
It includes a stable assertion ID, evaluator version, reason, and exact evidence references.
An input or capture error remains an explicit cause of `unknown`.
All-or-any composition, temporal ordering, and required evidence follow declared rules.

The final report separates:

- **Execution:** which required operations and checkpoints the agent completed.
- **App behavior:** which expected conditions held or failed.
- **Agent judgment:** whether the submitted PASS/FAIL agrees with the verified case outcome and required evidence.
- **Infrastructure:** setup, capture, timeout, and artifact errors.

An unattempted operation does not establish an app defect.
A verified app defect that prevents progress can satisfy a failure case through its declared alternative evidence.
A faulty build label alone cannot prove that the agent caught its defect.
Likewise, a correct build label alone cannot prove that the agent executed the test.

The reviewed build assignment and expected defect remain fixed ground truth.
Recorded state establishes exposure, execution, and the actual case behavior.
A disagreement with reviewed ground truth needs investigation and an explicit invalid-case or environment result.
The grader must not silently rewrite ground truth from the agent verdict.

Current protocol mapping remains `NO_DEFECT` = PASS and `DEFECT` = FAIL.
`INCONCLUSIVE` remains an explicit undecided answer.
Changes to reward rules require a versioned scoring policy.

Open questions:

- What execution evidence is sufficient for PASS in each case?
- Does FAIL always require the existing `flag_step`, or can a claim reference a checkpoint interval?
- How will a case establish that its symptom reached an observation supplied to the agent?
- How will unrelated defects and known issues affect the primary verdict grade?
- Which results earn zero credit, and which infrastructure results require a rerun?
- How will reports retain scheduled attempts so exclusions cannot silently improve the score?
- How will pair scores, bucket scores, app weighting, and confidence intervals use these result categories?

## Proposed consolidation of reporting buckets

The nine existing buckets mix defect types, lifecycle conditions, and comparisons between evidence sources.
The proposed reporting taxonomy has four primary families.
Lifecycle events and misleading feedback remain tags that can apply across families.
This proposal does not change dataset files, current bucket IDs, or scoring code.

| Proposed family | Existing capabilities | Shared evidence and assertions |
| --- | --- | --- |
| Data correctness and effects | `record_integrity`, `action_effect_side_effects` | Storage snapshots, field predicates, expected deltas, uniqueness, protected records |
| UI presentation | `visual_layout`, `presentation_consistency` | Screenshots, hierarchy, geometry, rendered values, reference comparisons |
| Interaction and navigation | `navigation_transitions`, `control_reachability` | Action sequences, semantic screen identities, control state, input effects |
| Platform behavior | `permission_state` | Permission grants, AppOps, system events, and permitted operation effects |

`persistence_lifecycle` becomes a lifecycle tag with a specific event, such as rotation, background, process death, or restart.
Its assertions compare relevant state across that boundary.
The same temporal comparison can apply to a database value, rendered content, or navigation context.

`success_signal_truth` becomes a feedback-truth tag.
Its assertions correlate a signal with the actual effect and agent-visible exposure.
A misleading Save signal usually belongs to the data family and uses this additional tag.

A case has one primary family and any declared capability, lifecycle, or feedback tags.
Secondary assertions can use evidence from other families.
Reports count a case once in the primary family. Tag views can overlap and must identify that overlap.
Historical bucket IDs remain available for comparison with older artifacts.
Any future native task field changes require a versioned contract.

Evaluator modules follow reusable assertions rather than one implementation for each reporting category.
For example, field equality, storage delta, temporal preservation, screen transition, geometry, and signal-effect correlation can compose one case evaluator.
Collector selection follows the required evidence, independent of the reporting family.

Open questions:

- Do these four families provide useful comparisons across apps and task types?
- Which family owns a case whose main defect crosses presentation and stored state?
- Which lifecycle and feedback tags need separate summary metrics?
- What minimum number of distinct faults and apps supports a family-level score?

## Capture and evaluator questions by capability

These nine IDs match the [existing reference generator](../scripts/androidworld/generate_qa_buckets.py).
They preserve detailed requirements under the proposed families and tags.
They do not identify nine separate evaluator frameworks or completed live adapters.
The following capture plans and open questions remain useful after consolidation.

### Record integrity: `record_integrity`

**Proposed capture:** consistent storage snapshots before the operation, after the operation, and after reopen.
Snapshots identify target records and protected records. UI captures show the inspected record and displayed fields.

**Proposed evaluator:** exact field predicates, target uniqueness, expected row changes, and preservation of protected records.
File and provider adapters use equivalent content predicates.

**Open questions:**

- Which apps permit private reads through a debug interface, emulator privileges, provider, or read-only app hook?
- How will SQLite capture include committed WAL contents without changing the app behavior?
- Which identities link a record across storage snapshots and UI observations?
- Which values require exact equality, units, normalization, or permitted timestamp differences?

### Persistence and lifecycle: `persistence_lifecycle`

**Proposed capture:** storage, UI, and process/activity records around background, rotation, process death, relaunch, and reopen.
The journal records the actual lifecycle boundary and its completion.

**Proposed evaluator:** compare declared durable values before and after that boundary.
Separate saved data, unsaved drafts, UI restoration, duplicates, and unrelated state changes.

**Open questions:**

- Which lifecycle event does each case require, and what evidence proves that event occurred?
- Which state must survive, and which transient state must clear?
- Can collector reads flush or preserve data that the fault normally loses?
- What commit deadline applies before process death or restart?

### Action effects and side effects: `action_effect_side_effects`

**Proposed capture:** before/after storage snapshots, action results, target identity, and relevant local service or system events.
Capture Cancel, Back, repeated Save, and wrong-record actions at their attempted boundaries.

**Proposed evaluator:** expected state delta, forbidden changes, uniqueness, and protected-state preservation.
A Cancel case can require an empty persistent delta.

**Open questions:**

- Which state lies inside the protected scope for each operation?
- How will fixtures record external effects such as sent messages or queued jobs?
- What timing distinguishes two agent taps from one tap that causes duplicate writes?
- How will asynchronous jobs and transaction completion enter the recorded evidence?

### Navigation transitions: `navigation_transitions`

**Proposed capture:** source and destination screenshots, raw hierarchy, activity/task state, record identity, and the intervening action sequence.
The navigation attempt triggers capture even if the expected destination never appears.

**Proposed evaluator:** permitted semantic transitions, Back/Up behavior, destination identity, preserved context, and forbidden data changes.
Different valid paths can satisfy the same transition requirement.

**Open questions:**

- How will semantic screen identities distinguish fragments and dialogs within one Android activity?
- Which paths, system screens, permission dialogs, and keyboard transitions are valid alternatives?
- What observation establishes an app navigation fault rather than an incorrect agent target?
- Do rapidly changing screens require event capture beyond snapshots after tool calls?

### Control reachability: `control_reachability`

**Proposed capture:** screenshots, hierarchy, viewport, insets, keyboard state, bounds, enabled state, and observed effects of input attempts.

**Proposed evaluator:** declared controls exist, remain visible and usable, and produce the required behavior after valid input.
Bounds or an enabled flag alone cannot prove reachability.

**Open questions:**

- Which controls require scrolling, keyboard dismissal, or another permitted discovery action?
- How will captures establish occlusion, hit targets, and overlapping touch regions?
- How will the evaluator distinguish an agent mis-tap from an unresponsive control?
- Which display profiles and accessibility properties form the task contract?

### Visual layout: `visual_layout`

**Proposed capture:** original screenshot bytes, raw hierarchy, element bounds, viewport, insets, density, font scale, theme, and orientation.
Capture both sides of relevant keyboard, rotation, and font-scale changes.

**Proposed evaluator:** geometry predicates for clipping, overlap, containment, spacing, and declared size requirements.
Deterministic image comparison can use pinned references, fixed masks, and declared tolerances.

**Open questions:**

- Which assertions use geometry, pixels, or both?
- How will references account for antialiasing, fonts, dynamic text, system bars, and animations?
- Which screenshot regions and tolerances require curator review before admission?
- How will the evaluator handle canvas content or missing hierarchy without treating absent evidence as a clean screen?

### Presentation consistency: `presentation_consistency`

**Proposed capture:** persisted values, rendered UI fields, screenshot regions, locale, timezone, and input parameters at the same logical checkpoint.
Paired captures retain separate measurement times.

**Proposed evaluator:** stored-versus-rendered field predicates, formatting rules, units, stale values, truncation, and record identity.
Expected formatting follows a declared locale and timezone.

**Open questions:**

- Which stable locators associate rendered fields with storage fields?
- How will canvas text enter a model-free evaluator?
- Which date, currency, rounding, ordering, and truncation rules belong to the contract?
- What capture interval permits a valid comparison during asynchronous refresh?

### Permission state: `permission_state`

**Proposed capture:** package permission grants, relevant AppOps, system dialogs, app UI, requested operation, and its data or service effect.
Capture initial state, grant or denial, and the subsequent operation.

**Proposed evaluator:** required permission state, expected app response, permitted fallback behavior, and forbidden effects after denial.

**Open questions:**

- Which Android versions and target SDK values change the expected behavior?
- Which permissions, AppOps, special access grants, and one-time grants need distinct collectors?
- How will revocation, Settings changes, and process restarts enter the checkpoint sequence?
- What independent evidence proves that a denied operation produced no forbidden effect?

### Success signal truth: `success_signal_truth`

**Proposed capture:** buffered toast, Snackbar, dialog, or other success events linked to the initiating action.
Capture durable state separately after the declared commit deadline.
Delivery records establish whether the agent received the signal.

**Proposed evaluator:** correlate success feedback with the actual effect, target values, duplicates, and protected state.
Private signal detection and agent-visible exposure remain separate facts.

**Open questions:**

- Which signal types can the existing helper observe, and which need instrumentation or buffered video?
- What evidence proves exposure to the agent rather than exposure only to a private collector?
- How will signals correlate with retries, multiple actions, and delayed commits?
- What time window distinguishes a misleading signal from an ordinary asynchronous save?

## Implementation sequence

1. Define the versioned journal, artifact contract, and evaluator result contract.
2. Add reset provenance, initial-condition verification, final capture, and sealing.
3. Complete one verified correct/faulty pair for record integrity through the native Harbor path.
4. Add persistence and action-effect captures using the same storage adapter.
5. Add navigation identities, transitions, and alternate failure evidence.
6. Add control, layout, and presentation collectors for one pinned display profile.
7. Add permission and transient success-signal collectors with explicit exposure records.
8. Extend family and tag reports after the taxonomy, execution, and infrastructure policies are agreed.

Each completed case needs evidence from both builds and repeated clean resets.
Replaying its sealed journal must reproduce the evaluator result without a device or model.

## Research position and evidence still required

The broad idea of Android GUI defect evaluation already has close prior work.
This plan does not establish a claim that Bagel is the first such benchmark.

| Related work | Relevant overlap |
| --- | --- |
| [AndroidWorld](https://arxiv.org/html/2405.14573) | Task initialization, cleanup, and outcome checks through databases, files, system settings, and UI state |
| [GTArena](https://arxiv.org/html/2412.18426v1) | Test execution and defect judgments against labelled defective and normal GUI transitions |
| [GUITestBench](https://arxiv.org/html/2601.04500) | Interactive mobile defect discovery, navigation to defect locations, and trajectory-based verification |

GUITestBench describes tasks that each target an issued defect.
Its single-action verification uses state and action matching. Its multi-action verification uses an LLM judge.
These are direct overlaps with the problem Bagel studies.
They also identify comparison points for matched clean controls and model-free evaluation.
See [GUITestBench, section 3.2](https://arxiv.org/html/2601.04500#S3.SS2).

The proposed contribution is reliable QA verdict evaluation on matched correct and faulty live-app builds.
Both builds receive the same natural-language test and controlled setup.
Private state assertions establish behavior and execution evidence.
An offline grader scores catches and correct clears from the recorded journal without a model judge.

The useful distinction is this combination and its demonstrated reliability.
Screenshots, buckets, state inspection, journals, and Harbor integration do not individually establish novelty.
The protocol must demonstrate valid clean controls, visible faults, capture fidelity, repeatable reset, and reproducible grading.
Results must report false PASS, false FAIL, incomplete execution, and infrastructure errors.
Model comparisons require a fixed harness or explicit model-and-harness labels.

Open research questions:

- Which existing benchmarks already supply matched correct/faulty interactive builds under the same instruction?
- Does an agent catch the fault and clear its matched correct build consistently?
- How often does success feedback cause a false PASS despite an incorrect durable state?
- Which failures arise from incomplete execution, missed symptoms, or incorrect judgment?
- Does grading remain stable across repeated clean runs and replay of the same captures?
- How much app-specific capture and evaluator work does each added case require?

No validated native pairs or comparative results currently establish these contributions.
A broader related-work review and an implemented case set are required before a novelty claim.

## Lessons from Cognition and Devin evaluations

Model-free grading is a reproducibility requirement for Bagel. It does not establish novelty by itself.
Related benchmarks use programmatic checks, model judges, or a combination.

| Evaluation | Published design | Lesson for Bagel |
| --- | --- | --- |
| Devin on SWE-bench | Cognition adapts an existing repair benchmark. Prepared environments and restricted repository history limit leakage. Trusted tests run after agent execution. | Keep agent access separate from private fixtures, assertions, and reference artifacts. Record exact environment preparation. |
| `cognition-golden` | An internal suite uses realistic environments and explicit success criteria. Complex outcomes can use evaluator agents with browser and shell access. | State each criterion explicitly and retain evidence for its result. |
| FrontierCode | Cognition combines executable checks, rubric criteria, and LLM-based grading. Blocking criteria gate the final score. | Separate required validity conditions from optional diagnostic measurements. |

Sources: [SWE-bench technical report](https://cognition.com/blog/swe-bench-technical-report), [coding-agent evaluation method](https://cognition.com/blog/evaluating-coding-agents), and [FrontierCode design](https://cognition.com/blog/frontier-code).
The published methods are available for review. `cognition-golden` is internal, and the FrontierCode article states that its tasks remain private.
These sources describe software-engineering evaluations rather than the Android QA verdict protocol proposed here.

Cognition describes calibration and review of evaluator results against ground truth.
Its FrontierCode process also challenges criteria with incorrect outputs and valid alternative implementations.
For Bagel, the corresponding admission review covers these cases:

- An incorrect app outcome must not earn credit from plausible feedback or incomplete captures.
- A valid alternative route must satisfy the same semantic execution requirements.
- A missing capture must produce an explicit evidence error or unknown result.
- A correct build with no meaningful execution must not earn a correct-clear grade automatically.
- Repeated evaluation of the same sealed artifacts must preserve the result for a fixed evaluator version.

The task contract must identify these cases and the evidence for its admission decision.
The evaluator requires its own error analysis, separate from agent false PASS and false FAIL rates.
An executable final assertion does not make a pipeline model-free if a model changes its inputs or decides its result.
Bagel keeps both assertion selection and grading rules fixed before the run.

## Evaluation references

OSWorld separates task setup, action execution, state getters, and metric functions.
Its standard `step()` path returns observations. Its main task evaluation runs through `evaluate()` after execution.
Used environments reset through the snapshot mechanism before the next task setup.
This plan adds private capture boundaries and replayable artifacts for Android QA.
It does not claim that OSWorld supplies a general mid-run checkpoint engine.
See the [OSWorld implementation](https://github.com/xlang-ai/OSWorld/blob/main/desktop_env/desktop_env.py).

GTArena evaluates action correctness against annotated GUI transitions and defect judgments against defective and normal labels.
Its test-intention coverage metric uses GPT as judge.
Bagel retains model-free grading and does not adopt that metric.
The published work does not establish a general database checkpoint implementation for this project.
See the [GTArena paper, sections 2 and 5.1](https://arxiv.org/html/2412.18426v1).

Existing [evaluation research](android-qa-evaluation-method.md) and the [dataset card](../apps/research_ui/datasets/androidworld/DATASET_CARD.md) supply context.
Historical documents and frozen datasets retain their contents.
