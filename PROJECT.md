# Artemis research harness

The project measures whether LLM agents can be trusted as Android QA testers. Agents run natural-language tests on real apps; planted faults and code that reads app data give a known right answer for every verdict.
See the [README](README.md) for the run loop and layout, [the harness guide](docs/harness-research.md), [research methods](docs/agent-interpretability-research.md), and [startup patterns](docs/startup-patterns.md).

Karpathy's autoresearch is the development workflow for improving the harness ([pilot log](experiments/qa-pilot/program.md)).
The working branch is `feat/harness-navigation-decisions`.

The original Google source is preserved on `upstream-snapshot`.
[Source provenance](docs/upstream-provenance.json) identifies the imported commit.

Execution success, verdict correctness, and explanation faithfulness remain separate measurements.
