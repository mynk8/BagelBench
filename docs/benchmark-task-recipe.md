# Recipe: deriving QA cases from open-source apps and their tests

Status: research recipe, 2026-10-31. It describes how established benchmarks build tasks and adapts that to Android QA cases. It does not claim any case below has been built or run.

The benchmark measures how well an LLM does **QA on Android and mobile apps**, acting as the tester. It does not measure task completion. The goal is a repeatable pipeline: pick an open-source Android app with good tests, turn each tested behaviour into QA material, build a correct and a faulty version of the app, and prove with the app's own tests that the two versions differ. The current AndroidWorld suite changes *data*; this recipe produces faults in *app behaviour*.

## 0. What we measure: does the model catch the defect?

The measured skill is **defect detection**: given an app build, does the model flag the defect when one exists and stay quiet when none does? Bug reports, root-cause analysis and test design come later, and only for defects it actually caught (§0.4).

### 0.1 The unit and its outcome

A **case** is one validated pair: a correct build and a faulty build of the same app, with the same prompt and seed state (§3). The model runs once on each build. Each run ends with a structured answer:

- `verdict`: `DEFECT`, `NO_DEFECT` or `INCONCLUSIVE`
- for `DEFECT`, the step at which it flagged, so the harness records the screen and UI tree at that moment

Every run reduces to one label, computed by the harness without reading free text:

| Build | Model says `DEFECT` | Model says `NO_DEFECT` | Model says `INCONCLUSIVE` |
|---|---|---|---|
| Faulty | **Catch** if the flag lands on the defect (0.2); otherwise **wrong catch** | **Miss** | **Abstain** |
| Correct | **False alarm** | **Correct clear** | **Abstain** |

### 0.2 What counts as catching *this* defect

A `DEFECT` verdict on the faulty build is a catch only if it lands on the seeded defect. Validation (§3 Step 3) records the defect's **symptom signature**: the screen (activity and key UI-tree nodes) and the state or element that differs between the two builds. The flag matches when the recorded screen at the flag step matches the signature and the differing element was on screen at or before that step. This is a mechanical check over recorded observations; no judge reads the explanation.

### 0.3 Metrics (all computed per model, per guidance level)

- **Detection rate** = catches ÷ faulty runs
- **False-alarm rate** = false alarms ÷ correct runs
- **Pair score** = cases with *both* a catch on the faulty build *and* a correct clear on the correct build ÷ all cases. This is the headline: a model that always says "defect" scores 0, and so does one that always says "fine".
- **Abstain rate**, reported per build type, so abstaining can't hide misses
- **Grounded catch rate** = catches where the differing element was on screen before the flag ÷ catches. Mostly 100% by construction (0.2); it drops only if the signature check is relaxed.
- **Consistency** = the share of cases whose pair score holds on all *k* repeats (pass^k)
- **Cost** = steps, tokens and wall time per run

Report each metric with confidence intervals grouped by app and source test, not by case, because cases from the same app are correlated.

### 0.4 Guidance levels (the difficulty axis)

The same pair runs at three levels. Lower guidance means harder detection:

1. **Directed:** a natural-language acceptance criterion naming the behaviour (§3 Step 4)
2. **Feature hint:** only the feature area, e.g. "Test task deletion"
3. **Open:** only the app, e.g. "Test this app for defects", with a step budget

Mobile conditions (§3, Mobile-condition faults) add a second axis: whether finding the defect needs rotation, backgrounding, process death, a permission change, going offline, or a display setting.

Out of scope for now, and later scored only on catches: reproduction steps (checkable by replaying them on both builds), root-cause localisation, and test-case design.

### 0.5 Rules

- **Every faulty case has a correct twin.** Correct builds measure false alarms.
- **The scaffold is fixed when comparing models**, so differences come from the model. A scaffold comparison is a separate experiment.
- **The model's explanation is not scored as evidence.** Detection is decided by the verdict, the flag step and the recorded screens. What the model says about why it flagged is a self-report.

### 0.6 Official grading rule

**A model passes a case when it catches the defect on the faulty build and reports no defect on the correct build. Its benchmark score is the share of cases it passes.**

Precisely:

1. **Final answer.** Each run ends with exactly one final answer: `verdict` (`DEFECT`, `NO_DEFECT` or `INCONCLUSIVE`) and, for `DEFECT`, `flag_step`, the id of a step the model actually executed. A run that ends without a valid final answer, or exceeds its step budget, counts as no answer.
2. **Faulty build is right** only if `verdict = DEFECT` and the screen recorded at `flag_step` matches the symptom signature:
   - same activity / screen identity, and
   - the signature's anchor nodes are present, and
   - the differing element shows its *faulty* state (e.g. the 'Quarterly report' row is absent).
3. **Correct build is right** only if `verdict = NO_DEFECT`. Any `DEFECT`, wherever it points, is a false alarm.
4. **Not right:** `INCONCLUSIVE`, no answer, a wrong catch (`DEFECT` that misses the signature), and a false alarm all count as not right. Abstaining never earns credit.
5. **Case pass** = both builds right in the same repeat.
6. **Repeats.** Each case runs k = 3 times per build, in fresh emulator snapshots. The case score is the fraction of repeats that pass (0, ⅓, ⅔ or 1).
7. **Benchmark score** = the mean case score within each app, averaged over apps, so every app has equal weight. Report it as a percentage with a 95% bootstrap confidence interval that resamples apps, then cases within apps.
8. **One score per guidance level:** Directed, Feature hint and Open are reported separately and never averaged together. The headline is the Directed score until the other levels have been validated.
9. **Harness failures are not model failures.** An emulator crash, a failed setup readback or a broken build is rerun. A case that fails setup twice is removed for *every* model and listed in the release notes.
10. **Secondary numbers** (reported, not ranked): detection rate, false-alarm rate, abstain rate per build type, all-repeats-pass consistency, and median steps, tokens and time per run.

11. **Grading never calls a model.** Every judgement above comes from ground truth fixed before the run, or from the harness's recordings:
    - which build is faulty: known by construction, confirmed by the app's own test
    - the answer: structured fields returned through a tool call or JSON schema, never parsed from prose; malformed means no answer
    - the catch: the recorded UI tree at `flag_step` matched node-for-node against the signature
    Visual-defect signatures must be computable as well: UI-tree bounds overlap, ellipsized-text flags, or a pixel diff against the correct build's reference screenshot. No vision-model judgement. LLM components inside the system under test (the Checker, screenshot review) never feed the score.
12. **Defects we didn't seed.** Real defects found in the correct builds during validation are listed as known issues, each with its own signature. A flag that matches a known issue is neutral: no credit, no penalty. Unmatched flags on correct builds count as false alarms in the score and are queued for human review between releases. Confirmed new defects become known issues in the next version.

The screen match shows the model was looking at the defect when it flagged; it does not show the model understood it. That is intentional: the explanation is a self-report and is not scored.

A case enters the scored set only after passing §3 Steps 2–6. The scored set, signatures, prompts, budgets and emulator image are frozen under a version tag, and scores are only compared within one version.

## 1. How strong benchmarks build their tasks

| Benchmark | Where tasks come from | What decides pass/fail | How a task is admitted | How it scales |
|---|---|---|---|---|
| SWE-bench | Real GitHub issues and the PRs that fixed them; 2,294 tasks from 12 Python repos | Repo tests: `FAIL_TO_PASS` (fail before the fix, pass after) and `PASS_TO_PASS` (must keep passing) | A PR is kept only if it has at least one fail-to-pass test | Mining merged PRs. [paper](https://arxiv.org/abs/2310.06770) |
| SWE-bench Verified | Human screening of 1,699 SWE-bench tasks, giving 500 | Same tests | Developers scored each task 0–3 for "issue underspecified" and "tests reject valid solutions". 38.3% were flagged underspecified and 61.1% for unfair tests | Manual. [OpenAI](https://openai.com/index/introducing-swe-bench-verified/) |
| SWE-smith | Any repo with a test suite; 50k tasks from 128 repos | A candidate bug is kept only if it breaks at least one existing passing test, with a 2-minute test limit | Repo admitted when an agent installs it and over 80% of tests pass | Synthetic bugs: LM modify/rewrite, AST edits (invert if, remove condition, change constant, remove assignment, …), combining bugs, reverting real PRs. Overall yield about 50%; combined bugs about 97%; individual AST operators 2–49%. [paper](https://arxiv.org/abs/2504.21798) |
| Defects4J | Real bugs from project history | A triggering test fails on the buggy version and passes on the fixed one | Fix minimised by hand (refactorings removed); broken and flaky tests excluded | Manual mining. [repo](https://github.com/rjust/defects4j) |
| Terminal-Bench | Real engineering work | Tests check the *final environment state*, not the agent's commands | "Well-specified": tests pass if and only if the end state is acceptable. A human-written oracle solution must pass. The environment must not contain the tests or solution | Contributed tasks plus review tooling. [paper](https://arxiv.org/abs/2601.11868), [task guide](https://www.tbench.ai/news/writing-a-good-terminal-bench-task) |
| AndroidWorld | 116 hand-written task templates across 20 apps | System state (databases, files) | Templates generate random valid parameters, so each run is a fresh instance | Parameterised templates. [paper](https://arxiv.org/abs/2405.14573) |
| OSWorld / OSWorld-Verified | Real desktop tasks with setup config and an evaluator script | Execution-based evaluator per task | A post-release audit fixed 300+ issues (site changes, ambiguous instructions, fragile evaluators) | Manual authoring. [Verified blog](https://xlang.ai/blog/osworld-verified) |
| GTArena | Real apps, apps with injected defects (source-level or MutAPK), and synthetic screenshots | Defect-present vs normal labels | Defect types: display (content, layout, style) and interaction (no response, navigation, wrong result) | Injection plus synthetic transforms. [paper](https://arxiv.org/abs/2412.18426) |

Supporting Android sources:

- **MDroid+** built a taxonomy of 262 Android fault types in 14 categories, from bug reports, bug-fixing commits, Stack Overflow and the Android API exception hierarchy. It defines 38 mutation operators, 35 of them automated (e.g. `BuggyGUIListener`, `ViewComponentNotVisible`, `InvalidKeyIntentPutExtra`, `WrongStringResource`, `InvalidSQLQuery`). Its mutants rarely fail to build (0.56%) or die trivially (2.42%), far below the generic tool muDroid. [FSE'17](https://www.cs.wm.edu/~dposhyvanyk/pubs/FSE'17-mDroid.pdf), [operators](https://thesoftwaredesignlab.github.io/android-mutation/)
- **Themis** has 52 reproducible real **crash** bugs from 20 open-source apps; 18 were found by no automated tool. It contains crashes only, not functional bugs. [repo](https://github.com/the-themis-benchmarks/home)
- **ISSTA'23 functional bug study** has 399 functional bug reports from 8 apps. The release is a bug list plus the RegDroid tool; reproducible buggy builds are not listed. [repo](https://github.com/Android-Functional-bugs-study/home)
- **Test culture is rare.** A study of more than 12,000 open-source Android apps found only 8% used automated testing. Apps with good tests must be picked on purpose. [ASE'20](https://seal.ics.uci.edu/projects/ase20empirical/index.html)
- **Validity checklist.** ABC names two failure modes: *task validity* (the task can be solved only with the intended skill) and *outcome validity* (the check is right). Flaws like τ-bench counting empty answers as success skew results by up to 100% in relative terms. [paper](https://arxiv.org/abs/2507.02825)

## 2. The shared recipe

Every benchmark above follows the same steps, in this order:

1. **Source.** Start from something real that already defines correct behaviour: an issue plus fix, a test, or a task template.
2. **Environment.** Make the source run reproducibly (Docker image, emulator snapshot, pinned build). Reject sources that don't run reliably.
3. **Reference behaviour.** Take an executable check that already exists: the repo's tests, a state evaluator, or an oracle solution.
4. **Variants.** Real history (revert the fix) or synthetic injection (mutate the code). Combining small bugs gives harder variants.
5. **Execution validation.** Keep a variant only if the reference check tells it apart from the original, and unrelated checks still pass.
6. **Instruction.** Write the human-facing text from the *expected behaviour*. State the outcome, not the steps.
7. **Human screening.** Score for underspecification and unfair checks; drop anything flagged.
8. **Difficulty and metadata.** Record steps, depth and time to solve.
9. **Freeze and split.** Pin versions; hold out by repo or template, not by instance.
10. **Report the funnel.** Publish how many candidates survived each stage.

## 3. Our adaptation: test → QA case pipeline

### Step 0: choose apps

Admit an app only if all of these hold:

- Builds from a pinned commit with a permissive licence.
- Runs **offline** without login, or has a demo/fixture mode.
- Its instrumented and unit tests mostly pass on our emulator image. Use SWE-smith's bar: over 80% pass.
- State can be seeded without the UI: database, backup import, content provider, or files.
- Has tests covering user-visible behaviour, not only parsers and utilities.

### Step 1: mine behaviour specs from the tests

Parse every test into **setup → action → assertion** and classify it:

| Test kind | Example | Use |
|---|---|---|
| UI test (Espresso / Compose) | OpenTracks `EspressoDeleteTrackTest` | Best source: the behaviour is reachable through the UI by construction |
| Service / DAO integration test | Tasks.org `TaskDeleterTest.dontDeleteReadOnlyTasks` | Strong spec; needs a UI reproduction path (Step 3) |
| Screenshot test (Roborazzi / Paparazzi) | Now in Android | Visual-layout and presentation buckets |
| Pure unit test (parsers, formatters) | date and title parsers | Use only when the result reaches the screen |

Map each spec to one primary bucket (record integrity, persistence, action side effects, navigation, control reachability, visual layout, presentation, permission, success-signal truth).

### Step 2: generate fault variants

Use three sources, kept separate in metadata because they answer different questions:

1. **Mutation of code the test reaches.** Use MDroid+ Android operators (GUI listener, view visibility, intent extras, string resources, SQL) and SWE-smith-style AST edits (invert if, remove condition, change constant, remove assignment). Optionally have an LM write a "plausible developer mistake" in the function under test.
2. **Reverted real fixes.** Find commits that fixed a user-visible bug and added or changed a test, then revert only the fix. These are natural faults (Defects4J / SWE-smith "PR mirror").
3. **Combined faults** for harder cases, only after single faults are validated.

Keep a variant only if:

- The app builds.
- The target test fails (the analogue of `FAIL_TO_PASS`).
- Every other test still passes (the analogue of `PASS_TO_PASS`). This keeps the fault local and the app usable.
- Its test-failure pattern isn't a duplicate. Equivalent mutants are dropped.
- Flaky tests are excluded: run each test several times on both builds, as Defects4J does.

### Step 3: prove the fault shows in the UI

A failing test proves the build is wrong. It doesn't prove a tester could see it.

- **UI tests:** visibility follows from the test; record the screen where the assertion fires.
- **Service tests:** a human or reference agent reproduces the behaviour through the UI once on each build. Record the screens and UI tree where control and fault differ. No visible difference means the case is rejected.

Our existing fault-visibility review covers this; it becomes required for admission.

### Step 4: write the natural-language test

- Draft from the **control** behaviour only: test name, assertion and the app's UI labels. Never draft from the mutation diff. SWE-smith writes issue text from the diff, but for us that would leak the fault to the actor.
- Control and fault get **the same text**.
- State the acceptance criterion as a user-visible outcome, with no step-by-step tutorial (Terminal-Bench's rule).
- An LM may draft; a human checks it.

### Step 5: oracles (hidden from actor and Checker)

- **Build oracle:** the target test's result on that build. It is developer-written, deterministic, and decides which variant is faulty.
- **State oracle:** device or database predicates after the run, including protected state the agent must not change.
- **Evidence:** the recorded screens from Step 3, used to check whether the agent's verdict cites the real symptom.

None of these is independent proof of *why* the agent decided. That stays a separate, model-reported layer.

### Step 6: human screening (SWE-bench Verified style)

Score each case 0–3 on:

- Is the criterion specific enough for a single correct verdict?
- Is the symptom visible within the allowed actions?
- Could a reasonable tester read the faulty behaviour as intended?
- Does the check reject valid evidence?

Drop anything scored 2 or higher on any axis, and keep the scores.

### Step 7: difficulty metadata

Record:

- Screens from launch to the symptom
- Whether a relaunch or rotation is needed
- Text versus visual symptom
- Reference-run step count
- Fault source (mutation, reverted fix, combined)

### Step 8: freeze and split

Pin the app commit, APK hashes for both builds, emulator image, seed data and test commit. Hold out whole apps and whole source test files. Re-run validation (Step 2) whenever the emulator image changes.

### Step 9: publish the funnel

Report per app: specs mined → mutants generated → built → target test fails → other tests pass → not flaky → visible in UI → passed screening. This is the honest coverage number, in place of a template-multiplied case count.

### Step 10: record the symptom signature and the guidance prompts

For each admitted pair, store:

1. **Symptom signature** (from Step 3): screen identity, the UI-tree nodes or state values that differ between builds, and the earliest reference step where the difference is visible. The detection score (§0.2) matches flags against this.
2. **Three prompts**, one per guidance level (§0.4): the Step 4 criterion, a feature-area hint, and the open "test this app" prompt. Each is the same on both builds.
3. **Step budget** per guidance level, set from the reference run (for example, 3× its step count).

Signatures, budgets and build labels stay out of the actor's and Checker's context.

### Mobile-condition faults

Mobile QA differs from web or desktop QA mostly in lifecycle and device conditions, and app test suites rarely cover these. Add a second fault family that targets them:

- **Lifecycle:** state lost on rotation or process death (e.g. remove a saved-state write); duplicate actions after backgrounding.
- **Permissions:** behaviour when a permission is denied or revoked mid-session.
- **Connectivity:** offline save silently dropped; stale data after reconnecting.
- **Display settings:** clipped text at large font scale; unreadable contrast in dark mode; broken layout in a right-to-left locale.

Validate these with the same rule, but the "test" is a harness script: apply the condition on both builds and compare state or screenshots. Android's core app quality guidelines list the expected behaviours to check (state preservation, orientation, back navigation, visual quality). [Android core app quality](https://developer.android.com/docs/quality-guidelines/core-app-quality)

## 4. Worked example (planned, not built)

**Source.** Tasks.org `TaskDeleterTest.dontDeleteReadOnlyTasks`: creates a task with `readOnly = true`, calls `markDeleted`, asserts the task is **not** deleted. Tasks.org is the `org.tasks` app AndroidWorld already installs, so seeding and DB-reading code can be reused.

- **Fault.** Remove the read-only guard in `TaskDeleter` (an AST "remove condition" edit). Keep it if `dontDeleteReadOnlyTasks` fails and `markTaskAsDeleted` plus the rest of the suite pass.
- **Visibility.** Seed a read-only task, as from a shared CalDAV list, through the database. On each build, try to delete it in the UI and record the result: control keeps it, fault removes it.
- **NL test (same for both builds).** "The task 'Quarterly report' comes from a read-only shared list. Check that it cannot be deleted from the app: after trying to delete it, it must still appear in its list."
- **Oracles.** Build oracle = that test's result. State oracle = `isDeleted` is still false for that task id, and other tasks are unchanged.
- **Symptom signature.** Task list screen for the shared list; on the faulty build the 'Quarterly report' row is gone after the delete attempt, and `isDeleted` flips to true.
- **Scoring one model run pair.**
  - Faulty build: `DEFECT` flagged on the task list after the row disappears → catch. `NO_DEFECT` → miss.
  - Correct build: `NO_DEFECT` → correct clear. `DEFECT` → false alarm.
  - Pair score is 1 only if both runs are right.
- **Guidance levels.** Directed: the NL test above. Feature hint: "Test task deletion." Open: "Test this app for defects."
- **Mobile-condition variant.** A separate pair whose fault only shows after rotating the device or killing the process right after the delete attempt.

## 5. Candidate apps

File counts below come from each repository's default branch, counted on 2026-10-31 with the GitHub tree API. They count `androidTest/` and `test/` source files. The screenshot column is a filename heuristic and also catches store screenshots, so treat it as a lead, not a measurement.

| App | In AndroidWorld | androidTest files | unit test files | Notes |
|---|---|---:|---:|---|
| Tasks.org (`tasks/tasks`) | yes (`org.tasks`) | 75 | 58 | Mostly service/DAO behaviour tests; offline use works. **First wave** |
| OpenTracks | yes | 61 | 0 | Has Espresso UI tests (delete track, edit recording, filters). **First wave** |
| Pro Expense | yes | 5 | 18 | Thin tests; keep it on the state-mutation track |
| Markor | yes | 0 | 20 | Unit tests only |
| Fossify Calendar | fork of Simple Calendar Pro (AndroidWorld pins the original) | 4 | 0 | Thin tests |
| Retro Music | yes | 0 | 0 | No tests |
| Now in Android | no | 13 | 52 | Compose UI and Roborazzi screenshot tests; demo flavour folders present. **Visual buckets** |
| AntennaPod | no | 27 | 91 | Mature app; feeds need network, so needs local fixtures |
| Amaze File Manager | no | 16 | 183 | Local files only; good for action side effects |
| Wikipedia | no | 30 | 77 | Network-dependent |
| Nextcloud | no | 166 | 89 | Needs a server fixture |
| Pocket Casts | no | 77 | 400 | Needs account/network |
| Firefox (`firefox-android`) | no | 275 | 1,232 | Very large; browser-specific |
| DuckDuckGo | no | 112 | 1,821 | Browser; network-dependent |
| Signal / Element X | no | 91 / 1 | 885 / 1,167 | Need accounts; Element X has many screenshot tests |

Suggested order:

1. **Tasks.org and OpenTracks.** Already in AndroidWorld; offline; real behaviour tests.
2. **Now in Android.** Visual and presentation buckets via screenshot tests.
3. **Amaze, then AntennaPod.** Local fixtures. Network or account apps only after a backend fixture exists.

## 6. Risks to track

- **Equivalent or invisible mutants.** Step 3 removes them; report the rejection rate.
- **Flaky instrumented tests on emulators.** Repeat runs before admission; exclude flaky tests, as Defects4J does.
- **Contamination.** Public repos and tests may be in model training data. Synthetic mutants are new, but reverted real fixes may be memorised; report the two fault sources separately.
- **Over-literal criteria.** Text drafted from tests can describe code-level behaviour a tester can't see. Screening axis 1 catches this.
- **Spec drift.** A test encodes one developer's intent. Where the UI suggests another reading, mark the case ambiguous instead of forcing a verdict.

## 7. Agent setup for scoring

Established benchmarks separate *model* comparison from *agent-system* comparison:

- SWE-bench runs every model in the same minimal mini-SWE-agent loop for its "Bash Only" model comparison, and accepts any system on its main leaderboard. [SWE-bench Verified](https://www.swebench.com/verified.html)
- Terminal-Bench built Terminus 2 as "a neutral testbed for comparing model performance", while its leaderboard ranks model–agent pairs. [paper](https://arxiv.org/abs/2601.11868)
- AndroidWorld reports one reference agent (M3A) across base models and observation types. [paper](https://arxiv.org/abs/2405.14573)
- HAL runs a standardised harness across benchmarks and reports cost next to accuracy. [paper](https://arxiv.org/abs/2510.11977)

### Primary track (official score): one model, fixed reference agent

- **One model makes every call**, including context summaries. No helper models for grounding, summarising or reviewing.
- **A fixed, published loop** with prompts not tuned to any one provider. Artemis's Flash profile is the starting point.
- **UI-only action space:** tap, long-press, type, swipe/scroll, back, home, launch app, wait. Mobile-condition actions are harness-provided tools: rotate, background/foreground, kill and relaunch, toggle network, grant/revoke permission, change font scale or dark mode.
- **No privileged channels:** no shell, no `adb` commands, no database or content-provider reads, no logcat, no file access, no web search. A tester must find the defect through the app.
- **Two observation settings**, reported separately: accessibility tree only, and screenshot plus accessibility tree.
- **A fixed step budget** per guidance level (§3 Step 10). The final answer comes through the structured tool in §0.6.

### Systems track: any scaffold, reported as a pair

Multi-agent systems (including Artemis Pro) are allowed when reported as *model + agent*. They must use the same UI-only interface and disclose every model they call. Their scores are not mixed into the model ranking.

### Implementation (2026-10-31)

The Pro multi-agent loop and the Checker are removed; Flash is the only runner. `artemis/bench` implements the primary track:

- **Device server** (`artemis/bench/server.py`): the bench tool set over MCP — UI actions (`click`, `click_sequence`, `long_press`, `input_text`, `swipe`, `press_key`, `manage_app` with an exact package, `wait_for_delay`), `observe_screen`, the mobile-condition tools and `submit_verdict`. No shell, app-data or web access, and no model call on the device side. Each call is a numbered step; the harness records the screen after it. Observing is free; the step budget counts actions.
- **Grader** (`artemis/bench/grading.py`, stdlib only): §0.6 labels and scores from the run record and the hidden signature, with no model call.
- **Harbor export** (`artemis/bench/harbor.py`): one task per case, build and repeat, declaring the device server under `[[environment.mcp_servers]]` at an opaque slot URL, with the grader and signature in `tests/`. Harbor's integrated agents (`claude-code`, `codex`, …) run against it unchanged; their built-in web search is switched off with `disable_web_search`.
- **Reference agent** (`artemis/bench/flash.py`): Flash with `bench=True` drives the same server object in-process, binds exactly the bench tools, ends on `submit_verdict`, and turns off its step summarizer and history chunker so the model under test (the `operator` node) makes every model call.

Open items: validated cases with signatures (§3), and a Harbor `BaseAgent` adapter if the reference agent should also run under `harbor run`.
