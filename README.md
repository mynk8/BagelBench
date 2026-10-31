# Artemis QA eval harness

Can an AI agent be trusted as a QA tester? This harness measures it. An LLM agent tests real Android apps from a natural-language test and reports PASS or FAIL. We plant known faults in the app's data, and code reads the app's data before and after each run, so every verdict is scored against a known right answer.

The agent runtime is a fork of [Google Artemis](https://github.com/google/artemis); see [docs/upstream-provenance.json](docs/upstream-provenance.json) for the imported commit.

## How one run works

1. **Pick a case.** One matched pair from the eval set: a control (correct record, right answer PASS) or a fault (one field broken, right answer FAIL). Both variants use the same test text.
2. **Seed the app.** Code writes the case's records into the app's database on the emulator.
3. **Read before.** Code reads the records back to confirm the seed landed.
4. **Agent tests the app.** The Planner writes a checklist; each turn the Operator sees a screenshot and the screen's text, picks one action, and the Validator approves it. The agent ends with a verdict in its notes. A second model, the Checker, reviews the run and gives its own verdict.
5. **Read after.** Code reads the database again: are the target fields correct, and did nothing else change?
6. **Score.** The agent's verdict is compared with the data read. Outcomes: correct, wrong PASS, wrong FAIL, no decision.

Only step 4 involves models. Every screen, action, model call, dataset hash and code version is recorded under `traces/`.

## Eval set

600 matched pairs (1,200 cases) across nine buckets and three AndroidWorld apps: Simple Calendar Pro, Pro Expense and Broccoli. Code checks every pair: all controls come out correct and all faults come out broken. The record integrity bucket (150 pairs) runs live on the emulator.

| Bucket | What the fault breaks | Pairs |
|---|---|---|
| Record integrity | A saved field is wrong: typo, shifted date, cut text, deleted | 150 |
| Success signal truth | App says "Saved" but data is missing, wrong or doubled | 60 |
| Persistence | Data lost or doubled after restart, rotation or resume | 60 |
| Action effects | Cancel still saves, edit hits the wrong record, double save | 60 |
| Navigation | Back, search or reopen lands on the wrong screen or record | 60 |
| Control reachability | A button is hidden, disabled, offscreen or does nothing | 60 |
| Visual layout | Clipped text, overlap, keyboard covers a field, tiny targets | 60 |
| Presentation | Screen shows a stale, wrong or cut-off value | 60 |
| Permission state | Wrong behaviour when a permission is granted or denied | 30 |

Dataset files live in [apps/research_ui/datasets/androidworld/expanded_v1](apps/research_ui/datasets/androidworld/expanded_v1). Regenerate them with `uv run python apps/research_ui/scripts/generate_qa_buckets.py`; no model calls are made.

## Quick start

```bash
make install        # Python and UI dependencies
make emulator       # dedicated AndroidWorld emulator, see docs/androidworld-local-setup.md
make dev            # backend on :8000, research UI on :5173
```

Model keys go in `.env` (see `.env.example`). In the UI, **New run** runs selected eval pairs end to end; **Eval set** checks all 600 pairs offline; **Results** shows accuracy, wrong PASS, wrong FAIL, no decision and pair accuracy per model, bucket and app, with 95% Wilson intervals.

## Layout

| Path | What it holds |
|---|---|
| `apps/harness_server/` | FastAPI backend. Eval code is in `routers/research.py` and `services/qa_catalog.py`, `research_batch.py`, `research_trials.py`, `research_grounding.py` |
| `apps/research_ui/src/` | React research UI: runs, eval set, results, run detail |
| `apps/research_ui/datasets/` | Eval set and pilot manifests |
| `apps/research_ui/scripts/` | Device fixture bridge, dataset generator, pilot scoring and audits |
| `artemis/` | Agent runtime: planner, operator, checker, validator, graph, device control |
| `third_party/mobile_use/` | Vendored device-control layer (Apache-2.0, Minitap) |
| `scripts/` | Emulator launcher, AndroidWorld app setup, dependency installer |
| `docs/` | Research methods, evaluation design and setup notes |
| `experiments/qa-pilot/` | Pilot iteration log |
| `tests/` | Unit and integration tests |

## Docs

- [Evaluation method](docs/android-qa-evaluation-method.md) and [benchmark design](docs/android-qa-benchmark-design.md)
- [Pilot protocol](docs/qa-pilot-protocol.md) and [AndroidWorld setup](docs/androidworld-local-setup.md)
- [Interpretability research methods](docs/agent-interpretability-research.md) and [startup patterns](docs/startup-patterns.md)

## License

Apache-2.0. Upstream copyright notices are retained.
