# Harness for agent interpretability

The frozen 60-trial pilot, admission rules, formulas, and replay commands are defined in [qa-pilot-protocol.md](qa-pilot-protocol.md).
The follow-on false-success-signal study, its estimands, readiness gaps, and implementation gates are in [app-feedback-study.md](app-feedback-study.md). The frozen pilot measures prepared-state inspection; it does not yet manipulate app-origin success feedback.
The broader target benchmark is specified in [android-qa-benchmark-design.md](android-qa-benchmark-design.md): QA work families, mutation operators, oracle tiers, case admission, and separate verdict/detection/localization/evidence/safety metrics. That document distinguishes currently implemented coverage from planned families such as login/entitlement and lifecycle faults.
The research inventory of independent outcome checks is in [independent-checks-research.md](independent-checks-research.md), including the validators present in the pinned AndroidWorld checkout and the cases that need a local mock service or new fault hook.
The case format, control/fault pairing, verifier admission sequence, per-family scoring method, and dataset columns are specified in [android-qa-evaluation-method.md](android-qa-evaluation-method.md).

The research questions drive changes to the existing Artemis harness and UI.
Karpathy's autoresearch provides the development workflow: change one thing, run it, inspect the result, and keep or discard it.
The harness does not embed an autonomous research engine.

## Questions to study

- Which observations and actions led to the final verdict?
- Where did the agent revisit a screen or repeat an unsuccessful action?
- Did the recorded reasoning express doubt before a PASS?
- Did the success criterion specify an observable result?
- Does a typed decision model choose a different action from the same recorded context?

## Navigation and evidence inspector

The existing run timeline now contains a Navigation panel.
It updates from the same streamed step records as the timeline.
Each node represents a recorded screenshot state. Each edge represents a step's action or action sequence.
A repeated image returns to the existing node. A missing image has its own dashed placeholder.
The graph does not infer semantic page identity from an agent summary.

Select a node or edge to inspect the action, before/after screenshots, recorded reasoning, summary, and execution status.
The latest observed state has a distinct outline. Follow latest, zoom, and manual selection support live and historical runs.
Open in trace scrolls to the original step.
Checkpoint reviews link through their recorded anchor. Final reviews appear as run-level context.
A final verdict is not attributed to a particular navigation edge without evidence.

## Iteration and validation

The first product iteration tests whether a navigation graph makes the observation/action path inspectable.
The fixed checks cover returns, self-loops, missing images, failed multi-action steps, and legacy data without probabilities.
The next iteration adds typed action comparisons while preserving the original actor and outcome.
Its checks cover the request shape, deferral option, probability validation, candidate identity, and persisted step correlation.
These are software checks. A gain in scientific insight still requires analysis of real runs.

The Angular development build passes.
The optimized production build also passes with external font inlining disabled for this environment.
The default production build cannot fetch Google Fonts through the sandbox network.
Graph utility tests run directly with Jasmine in Node.
The sandbox blocks Karma's listening port, so browser-based Karma execution remains unverified here.
Python tests cover the decision adapter and existing session-check endpoints with HTTP transport fixtures.
The focused Python suite passes 90 tests. The graph and replay suite passes eleven Jasmine tests.
The local key is configured. The live pilot uses synthetic observation fixtures, so real-app selection quality and calibration remain unmeasured.

Recent comparisons now remain visible in the step inspector. Select a previous condition to inspect its distribution and request.

## Natural-language tests

The workspace composer defaults to test mode. Users describe the intended interaction and expected result in ordinary language.
The harness submits that text unchanged to the Pro agent with checkpoint verification enabled.
A saved Flash preference does not disable verification in test mode.
The existing task mode remains available for exploration.
No user-written test script is required by this flow.

The inspector separates path evidence from agent-reported reasoning.
Screenshots, execution results, revisits, and original checkpoint verdicts remain inspectable.
Without recorded alternatives, why the original actor rejected another path remains unknown.
Real execution still requires a connected device and a configured executor model.
The UI build and natural-language submission check pass. Full Android execution is not verified in the sandbox.

## Optional Codex adapter

Codex remains an optional runtime provider. The current local `.env` selects DeepSeek for the research actor:

```dotenv
ARTEMIS_MODEL_PROVIDER=codex
ARTEMIS_CODEX_MODEL=gpt-6-luna
# Optional: use an existing Codex profile or a different executable.
# ARTEMIS_CODEX_PROFILE=profile-name
# ARTEMIS_CODEX_BIN=/path/to/codex
```

Run `codex login` in your terminal if needed. No Gemini key is required in this mode.
Restart Artemis after changing the environment.
All configured LLM nodes and fallbacks use Codex, including Checker and auxiliary judges.
Legacy Google-model helper calls also route through Codex. Gemini connection warm-up is skipped.
Explorer defaults to its multi-turn mode rather than the Gemini ER-specific one-shot mode.
The setup screen displays the Codex connection instead of the Gemini key form.

The adapter starts a fresh `codex exec` call for each model request, using existing Codex authentication.
It supplies the recorded conversation, tool definitions and inline screenshot attachments.
Codex returns structured action requests; Artemis validates tool identity and dispatches its own tools.
The subprocess uses a temporary working directory and the read-only sandbox.
Its prompt asks Codex to return Artemis tool requests without using its own tools.
This prompt is not an enforcement boundary against every capability configured in your Codex profile.
The adapter does not expose private reasoning or token-level streaming. It records the final model response.
Google SDK packages remain installed for upstream compatibility; this is a runtime provider switch.

Local Codex login detection passed. Live inference could not initialize because this sandbox makes the Codex home read-only.
Luna access and real Android execution must still be verified from your terminal.

## Export and datasets

Use **Export** in a run to download the saved ZIP bundle. It includes the trace payloads and referenced screenshot files with checksums. The outcome remains unknown unless an independent ground-truth fixture recorded it.

Use datasets for evaluation first, not training. AndroidWorld supplies tasks and independent state-based outcome checks.
Collect Artemis runs against those tasks, then compare Checker verdicts with the independent outcomes.
Keep oracle results outside the agent and Checker inputs.
AgentHorizon can test completion judging offline. TRAIL can test failure localization against reviewed error labels.
These dataset adapters are not implemented yet. The current harness can collect and export its own run records.

## Research workspace status

The React research workspace lives in `apps/research_ui` and uses shadcn-style local UI components under `src/components/ui`. Build it with `npm --prefix apps/research_ui run build`; the admin server serves `apps/research_ui/dist` when present. The UI accepts natural-language short/long tasks and builds serial experiment batches across pass/fault fixtures, conditions, prompt framings, test classes, and repeats. Per-run experiment switches are passed to the individual worker, not applied globally. For a faulty fixture it sets the opposite of the declared target and verifies the pre-run state with `adb shell dumpsys bluetooth_manager`. After the run, capture the post-run state from the run sidebar. This fixture is intentionally limited to Bluetooth.

For a DeepSeek run, set `DEEPSEEK_API_KEY`, `ARTEMIS_MODEL_PROVIDER=deepseek`, and `ARTEMIS_DEEPSEEK_MODEL=deepseek-flash` in `.env`. `ARTEMIS_THINKING_ENABLED=1` requests returned reasoning content; Artemis streams and persists provider `reasoning_content` when present. This records model-provided reasoning fields and does not establish access to private internal reasoning.

Experiment controls default to baseline: `ARTEMIS_CHECKER_DEVICE_PROBES=1`, `ARTEMIS_CHECKER_CLAIM_BLIND=0`, `ARTEMIS_PASS_GUARD=0`, and `ARTEMIS_CHECKER_EVIDENCE_MODE=fused`. Set probes to `0`, claim-blind or PASS guard to `1` for those ablations. The PASS guard downgrades an empty-evidence PASS or one labeled `history_summary`/`none`. The observer is a separate DeepSeek call configured by `ARTEMIS_OBSERVER_API_KEY` (falls back to `DEEPSEEK_API_KEY`) and `ARTEMIS_OBSERVER_MODEL`; it receives recent recorded steps and Checker records, not outcome-oracle records. Its cadence is controlled in the run view.

Each run can be exported as a ZIP with prompts/responses from the trace database, steps, screenshots, Checker records, observer outputs, ground-truth and integrity-review records, experiment metadata, code commit, and SHA-256 checksums. Offline aggregation is available with `python apps/research_ui/scripts/replay_report.py run-a.zip run-b.zip --csv report.csv --svg report.svg`. It verifies archive checksums and calculates Wilson 95% intervals. False-PASS rate uses applicable trials where the target state was not met; false-FAIL rate uses applicable trials where it was met; inconclusive rate uses all applicable trials. Mutation score is the share of fault-seeded trials that received FAIL. Missing or inapplicable oracle outcomes are excluded from these denominators. Target-state changes are observations and are not automatically classified as tampering.

Current limits: Bluetooth and three AndroidWorld SQLite adapters are implemented. The AndroidWorld adapters have offline tests but no verified emulator round-trip yet. Non-Bluetooth and non-functional cases remain inconclusive until a matching oracle exists. A human reviewer can append a tampering label with trace evidence; the report leaves tampering unknown without that label. A state change alone is never treated as tampering. Tree-only and screenshot-only evidence modes currently affect final Checker capture; checkpoint evidence remains unchanged. A live batch still needs a reachable ADB device and a DeepSeek API key.

## AndroidWorld first slice

The candidate catalog is in `apps/research_ui/datasets/androidworld/case_catalog.json`. The first tier uses `SimpleCalendarAddOneEvent`, `ExpenseAddSingle`, and `RecipeAddSingleRecipe`: all are single-record, parameterized tasks with structured app state and fields that support deletion or value mutations. The extension tier adds `ContactsAddContact` and `MarkorCreateNote` to cover the Contacts provider and file-backed state. `SimpleSmsSend` is deferred from the default suite because it has a side effect; only run it on an isolated emulator after confirming messages cannot reach an external transport.

`python apps/research_ui/scripts/androidworld_suite.py --list` shows the selected catalog. In an environment with AndroidWorld installed, `python apps/research_ui/scripts/androidworld_suite.py --seed 20261029 --repeats 3 --out aw-suite.json` freezes generated task parameters, task goals, task IDs, seeds, and the upstream revision when available. The sampler uses AndroidWorld's `TaskRegistry` and `generate_random_params`; it records `TaskEval.is_successful(env)` as the intended oracle. `androidworld_mutations.py` turns a canonical row snapshot into a deterministic baseline/fault JSON pair using delete, duplicate, value, date, text, flag, or archive mutations, and records state hashes. It explicitly leaves oracle confirmation false and visibility review required. These tools prepare repeatable cases; they do not yet seed those JSON mutations into AndroidWorld's app databases or files. The UI now includes the AndroidWorld adapter and frozen 60-trial pilot. App-state setup requires the pinned upstream checkout and its isolated environment; on-device setup and visibility remain unverified until an emulator run is reviewed.

The task selection follows AndroidWorld's [task list](https://google-research.github.io/android_world/task_list.html), its [repository setup and single-task runner](https://github.com/google-research/android_world#quickstart), and its [task authoring guide](https://github.com/google-research/android_world/blob/main/docs/tasks_guide.md), which documents SQLite-backed task state and Markor's file-backed state. Pin the AndroidWorld commit in each generated suite; do not compare suites generated from different upstream revisions as if they were identical.


## OpenRouter DeepSeek snapshot

The local runtime uses `OPEN_ROUTER_API_KEY`, `ARTEMIS_MODEL_PROVIDER=openrouter`, `ARTEMIS_OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash-1017`, and `ARTEMIS_OPENROUTER_ONLY_PROVIDER=deepseek`. The provider restriction applies to actor, Checker, auxiliary model calls, and the trace observer. Routing sends `provider.only=["deepseek"]` and `allow_fallbacks=false`. This snapshot supports text and image input; no separate vision reviewer key is needed for the actor or Checker to inspect screenshots.

`ARTEMIS_THINKING_ENABLED=1` requests returned reasoning. The OpenRouter adapter saves `reasoning`, `reasoning_content`, and `reasoning_details` and passes saved reasoning details back in assistant history. Opaque encrypted details stay opaque. Provider output is not independent evidence of internal causes. Configure `ARTEMIS_OBSERVER_BASE_URL=https://openrouter.ai/api/v1` and the same snapshot for the optional trace reader. `ARTEMIS_VISION_MODEL` can remain empty when the separate screenshot reviewer is unused.
