# Android tasks in Harbor

Harbor task directories are the source format for this benchmark.
Bagel adds Android metadata through Harbor's existing extension points.
There is no JSON case format, export command, or generated task manifest.

The contract uses Harbor 0.25 and task schema 1.4.
Harbor permits arbitrary task metadata and supports separate verifier environments.
These features require no changes to Harbor itself.
See the official [configuration](https://docs.harborframework.com/tasks/configuration) and [separate verifier](https://docs.harborframework.com/tasks/separate-verifier) documentation.

## Task directory

```text
dataset/
└── <opaque-task-name>/
    ├── instruction.md
    ├── task.toml
    ├── environment/
    │   └── Dockerfile
    └── tests/
        ├── test.sh
        ├── android.toml
        └── signature.json
```

`instruction.md` contains the natural-language test and answer protocol.
Paired tasks use exactly the same instruction.
Task names and MCP slot identifiers remain opaque.

`task.toml` uses Harbor's native agent, environment, MCP, and verifier configuration.
The `[metadata.android]` table adds these public fields:

| Field | Meaning |
| --- | --- |
| `version` | Android contract version, currently `1` |
| `app` | App name |
| `app_package` | Exact installed Android package |
| `guidance` | `directed`, `feature_hint`, or `open` |
| `action_budget` | Positive action limit, enforced by the device server |

The `android` MCP server uses the `streamable-http` transport.
Its URL ends in `/t/<opaque-id>/mcp`.
The environment allowlist includes the device host and selected model API host.

## Private Android fixture

`tests/android.toml` contains host-only benchmark information:

```toml
version = 1
case_id = "private-pair-id"
build = "correct"
repeat = 1
validated = false
setup = []

[provenance]
app_commit = "pinned-source-commit"
apk_sha256 = "pinned-apk-hash"
emulator_image = "pinned-image"
```

The twin task uses `build = "faulty"` and the same case identifier and repeat.
Each case, guidance level, and repeat has exactly one correct task and one faulty task.
Both tasks share the instruction, app, action budget, and hidden symptom signature.

`setup` contains host-side argv commands for reset, installation, seeding, and setup readback.
The host runs these commands from the task directory before the first agent tool call.
Agents do not receive setup commands, build labels, pairing identifiers, or oracle data.

`validated` records a curator decision. It does not replace validation evidence.
A case requires validated APKs, repeatable setup, a visible symptom, and a working signature before this value becomes `true`.
The supplied template keeps this value `false`.

## Verification

Harbor uses `verifier.environment_mode = "separate"`.
Its verifier retrieves the reward from `/t/<opaque-id>/reward` on the trusted device host.
The host computes that reward from its own record and the hidden signature.
The grading rules remain in `bagel/benchmark/grading.py`.

The verifier configuration supplies two environment values:

```toml
[verifier]
environment_mode = "separate"
env = { BENCH_REWARD_URL = "http://device-host:8765/t/opaque-id/reward", BENCH_VERIFIER_TOKEN = "${BAGEL_BENCH_VERIFIER_TOKEN}" }
```

The token remains an environment reference in the task file.
Harbor resolves the token only for the verifier process.
The verifier writes the returned JSON to `/logs/verifier/reward.json`.
Grading makes no model calls.

## Scheduling and scoring

Each native task represents one scheduled build and repeat.
The current device host records one attempt per task endpoint.
Harbor runs these tasks with `--n-concurrent 1 --n-attempts 1`.
A fresh job uses a fresh run directory.

The scorer derives pair assignments directly from native task directories.
It requires no `slots.json` or `manifest.json`.
Missing trials remain explicit and earn no credit.
Duplicate reward files cause an error instead of replacing an earlier result.
Each dataset contains one guidance level, so different guidance levels never share an aggregate score.

## Template and validation

The template lives in `templates/android-harbor/`.
Task authors replace its placeholders and preserve the native Harbor directory format.
The assistant can construct these files from a natural-language case description.
Users do not need to write setup commands or grading code.

Before execution, run both validators:

```bash
harbor lint <task-dir>
uv run bagel bench validate-tasks <dataset-dir>
```

Harbor validates its native format.
Bagel validates the Android extension, private fixture, endpoint configuration, and matched pairs.
