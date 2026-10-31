# Evidence-grounded agent interpretability

Reviewed 2026-10-29. This document guides the harness and UI.
The methods below are published research methods or proposed adaptations. They are not validated results for Artemis.

## Research objective

A user describes a test and its expected outcome in natural language.
The agent executes the test. The harness records the environment, actions, observations, and verdict.
The researcher investigates which input or system component influenced a decision.

The immediate scope is behavioral and system-level interpretability.
Closed-model APIs do not expose the activations, circuits, or gradients required for mechanistic interpretability.
A screenshot establishes an observation. A self-report establishes that a statement was returned.
Neither a readable reasoning trace nor a plausible narrative independently establishes an internal cause.

## Primary papers and usable methods

| Work | Evidence and method | Adaptation for this harness |
| --- | --- | --- |
| [Turpin et al., 2023: Language Models Don't Always Say What They Think](https://arxiv.org/html/2305.04388v2) | Biasing input features can affect answers without acknowledgement in generated explanations. | Hold screen evidence fixed. Add or remove an Operator success claim. Measure verdict and action-distribution changes. |
| [Lanham et al., 2023: Measuring Faithfulness in Chain-of-Thought Reasoning](https://arxiv.org/html/2307.13702) | Tests truncate, corrupt, paraphrase, or replace returned reasoning to investigate its influence. | Where returned text can be replayed, compare its removal against content-preserving and length controls. Do not claim access to hidden reasoning. |
| [ERASER, ACL 2020](https://aclanthology.org/2020.acl-main.408/) | Separates agreement with human rationales from intervention-based rationale faithfulness. Uses sufficiency and comprehensiveness. | Remove a cited observation, or retain only cited observations, and measure effects on the same decision. Check that edited inputs remain valid. |
| [Walk the Talk?, ICLR 2025](https://www.microsoft.com/en-us/research/publication/walk-the-talk-measuring-the-faithfulness-of-large-language-model-explanations/) | Compares concepts claimed to influence an answer against effects estimated using counterfactual input changes. | Turn an explanation into testable claims about observed UI facts. Change one fact and evaluate predicted versus observed sensitivity. |
| [A Causal Lens for Evaluating Faithfulness Metrics, EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1496/) | Uses controlled faithful/unfaithful explanation pairs to evaluate the metrics themselves. Diagnostic performance varies by task and model. | Validate the insight evaluator against known injected failures and expert annotations before trusting its scores. |
| [TRAIL, 2025](https://arxiv.org/html/2505.08638) | Human-annotated agent traces support error categorization and step localization evaluation. | Label specific failing steps and error categories. Score localization, category accuracy, and their joint correctness on held-out runs. |
| [AgentAbstain, 2026](https://arxiv.org/html/2607.10059) | Pairs tasks where acting is appropriate with minimally changed tasks where abstention is appropriate. | Pair a verifiable outcome with missing or conflicting evidence. Reward correct action and appropriate deferral together. |
| [Faithfulness as Information Flow, 2026](https://arxiv.org/html/2605.24286) | Distinguishes sufficiency, completeness, and necessity, including methods that require internal model access. | Use the distinctions to organize questions. Its attention/gradient experiments do not transfer directly to closed provider APIs. |

These works motivate different measurements. A good task score does not certify faithfulness.
The CoT studies primarily concern reasoning tasks, not Android navigation. Our transfer is a research hypothesis.
Input deletion can create unnatural examples or leave redundant evidence. A null effect is not proof that an observation was unused.
A changed decision can reflect several mechanisms. Isolated changes and repeated trials narrow the claim.

## Execution benchmarks provide independent outcomes

[AndroidWorld](https://github.com/google-research/android_world) combines natural-language tasks with initialized environments and state-based success checks.
Borrow its separation of task instructions from the outcome oracle.
The harness team implements reusable app adapters. Test authors still write natural language, not evaluator scripts.

[VisualWebArena](https://github.com/web-arena-x/visualwebarena) provides visually grounded tasks with execution-based evaluation.
Use it as a reference for web tasks and visual failure cases, not as evidence that an Android test passed.

[AgentDojo](https://github.com/sequrity-ai/agentdojo) tests agent behavior under changes to untrusted tool content.
Its useful design pattern here is to change one information source and observe downstream behavior.
Prompt-injection resistance and explanation faithfulness remain distinct evaluations.

## Evaluation families

### 1. Independent outcome and verdict audit

Use a held-out environment oracle or independently reviewed evidence.
Record the user criterion verbatim. Separate a screen's current appearance from durable app state.
An actor's note, a second model's agreement, and a Checker PASS cannot serve as the independent oracle.
Without a defensible oracle, truth is unknown and false PASS cannot be established.

Report false PASS among oracle-fault cases and false FAIL among oracle-pass cases.
Report INCONCLUSIVE among scorable cases, decisive coverage, and error among decisive judgments.
Keep missing runs, infrastructure errors, and unknown truth separate. Show counts and denominators.

### 2. Evidence and claim sensitivity

At one recorded decision boundary, freeze the model version, goal, candidate set, option order, instructions, and observations.
Vary only the declared intervention. Preserve the full request before and after.

Useful interventions are claim removal, authoritative-looking success claims, a cited observation's removal, and conflicting evidence.
Add content-preserving paraphrases, irrelevant-text edits, and repeated unchanged requests as controls.
Measure action flips, verdict flips, and shifts in probability assigned to the same semantic option.
For distributions, total variation is a useful bounded descriptive effect size.
Neither this metric nor one changed answer alone establishes a general causal explanation.

### 3. Criterion specificity

Compare a vague condition with an explicit observable condition on the same recorded state.
Keep the original user intent separate from the rewritten criterion. Do not silently replace it.
This intervention changes the task specification. A changed decision is not automatically an agent error or unfaithfulness.
Show the criterion diff next to the outcome evidence.

### 4. Failure localization and insight quality

Build an expert-reviewed sample with known failure steps and categories.
Seed faults only in a separate controlled evaluation environment and retain unmodified controls.
Measure exact step localization and a predeclared tolerance, category precision/recall, and joint correctness.
Compare trace-only review against trace plus generated insights with reviewers blinded to the condition where feasible.
Measure correct diagnosis and time to diagnosis, not just perceived explanation quality.
An LLM can propose labels, but its agreement with itself is not ground truth.

### 5. Action versus deferral

Pair an actionable task with a minimally changed task requiring clarification or more evidence.
Score the pair jointly. Always acting and always abstaining must not receive a good paired score.
The harness can generate candidate variants, but a reviewer or a reliable oracle must validate their semantics.

### 6. Decision-model calibration and option controls

For any decision model, preserve the full returned distribution, actual model version, candidate definitions, and option order.
Use semantic action IDs when comparing reordered options. Test reordered and renamed options separately.
Measure Brier score or log loss only with independently labeled targets and a defensible choice set.
When multiple actions are valid, use a set-valued target or explicitly defined utility. Do not invent a unique gold action.
Confidence is not task correctness. Report calibration by task family and abstention coverage.

## Research protocol

Start with a small reviewed discovery set, then freeze a separate held-out evaluation set.
Split by task family or session so neighboring steps cannot leak across splits.
Predeclare scoring rules, exclusion rules, repetitions, and the improvement criterion.
Store model, source, prompt, dataset, oracle, and evaluator versions.
Randomize condition order and use matched resets or snapshots for environment-level comparisons.
Use paired confidence intervals clustered by task/session. A provider seed is not a guarantee of determinism.
Report all scheduled cases, failures, and uncertainty. Single-pair pilots support debugging, not broad performance claims.

A replay through a separate decision model investigates that model's response to the context.
It does not explain the original Operator if a different model or candidate generator acted originally.
Action trajectories require environment resets to study downstream path effects, not just isolated API replays.

## UI evidence levels

Each insight needs a source location and one of these labels:

- Observed: linked screen, UI-tree record, tool result, or independent outcome.
- Agent-reported: returned explanation or summary.
- Replay sensitivity: a documented intervention changed a measured decision.
- Hypothesis: a proposed mechanism not yet tested.
- Unknown: required evidence or alternatives are missing.

The graph shows the executed path. Show alternatives only when captured prospectively or explicitly labeled as replays.
A citation to a screenshot does not establish that the original model received or used that screenshot.
Record exposure and temporal provenance independently.

## Next implementation priorities

1. Saved natural-language test cases with stable IDs, acceptance criteria, and versions.
2. A report that links each verdict to observations, oracle status, and the relevant graph location.
3. Recorded-input validation for paired comparisons, including candidate order and model version.
4. Reviewer annotations for failure step, category, evidence sufficiency, and disagreement.
5. A held-out paired evaluation runner behind the UI, with coverage and failure accounting.

These are roadmap items. The current graph and test composer cover only part of them.
