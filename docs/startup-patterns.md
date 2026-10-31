# Startup patterns for the interpretability harness

Reviewed 2026-10-29 from public first-party websites and documentation.
Capabilities below are vendor-documented, not independently audited product results.
No private Zenact source, customer data, or internal architectural information was used.

## What we can adapt

| Company | Publicly documented pattern | Application to our harness |
| --- | --- | --- |
| [Zenact AI](https://www.zenact.ai/) | Plain-language journeys and checks, app-build testing, and reports containing video, screenshots, device context, and runtime logs. | Make the natural-language test and expected outcome the primary input. Produce a case-level evidence report that a researcher can inspect without rerunning the agent. |
| [Browserbase](https://www.browserbase.com/observability) | Live browser sessions, recorded replay, structured logs, and associated prompts. | Synchronize selected graph transitions, screenshots/video time, tool results, and the model input available at that moment. Adapt the pattern to Android. |
| [Laminar](https://laminar.sh/) | Transcript-style tracing, model/tool spans, screen recording, failure signals and clustering, and turning errors into eval cases. | Maintain an evidence-backed issue list across runs. Turn a reviewed failure into a saved regression case. Automated clustering remains a proposal until reviewed. |
| [Langfuse](https://langfuse.com/docs/evaluation/experiments/compare-experiments) | Side-by-side experiment comparisons with stable dataset/evaluator versions, per-case traces, and human scores. | Compare matched test IDs and criterion versions across conditions. Show regressions and missing cases, not only average scores. |
| [Patronus / Percival](https://docs.patronus.ai/docs/percival/debugging_overview) | Trace-level error detection and clustering, span-linked findings, and suggested fixes. | An insight card should point to a specific step and evidence span. A proposed root cause must remain labeled as a hypothesis until tested. |

Zenact is the closest reference for the user-facing test workflow.
Browserbase and Laminar inform the execution-inspection experience.
Langfuse informs repeatable comparisons. Patronus informs evaluated failure localization.
These are product-design recommendations, not claims about equivalent implementation or achieved quality.

## What the research adds

Replay answers what happened. Our next question is which controlled change affects the decision.
Combine the product patterns above with the [research-backed evaluation plan](agent-interpretability-research.md).

A proposed finding must include:

- The original test and criterion.
- The relevant step and observed before/after state.
- The actor's actual input and available actions, when recorded.
- The independent oracle result or explicit unknown status.
- The claimed mechanism and any supporting intervention.
- Other plausible explanations and missing evidence.

A generated narrative or a high model confidence does not satisfy this evidence contract.

## A startup benchmark that directly fits

Patronus released [TRAIL](https://www.patronus.ai/research/trail), a human-annotated benchmark for locating and categorizing errors in agent traces.
Its [paper](https://arxiv.org/html/2505.08638) makes failure localization measurable instead of assuming that a debugger's explanation is correct.
Adopt the annotation and scoring pattern on Android traces. Do not transfer its reported scores to our domain.

## Product flow

1. The user writes a test in natural language.
2. The harness preserves the text and extracts proposed checks without silently changing the requirement.
3. The agent executes against the connected app.
4. The report links verdicts to screenshots, state evidence, and execution results.
5. The graph reveals the executed route, revisits, failures, and uncertainty.
6. Optional analysis runs matched evidence/claim interventions on recorded contexts.
7. A reviewer can inspect a finding and save it as a regression test.

Reusable app/oracle adapters belong to the harness implementation.
Users must not need to write evaluation scripts or decision-model payloads.

## Priority and current gaps

| Priority | Feature | Current state | Completion evidence |
| --- | --- | --- | --- |
| P0 | Natural-language test execution | Composer runs the Flash loop; the Pro multi-agent loop and Checker were removed on 2026-10-31 | A connected-device end-to-end run preserves the original case and records checks |
| P0 | Case evidence report | Graph and step inspector exist | Every verdict has source links and an explicit independent-oracle status |
| P1 | Saved test library | Run history exists; stable test versions need work | Reruns share a test ID and immutable input/criterion version |
| P1 | Synchronized replay | Screenshot inspection exists | Selecting a graph edge seeks the corresponding recording and trace |
| P1 | Paired intervention results | Not built; the Jev comparison was removed | The harness verifies comparable recorded inputs and reports repeats and effect sizes |
| P1 | Reviewed failure localization | Not implemented | Held-out annotations and source-linked precision/localization measurements |
| P2 | Failure clusters into regressions | Not implemented | Reviewer-approved issues become versioned natural-language cases |

Cloud fleets, broad platform parity, and enterprise integrations are later infrastructure concerns.
They do not establish interpretability by themselves.
Do not repeat vendor speed, maintenance, or accuracy claims as our targets without a defined evaluation.

## How to use autoresearch here

Choose one research question and one product change per iteration.
Keep the task/evaluator versions fixed. Run an unchanged baseline and the candidate on matched cases.
Inspect individual failures and evidence validity before comparing aggregate scores.
Keep changes that improve held-out diagnosis or evidence quality without hiding unknowns or reducing useful coverage unnoticed.
Record inconclusive experiments. Do not force the expected story.
