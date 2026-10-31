# Project direction

This project is an agent interpretability research harness built on Artemis.
Keep this direction across tasks and context changes.

- Users create tests in natural language. The agent executes them through the real harness.
- Do not require users to write scripts, selectors, evaluation code, or decision-model request bodies.
- Use Karpathy's autoresearch workflow to improve the harness and UI. Do not build an autoresearch engine into the product.
- Ground insights in recorded observations, screenshots, action results, input provenance, and controlled interventions.
- Treat agent explanations and summaries as self-reports, not independent evidence or causal ground truth.
- Distinguish observed facts, model-reported claims, replay sensitivity, and untested causal hypotheses in the UI.
- Show unknown when alternatives, evidence, or an independent outcome oracle are missing.
- Preserve the original natural-language test, declared acceptance criteria, and experiment versions.
- Evaluate execution success separately from explanation faithfulness and failure localization.
- Keep outcome-oracle information (build labels, signatures, oracle results) outside every agent input during evaluation.
- A replay by a different model is not a record of why the original actor chose an action.
- Follow docs/agent-interpretability-research.md and docs/startup-patterns.md for sourced methods and priorities.
- Preserve secrets in ignored .env files. Never print or commit credentials.
