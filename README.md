# BagelBench

Bagel gives external agent harnesses, such as Codex and Claude Code, tools to test Android apps.
The agent receives a natural-language test and uses the same device interface as every other agent.
Its verdict is scored against verified ground truth that stays hidden throughout the run.

BagelBench is derived from [Google Artemis](https://github.com/google/artemis). Upstream and vendored license notices remain intact.

Harbor starts the agent and runs the verifier. Bagel supplies the Android device service, evidence recording, grading, and aggregate scores.
There is no browser application or built-in agent loop.

## Execution

```text
Native Harbor task → Harbor agent → Bagel MCP tools → Android device
                                          ↓
                                 numbered actions + screens
                                          ↓
                         private deterministic grader → reward
```

The benchmark tools expose screen observations, UI actions, controlled device conditions, and one final verdict.
They do not expose a shell, app databases, private setup commands, or ground-truth labels.
The device service and grader make no model calls.

PASS means the tested behavior satisfies the test. FAIL means the agent detected a defect.
The current wire protocol represents these as `NO_DEFECT` and `DEFECT`; `INCONCLUSIVE` records an undecided run.
A defect verdict must reference a recorded step.

The current grader matches hidden screen signatures against the harness record.
Navigation, layout, screenshot comparison, and data-integrity graders are planned extensions.
They are not implemented by the current signature grader.

The [capture journal and evaluator plan](docs/capture-journal-evaluation-plan.md) records the agreed approach and open questions for all nine QA buckets.

## Run a benchmark

```bash
uv sync --dev
uv run bagel doctor
# Validate an authored, verified pair of native Harbor tasks.
uv run bagel bench validate-tasks <dataset-dir>
# Set BAGEL_BENCH_VERIFIER_TOKEN in the host and Harbor environments.
uv run bagel bench serve --tasks <dataset-dir> --serial emulator-5554 \
    --host 0.0.0.0 --public-host <device-host-ip>
# In another terminal, with Harbor installed:
harbor run -p <dataset-dir> -a claude-code -m anthropic/<model> \
    --n-concurrent 1 --n-attempts 1 --ak disable_web_search=true
uv run bagel bench score --tasks <dataset-dir> --results <harbor-job-dir>
```

Use a device host address reachable from Harbor's containers. Configure it in each task's MCP URL and network allowlists.
Keep credentials in ignored `.env` files. Harbor controls agent credentials; Bagel does not configure model providers.

Use a fresh run directory and one trial at a time per device. Each authored task represents one build and repeat.

## Author tasks

Tasks use [Harbor's native layout](templates/android-harbor), with Android metadata and private verifier files.
There is no conversion or export step.
Read the [Android task contract](docs/android-harbor-tasks.md) before authoring a pair.

The template is unvalidated. No validated native task pairs are included yet.
Older AndroidWorld datasets remain under `apps/research_ui/datasets/` as research artifacts.
Their checks do not establish that a native Harbor task has been validated.
Dataset preparation and audit scripts live under `scripts/androidworld/`.

## Code

| Directory | Responsibility |
|---|---|
| `bagel/benchmark/` | Tool policy, private task slots, evidence, grading, scoring |
| `bagel/device/` | Android actions, observations, conditions, drivers and recording |
| `bagel/transports/` | MCP tools and HTTP task hosting |
| `bagel/integrations/harbor.py` | Read and validate Android extensions to native Harbor tasks |
| `bagel/interfaces/cli/` | Serve, validate, grade, score, diagnose, manage the device helper |
| `bagel/runtime/` | Device endpoints, locks, helper lifecycle and awake leases |
| `bagel/diagnostics/` | Host tooling and device readiness checks |
| `templates/android-harbor/` | Native task authoring template |
| `scripts/androidworld/` | Dataset preparation and audits |

The [structure guide](docs/codebase-structure.md) describes dependencies and retained legacy utilities.
Historical research documents, datasets, and run evidence remain available.
They retain their original Artemis names and schema identifiers. The existing emulator and helper APK retain their Android identifiers.
The Python package and CLI are `bagel`; the distribution name is `bagelbench`.

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright --project pyright-core.json
uv run python scripts/dev/check_import_names.py
```

Apache-2.0. Upstream copyright and vendored license notices are retained.
