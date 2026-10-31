# Independent checks for an Android QA benchmark

Status: research inventory, 2026-10-30. Based on the pinned AndroidWorld checkout at `55ddaf5edc6f6c25673aed343907d5b9dca66f84`, the current Artemis pilot, and official Android testing/storage documentation. “Available” means an evaluator pattern exists upstream; it does not mean an Artemis adapter has been implemented or validated on the emulator.

## What “independent” means here

An independent check is computed by the harness from a source the evaluated agent and Checker did not author and cannot alter through their normal UI tools. It answers the benchmark's truth question from a controlled fixture or external observation. It does **not** have to use a different sensor from the agent in every case.

Keep these evidence roles distinct:

1. **Outcome oracle:** decides whether the requested behavior is true, using app/system/backend state or a frozen external criterion.
2. **Exposure record:** records what the agent could see, such as a toast, screen text, tree, or screenshot.
3. **Agent evidence:** the screenshot/tree/action result cited by the agent or Checker.

For example, a screenshot can confirm that a “Saved” toast was exposed, but it cannot prove the write persisted. The database or local service log decides persistence. Conversely, the database can prove a value exists but cannot prove it was displayed correctly. Paired outcome and exposure checks are needed for deceptive-success experiments.

“Independent” is about provenance and access control, not merely a different file format. The oracle result, mutation metadata, and expected label must stay out of actor and Checker inputs. If the evaluated agent receives shell/ADB access, an oracle in the same device environment is not hidden; use a separate evaluator process/credential boundary or constrain the agent tool set.

## Oracle inventory from the pinned AndroidWorld checkout

The following is direct source inspection of `/home/lucky11/workspace/android_world`, pinned to the same revision used by `pilot_v1`.

| State/evidence source | AndroidWorld examples in this checkout | What it can verify for QA | Confidence and caveat |
| --- | --- | --- | --- |
| App SQLite database | Calendar, Expense, Recipes; `common_validators/sqlite_validators.py` reads app DB rows over ADB and checks additions/deletions/integrity | Exact fields, missing/extra/duplicate rows, unchanged protected rows, mutation confirmation, durable state after reopen | Strong for structured state; schema-specific and privileged DB access may require rooted/debuggable emulator. Does not prove correct screen rendering. |
| App/shared filesystem | `common_validators/file_validators.py`, Markor and file tasks use ADB file operations; checks file existence/move/delete and file contents | Exact file path, existence, bytes/text, rename/move, persistence across relaunch | Strong for file outcomes; avoid upstream fuzzy matching where the benchmark requires exact text. The evaluator's read must not be exposed to the agent. |
| Android Contacts provider | `common_validators/contacts_validators.py` reads contacts through AndroidWorld's contacts utility | Contact existence, exact name/normalized number, accidental duplicate or collateral contact changes | Strong local device-state oracle. Android documents the provider's tables/query model; aggregation can make raw row counts misleading, so compare normalized contact data and stable IDs where appropriate. |
| SMS provider / local sent-message state | `common_validators/sms_validators.py` reads emulator sent messages, recipient/body/time, and checks stuck-at-sending UI | Whether the intended local message exists, recipient/body correctness, duplicate/suppressed send, hang state | Useful only on an isolated emulator with no real delivery. Provider state does not establish carrier delivery. Keep externally routed SMS out of the suite. |
| Telephony call state plus UI | `common_validators/phone_validators.py` checks Android call state and also checks dialer activity/UI for the expected number | Whether a call is active and whether the intended number is displayed | Mixed oracle: call state is system-level; number is verified in the UI because the system API does not reveal it in this task. Do not label the UI portion as durable state. |
| System settings/services | `single/system.py` reads brightness, Wi-Fi, and Bluetooth state; composite tasks check setting + app launch | Setting changed or preserved, permission/connectivity preconditions, cross-app/system workflows | Strong for queried system state. Some Android versions restrict or virtualize toggles; validate actual effect on this emulator/API level. |
| UI hierarchy / current activity | Clock checks timer/stopwatch state in UI elements; Browser tasks check current app and a rendered “Success!” element; phone call checks dialer content | Visible state, screen reached, visible label/control, timer state where no exposed DB is practical | Good behavioral/render evidence, but correlated with what the agent sees. It cannot alone substantiate a hidden persistence claim. Accessibility omissions can make it incomplete. |
| Composite state oracle | `composite/system.py` combines Wi-Fi state with app launch; `composite/markor_sms.py` combines note/file and SMS outcomes | Multi-step, cross-app acceptance criteria; all components must be checked independently | Strong if every component is asserted. Preserve per-component results rather than only an averaged reward. |

The source inventory demonstrates several grounded checks exist in AndroidWorld, but not every task is immediately suitable for the QA benchmark. Most upstream evaluators check whether an agent successfully completed an action. To study QA, convert a task into a **test case**: prepare correct/faulty outcomes and ask the agent to inspect and report them, without revealing which variant it received.

### Candidate cases that follow from these oracles

| QA check | Independent check | Example controlled defect | Status for Artemis |
| --- | --- | --- | --- |
| Record-field correctness | SQLite row and protected-row hash | target deleted, near-miss text, wrong amount/date, duplicate | Current pilot exists for Calendar/Expense/Recipe, but emulator round-trip and human discoverability remain case admission requirements. |
| File/text persistence | File exists + exact content hash before/after reopen | missing file, truncated text, old content after edit | AndroidWorld evaluator patterns exist; no Artemis task adapter in the frozen pilot. |
| Contact correctness | Contacts provider query | wrong number, changed display name, duplicate contact | Upstream AddContact evaluator exists; Artemis adapter not yet implemented. |
| Message side-effect correctness | Local sent-SMS state + recipient/body | wrong recipient/body, duplicate, “sent” feedback but no local message | Upstream validator reads local sent state; isolate transport and verify no external send before admission. |
| System-setting correctness | ADB/system setting reader | setting stays wrong despite success cue, unrelated setting changes | Existing Artemis Bluetooth fixture is a first system-state oracle. Extend only after API/device reliability is measured. |
| UI text vs stored text | Screenshot/accessibility tree plus SQLite/file value | stale display, wrong formatting, label/value mismatch | Requires two assertions: persisted value and rendered value. Do not make OCR/vision the sole ground truth where exact state is readable. |
| Back/cancel workflow safety | Pre/post target and protected-state snapshots plus action path | cancel still deletes, Back saves unexpectedly, wrong neighboring row changed | Oracle pattern is straightforward, but requires a workflow fault hook or app version exhibiting the defect. |
| Toast says success but write failed | Capture toast exposure + DB/file/local service state | fail commit while retaining ordinary success UI | Core research case; not available in current pilot. Prefer app-owned persistence fault hook or a reproducible real bug. |
| Login/role/entitlement | Separate local mock service's account/role/entitlement DB and request log + UI | basic role sees premium content, revoked membership remains effective, logout retains private data | Not supplied by AndroidWorld (which avoids login-dependent apps). Build a deterministic local service/demo app with synthetic accounts. |
| Crash/hang | Process/activity state, logcat crash/ANR event, timeout threshold | crash on navigation, indefinite loading | Android logcat can provide diagnostics; use explicit time limits and repeated controls. It is a separate reliability track, not an ordinary PASS/FAIL oracle for functional state. |
| Accessibility/layout | UI tree properties and deterministic screenshot geometry; human review for subjective quality | missing accessible label, clipped primary control, overlap, low contrast | Android offers UI Automator/accessibility tooling. Keep objective machine checks separate from human usability judgments. |

## Independent-check ladder

Use the strongest feasible source per claim. This is not a single universal ranking; each source answers a different question.

1. **Exact durable state** — DB rows, file content, Contacts/SMS provider, system setting, or mock-service database. Best for whether an outcome persisted and whether unrelated data changed.
2. **Independent event record** — local backend request log, notification/event store, controlled fault hook, app instrumentation event. Best for whether the app attempted, accepted, rejected, or duplicated an operation.
3. **System process/state record** — activity/task state, permission grant state, connectivity, call state, crash/ANR log. Best for OS interaction and reliability claims.
4. **Rendered UI capture** — screenshot plus accessibility/UI hierarchy. Best for what was visible and reachable, including false success messages and stale/wrong text.
5. **Human adjudication** — blinded protocol over saved evidence. Needed for discoverability and subjective UX; publish reviewer agreement and retain disagreement as unresolved/unknown.

For each case, state which source is the truth oracle and which sources only support visibility, exposure, or diagnosis. A text recognition model can extract or annotate screenshot content, but its output is model-assisted evidence, not independent ground truth unless validated against a deterministic source or blinded human labels.

## First buildable check matrix

Rank candidates by oracle maturity and research value rather than by number of mutation operators.

| Rank | Check family | Harness condition | Independent oracle | Why first/why later |
| ---: | --- | --- | --- | --- |
| 1 | Exact record verification (Calendar/Expense/Recipe) | correct vs one-field/deletion/duplicate fault | app SQLite | Already has frozen cases and strict scorer. Use to qualify state setup and evidence capture. |
| 2 | Visible text vs stored text | state correct but UI stale/wrong, or both wrong | SQLite/file plus captured UI tree/screenshot | Directly tests multimodal QA skill; exact stored content gives reference. Need a validated way to control render/cache fault. |
| 3 | Cancel/delete and protected-state check | correct cancel vs cancel-commits fault | pre/post DB/provider snapshot | Measures workflow reasoning and safety; choose a reversible local record and ensure the prompt is unambiguous. |
| 4 | Success feedback vs dropped write | shown/suppressed feedback, identical failed durable outcome | toast exposure capture plus DB/file/mock backend | Best fit to the false-PASS research question, but requires a valid app-side failure hook. |
| 5 | Lifecycle persistence / recovery | same draft across background/relaunch/offline/reconnect | file/DB/service state before and after named boundary | Good mobile-specific family; define timing and avoid conflating app instability with infrastructure. |
| 6 | Account/entitlement | basic/member/expired/logged-out pairs | isolated mock backend + UI | High QA value but new local app/service needed; cannot be inferred from AndroidWorld. |
| 7 | Accessibility / compatibility | device profile and settings pairs | UI tree/geometry and official checks | Add as a separate track after deterministic criteria are validated. |

Do not make early task counts sound broader than they are. Ten random amounts in the same expense template give ten parameterized instances but only one core test skill. Report independent templates, generated instances, app count, oracle types, fault families, and admitted-case rate separately.

## Evidence-informed high-coverage slice

If “70–80% coverage” means **coverage of functional bug symptom classes in an observed bug corpus**, the most concrete estimate found here comes from an empirical study of 399 functional bugs in eight Android apps. It reports: content-related display issues 21.3%; incorrect interaction logic 19.0%; missing UI elements 18.0%; UI distortion 13.8%; functionality not taking effect 11.8%; redundant UI elements 8.5%; unresponsive UI elements 4.5%; other symptoms about 3.0%.

The first four sum to **72.1%** of that study's symptom labels. Adding “functionality does not take effect” gives **83.9%**. This supports a practical first slice of five check families. It does **not** show that these checks cover 72–84% of all Android bugs or real user workflows: the sample is finite, old enough to be version-sensitive, drawn from eight open-source apps, and measures reported functional-bug symptoms rather than the prevalence of all QA work. Treat the number as a rational coverage target for case design, then validate against a broader and newer bug corpus.

| Priority | Benchmark check | Representative natural-language test | Independent outcome check | Fault/control pair |
| ---: | --- | --- | --- | --- |
| 1 | Content/data correctness across reopen | “Open the target note, verify the exact title and text, edit the title, reopen it, and confirm the change persisted.” | Exact file/DB state for truth; screenshot/tree to establish what was displayed | Correct field vs near-miss, stale render, truncation, or lost update |
| 2 | Navigation and interaction logic | “Open the Downloads folder, go back, and verify you return to the prior folder without opening a file.” | Recorded activity/screen transition plus unchanged state snapshot | Correct destination vs wrong transition, Back failure, cancel that commits |
| 3 | Required controls present and reachable | “On the detail screen, verify the Save and Cancel actions are both present and usable.” | UI tree bounds/labels + screenshot review; scripted hit/response check where safe | Normal layout vs missing/hidden control or unreachable target |
| 4 | Layout and displayed content integrity | “Check that the amount, category, and primary action are readable and do not overlap at the configured screen size.” | Screenshot geometry and UI bounds; objective cut-off/overlap assertions, with human review for ambiguous cases | Baseline vs rotation/keyboard/large-text condition causing clipping or overlap |
| 5 | Action takes effect exactly as requested | “Change the note title, save, and confirm the new title is present after reopening while the other note is unchanged.” | Before/after DB/file snapshot and protected-record hashes | Successful update vs no-op, wrong record, partial write, or collateral change |

These five are **test families**, not five individual cases. Instantiate each across app/task templates and correct/fault variants; include positive controls, fault confirmation, protected-state checks, and UI discoverability review. Families 1 and 5 deliberately use dual assertions: durable state decides outcome, while the UI capture tells us what the agent could see. Families 3 and 4 need deterministic checks for objective criteria and a separate human-adjudication track for subjective judgments.

The study also grouped the oracles required by its bug sample: 133/399 were app-feature-agnostic; 100/399 used app-independent feature knowledge such as CRUD, navigation, settings, authentication, or icon consistency; 166/399 required app-specific feature knowledge. This means reusable generic checks alone do not cover all semantic app behavior. The high-coverage slice should therefore use generic UI/lifecycle checks **plus** app-specific state predicates (for example, exact note text, expense amount, or membership entitlement).

If “70–80% coverage” means **flows through a particular app**, percentages cannot be inferred from a bug taxonomy. Build a flow inventory for each selected app (screens, transitions, user goals), define a critical-flow denominator with human review, and measure which transitions/criteria the suite exercises. Report that as transition coverage or requirement/flow coverage, separate from bug-symptom coverage.

### Suggested measurable coverage reporting

- **Bug-symptom coverage:** share of a labeled reference bug corpus whose symptom labels map to at least one benchmark family; publish corpus, labels, mapping, and unmapped cases.
- **App-flow coverage:** covered critical transitions or user journeys divided by the reviewed app-specific inventory; publish inventory and denominator per app.
- **Oracle coverage:** admitted benchmark cases with a validated independent oracle divided by scheduled cases.
- **Fault-family coverage:** admitted distinct fault mechanisms and app/task templates; do not count parameter seeds as new mechanisms.

Do not publish “covers 80% of actual app flows” until the target app set and flow inventory have been defined and reviewed. A defensible near-term claim is “the selected case families map to 72.1% of symptom labels in the cited 399-bug study,” and even that must be described as corpus-specific.

## Admission and verifier self-checks

Before a case can enter the benchmark, its verifier must itself pass these checks:

- Correct control satisfies the predicate; fault condition fails it.
- A no-op agent does not accidentally appear successful on the fault variant.
- An unrelated mutation is caught by protected-state assertions when relevant.
- Reset/replay twice from the same seed produces the same canonical oracle state.
- A deliberate oracle read error yields `unknown` / infrastructure exclusion, never agent `INCONCLUSIVE`.
- The agent cannot read the evaluator output or hidden mutation metadata through its normal tools.
- The task instruction and evaluator agree field by field; tests do not demand undisclosed criteria.
- UI discoverability is reviewed on both variants, and the evidence artifacts are saved.
- Faults that can cause external side effects use only local sinks/test accounts and are cleaned up.

## Practical limits

- App-private DB inspection is convenient on rooted research emulators and for open-source apps; it is not the same capability an end-user tester has. Keep the evaluator channel separate and report when privileged oracle access is used.
- A durable state oracle may miss a display bug; a UI oracle may miss a persistence bug. A robust case often needs both and explicitly names which metric each informs.
- UI trees omit custom/canvas elements and may expose incomplete labels. Pixels/OCR can help establish visible exposure but may be ambiguous; label tool-assisted interpretations and retain the original screenshot.
- Device/emulator state changes across Android versions. Pin emulator image, API level, app APK, locale, clock and network. Verify preconditions immediately before each run.
- Login, paid membership and true server authorization are not reproducible on public accounts. Use a local mock backend and synthetic identities, with separate expected truth and UI observations.
- “Fault seeded” does not mean “realistic bug.” Keep fault operators tied to documented bug reports, app code paths, or empirical bug families; add a real-bug subset later to check external validity.

## AndroidWorld task data mapped to the five check families

The pinned checkout contains 116 task templates over everyday apps and system utilities. Its task metadata, initializers, and `is_successful` evaluators give us parameter generation and durable outcome predicates to reuse. They do **not** provide the correct-vs-fault QA pairs by themselves: current tasks usually ask the agent to perform an action and then reward the final target state. For this benchmark, retain their initializers/oracles but create inspection-oriented prompts and controlled fault variants.

| Check family | Useful AndroidWorld task templates in the pinned catalog | Oracle already present | Reuse decision |
| --- | --- | --- | --- |
| Content/data correctness across reopen | `MarkorCreateNote`, `MarkorEditNote`, `MarkorChangeNoteContent`, `MarkorMergeNotes`; `SimpleCalendarAddOneEvent`; `ExpenseAddSingle`; `RecipeAddSingleRecipe`; `ContactsAddContact`; `FilesMoveFile` | Markor/file content and path; app SQLite rows; Contacts provider | Strong source for parameterized records and exact/durable predicates. Build paired inspect tasks and include reopening before checking persistence. |
| Navigation and interaction logic | `SimpleCalendarDeleteOneEvent`, `ExpenseDeleteSingle`, `RecipeDeleteSingleRecipe`; `MarkorMoveNote`, `MarkorMergeNotes`; `TurnOnWifiAndOpenApp`, `TurnOffWifiAndTurnOnBluetooth`; cross-app image/Markor-to-expense or recipe tasks | Resulting record/file/system state; composite task components | Good source of multi-step normal flows and parameters. It does not seed wrong screen transitions, Back bugs, or cancel bugs; those need reproducible APK defects or fault hooks. |
| Required controls present and reachable | Tasks expose screenshot and accessibility-tree observations; screen-variation wrappers run task instances across portrait/landscape and multiple resolutions | UI hierarchy for visible controls; screenshots | Useful environment and navigation states; no AndroidWorld fault cases for missing controls. Need define objective control-presence/reachability assertions and add a seeded UI/build fault. |
| Layout/display integrity | `screen_variation.py` wraps tasks at NormalPortrait (1080×2400), NormalLandscape, LowResPortrait (720×1520), LowResLandscape, and HighResPortrait (1600×2560); tasks such as `ClockTimerEntry`, `BrowserDraw`, and data-entry screens provide visible targets | Screenshots/UI hierarchy; task result state | Reuse the screen configurations, but do not treat successful task completion as a layout oracle. Add screenshot/geometry checks plus human adjudication for ambiguous visual defects. |
| Action takes effect exactly as requested | Calendar/Expense/Recipe add/delete tasks; Markor file changes; Contacts; SMS; Bluetooth/Wi-Fi/brightness/clipboard; camera/media tasks | SQLite, file state, providers, system settings, task-specific UI checks | Best direct reuse. Convert each action task into a controlled no-op/wrong-target/partial-effect fault and check target + protected state before/after. Keep external effects isolated. |

The natural-language task templates and random parameters can supply realistic names, dates, messages, descriptions, and multi-record distractors. Keep `task_name`, upstream revision, generated params, original task goal, and original oracle version in each benchmark record. Do not report task-template count as bug-family count: several Calendar or Expense templates may be variants of the same semantic check.

### What AndroidWorld cannot supply for the initial target

- It does not include authentication or membership flows; the AndroidWorld paper explicitly avoids apps requiring login. Use a local mock service and synthetic `basic`, `member`, `expired`, and logged-out accounts for that family.
- It does not include seeded layout, wrong-navigation, dropped-write, stale-cache, or false-success defects. Those require patched APKs, app-owned hooks, or reproducible historical buggy APKs.
- It is not a corpus of Android bug reports. Use bug-report/patch datasets for external-validity cases; use AndroidWorld for controllable app workflows, task parameterization, and existing state oracles.
- Screen variation is not defect injection. It tests agent robustness under different screen geometries; a layout QA check additionally needs a geometry/visual oracle to label clipping, overlap, or missing controls.

## Peer-reviewed approaches to borrow

These papers provide methods for constructing or validating the check families. We should borrow the method and preserve its limitations, rather than claim these techniques as new.

| Check need | Accepted research and method | What we can adapt |
| --- | --- | --- |
| Choose families and oracle types from observed failures | Xiong et al., ISSTA 2023, **ACM SIGSOFT Distinguished Paper**, studied 399 bugs in eight Android apps, analyzed symptoms and oracle needs, and released the bug dataset. The same work's RegDroid uses differential behavior across adjacent app releases and reported 14 functional bugs in five apps, 10 previously unknown and developer-confirmed. | Use its symptom/oracle taxonomy to stratify cases; reproduce a small version-pinned real-bug subset; compare correct and faulty versions where available. Do not equate its sample proportions with production prevalence. |
| Generate navigation/workflow paths | Stoat, ESEC/FSE 2017, builds a stochastic GUI transition model from runtime/UI information, then uses weighted exploration and model mutation/sampling to produce diverse tests; it also injects system events. DroidBot (ICSE Companion 2017) generates UI-guided inputs from an on-the-fly state transition model without requiring app/system instrumentation. | Use the navigation graph and state/action data to define transition coverage, revisit/recovery paths, and candidate test flows. For our benchmark the **LLM** executes natural-language test instructions; model-based exploration helps curate paths and assess coverage, not replace the tested agent. |
| Seed plausible app-specific faults | MDroid+ (ESEC/FSE 2017) derived Android fault categories from 2,023 artifacts, created 38 Android-specific mutation operators, and implemented 35 operators. | Start mutation design from documented fault classes; select operators that produce observable, non-trivial faults; validate each mutant with the case oracle and real-bug examples. Our initial DB row mutations are convenient but not a substitute for app-level Android mutations. |
| Test persistence/lifecycle behavior | DDLDroid, ISSTA 2023, analyzes save/restore data flows and reports data-loss defects around activity restart/relaunch. | Add pause/resume, rotation, process death, relaunch, and reconnect boundaries; compare exact user data before and after. Use this as a targeted fault family rather than blindly replaying only stable one-shot CRUD cases. |
| Evaluate UI appearance | Nighthawk, published in IEEE TSE, detects and localizes display issues from screenshots and evaluates on real apps; it reports precision/recall and human-confirmed/fixed findings. | Use screen variants and paired screenshots for candidate display anomalies; keep model-detected regions as triage signals, then use deterministic geometry checks or blinded reviewers for final labels. Do not let a vision model be the ground-truth oracle for itself. |
| Build a reproducible benchmark harness | AndroidWorld (ICLR 2025) and OSWorld (NeurIPS 2024) pair natural-language tasks with deterministic initialization and task-specific evaluators; AndroidWorld uses app/system state primarily and UI checks where necessary. | Package each case with frozen instruction, setup, variant, oracle, teardown, and verifier self-checks. Save all run data and score offline, as the existing pilot intends. |

The paper/corpus mapping implies a practical sequence:

1. **Inventory AndroidWorld source tasks and validators** (the table above) and create a machine-readable case catalog.
2. **Build verifiable instances** for CRUD/content and system-state workflows using the existing SQLite/file/provider/system oracles. Add paired correct/fault states and protected-state hashes.
3. **Add observed paths** for navigation using AndroidWorld task flows plus a recorded state-transition graph; define transition coverage per app.
4. **Add visual checks** on the supported screen configurations, initially limited to missing/overlapping/cut-off controls with deterministic geometry or blinded human review.
5. **Add lifecycle and transaction faults** using DDLDroid-inspired durability boundaries and MDroid+-inspired fault categories; prioritize the false-success dropped-write case.
6. **Validate realism** by reproducing a small sample from the ISSTA 2023 bug dataset or a newer curated report/patch corpus; separately report seeded-mutant and real-bug results.

This is the “OSWorld-style data gathering” part: each record is a task definition plus a controlled environment and evaluator, not just a prompt list. The evaluation set should contain task templates, parameterized instances, initial-state/variant hashes, oracle version, expected outcome, and run traces. Freeze the public development split and keep a held-out set of task templates or fault mechanisms to limit prompt/agent overfitting.

## Sources

### Local pinned source

- [AndroidWorld repository at the pinned pilot revision](https://github.com/google-research/android_world/tree/55ddaf5edc6f6c25673aed343907d5b9dca66f84)
- [SQLite validators](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/common_validators/sqlite_validators.py)
- [File validators](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/common_validators/file_validators.py)
- [Contacts validator](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/common_validators/contacts_validators.py)
- [SMS validator](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/common_validators/sms_validators.py)
- [Phone validator](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/common_validators/phone_validators.py)
- [System task evaluators](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/single/system.py)
- [AndroidWorld screen-variation wrapper](https://github.com/google-research/android_world/blob/55ddaf5edc6f6c25673aed343907d5b9dca66f84/android_world/task_evals/robustness_study/screen_variation.py)

### Accepted research papers

- [AndroidWorld, ICLR 2025](https://arxiv.org/abs/2405.14573)
- [An Empirical Study of Functional Bugs in Android Apps, ISSTA 2023](https://doi.org/10.1145/3597926.3598138)
- [Guided, Stochastic Model-Based GUI Testing of Android Apps (Stoat), ESEC/FSE 2017](https://doi.org/10.1145/3106237.3106298)
- [DroidBot, ICSE Companion 2017](https://doi.org/10.1109/ICSE-C.2017.8)
- [Enabling Mutation Testing for Android Apps (MDroid+), ESEC/FSE 2017](https://doi.org/10.1145/3106237.3106275)
- [DDLDroid, ISSTA 2023](https://doi.org/10.1145/3597926.3598089)
- [Nighthawk, IEEE Transactions on Software Engineering](https://doi.org/10.1109/TSE.2022.3150876)
- [OSWorld, NeurIPS 2024](https://arxiv.org/abs/2404.07972)

### Official Android documentation

- [Behavior UI tests and UI Automator](https://developer.android.com/training/testing/ui-tests/behavior)
- [Modern UI Automator testing](https://developer.android.com/training/testing/other-components/ui-automator)
- [Contacts Provider](https://developer.android.com/identity/providers/contacts-provider)
- [Android data and file storage](https://developer.android.com/training/data-storage)
- [Logcat](https://developer.android.com/tools/logcat)

