# AndroidWorld-derived QA pilot, version 1

This is a discovery pilot of verdict correctness on prepared app states. It does not measure app workflow execution, realistic software-bug prevalence, or explanation faithfulness. No device trial has been validated yet.

## Frozen design

Source: `google-research/android_world` commit `55ddaf5edc6f6c25673aed343907d5b9dca66f84`.
The immutable artifact is `apps/research_ui/datasets/androidworld/pilot_v1.json`. Its `suite_id` hashes the entire canonical manifest except the ID itself. Editing parameters, prompts, trial order, or definitions changes the ID.

| Family | Upstream task | Instances | Correct trials | Fault trials |
| --- | --- | ---: | ---: | ---: |
| Calendar record integrity | SimpleCalendarAddOneEvent | 10 | 10 | 10 |
| Expense record integrity | ExpenseAddSingle | 10 | 10 | 10 |
| Recipe record integrity | RecipeAddSingleRecipe | 10 | 10 | 10 |
| Total per condition and repeat | | 30 | 30 | 30 |

Seeds 42 through 51 generate ten instances for each family. Complete generated parameters are saved; execution loads those parameters rather than regenerating them. Trial order is shuffled with seed 42 and frozen. Conditions use the same order. There is no claim of randomized condition order or independent repeats.

Calendar fault distribution: 2 missing records, 4 wrong titles, 2 shifted dates, 2 truncated descriptions. Expense: 2 missing records, 2 wrong names, 4 wrong amounts, 2 truncated notes. Recipe: 2 missing records, 4 wrong titles, 2 truncated directions, 2 wrong servings. Calendar date shifts move both endpoints by one day, preserving duration. Every fault changes one declared semantic property.

The artifact contains 30 unique parameterized instances of three task families. It does not establish millions of valid tasks. Validation coverage must be reported separately from generation count.

## Exact state predicate

For instance i, let B_i be the rows before the expected target is inserted, T_i its expected target, and F_i its declared field list. Let S be the observed table rows.

`P_i(S) = 1` exactly when:

1. Every row in B_i remains unchanged, including multiplicity.
2. Removing B_i from S leaves exactly one target row.
3. Every field in F_i equals the corresponding field in T_i, with no fuzzy text matching.

Field lists are calendar: title, start time, end time, description; expense: name, amount, category, note; recipe: title, description, servings, preparation time, ingredients, directions. Amounts use cents. Calendar timestamps use Unix seconds in UTC; prompts also include readable UTC times. The oracle covers the selected table, not all application or device state.

Control state C_i must satisfy `P_i(C_i)=1`. Fault state `M_i(C_i)` must satisfy `P_i(M_i(C_i))=0`. AndroidWorld's own oracle result is recorded separately. A seed that fails either the correct-state check or intended fault-state check cannot be counted as an agent failure.

Both variants receive exactly the same frozen prompt. The agent may navigate and search, but must not edit records. Variant, mutation details, observed rows, and oracle labels are excluded from that prompt.

## Admission and accounting

Every scheduled trial has a stable trial ID. Each observation records condition, model, and repeat. Duplicate observations for the same trial/condition/model/repeat are rejected; unknown trial IDs are rejected. A rerun requires a new repeat index.

A trial is admitted only when all of these are true:

- Setup was confirmed by the independent oracle and matches the scheduled variant.
- A human reviewer confirmed that the criterion is discoverable through permitted UI actions and recorded evidence. An initial screenshot alone does not prove this.
- The evaluated criterion exactly matches the frozen prompt.
- Pre-run and post-run truth are known and agree.
- The selected table's canonical state hash did not change during inspection.
- The agent returned PASS, FAIL, or INCONCLUSIVE and no execution error occurred.

Exclusion precedence: missing observation; missing/invalid fields; execution error; setup failure; unreviewed discoverability; criterion mismatch; changed protected state; admitted. The report publishes each count. Read failure is unknown, never INCONCLUSIVE by assumption. A state change is an observation, not proof of malicious tampering.

## Scores

Let F be admitted fault trials, C admitted correct trials, U their union, and D admitted decisive judgments (PASS or FAIL). Let indicator `[x]` be 1 if x is true, otherwise 0.

| Metric | Numerator / denominator |
| --- | --- |
| Fault detection / mutation score | `sum_F[verdict=FAIL] / count(F)` |
| False PASS | `sum_F[verdict=PASS] / count(F)` |
| False FAIL | `sum_C[verdict=FAIL] / count(C)` |
| Inconclusive | `sum_U[verdict=INCONCLUSIVE] / count(U)` |
| Decisive coverage | `count(D) / count(U)` |
| Error among decisive | `(false PASS count + false FAIL count) / count(D)` |
| Admission coverage | `count(U) / scheduled trials` |
| Protected-state change | `observed trials with changed state / trials with known change status` |

An instance pair is complete only when both variants are admitted for the same model, condition, and repeat. Pair success is `[control verdict=PASS AND fault verdict=FAIL]`. Paired accuracy is successful pairs divided by complete valid pairs. Always PASS, always FAIL, and always INCONCLUSIVE each score zero. Report the pair denominator beside the score.

A condition/repeat is eligible for ranking only when all 60 trials and all 30 pairs are admitted. Partial scores remain diagnostic and include coverage. This prevents selective exclusions from masquerading as a complete benchmark result.

Zero denominators produce null scores, not zero. Counts and descriptive Wilson 95% intervals accompany each binary rate. These intervals do not account for dependence across repeats or related templates. A future inferential model comparison needs paired intervals clustered by instance; this pilot does not implement that analysis.

Worked example, not measured results: 21 FAIL, 6 PASS and 3 INCONCLUSIVE on 30 fault trials; 25 PASS, 2 FAIL and 3 INCONCLUSIVE on 30 controls. Fault detection = 21/30 = 70%; false PASS = 6/30 = 20%; false FAIL = 2/30 = 6.67%; inconclusive = 6/60 = 10%; decisive coverage = 54/60 = 90%; decisive error = 8/54 = 14.81%. Pair accuracy additionally requires the instance-level pairing; these marginal counts alone cannot determine it.

## Run and replay

In the research UI, open New experiment, expand Experiment settings, and select Frozen pilot under State oracle. Select a dedicated AndroidWorld emulator. The pilot schedules each trial for each selected condition and repeat. It uses frozen prompts and parameters. Discoverability labels are recorded in each run's ground-truth panel. The current browser-run scheduler must remain open; it stops on setup/submission errors and does not provide durable resume.

Prerequisites: AndroidWorld emulator and its apps set up using upstream instructions, gRPC enabled (default 8554), and the configured model credentials. The adapter uses the separate `android_world/.venv` Python environment. It pins the source revision and reconstructs the post-run oracle without resetting the app.

Download observations from `/api/research/pilot/observations`, then run:

```sh
python apps/research_ui/scripts/score_pilot.py \
  apps/research_ui/datasets/androidworld/pilot_v1.json \
  pilot-observations.jsonl --out report.json --csv metrics.csv
```

Scoring requires only Python's standard library. It performs no device or model calls. An empty observations file produces no measured groups. A condition that never started cannot be inferred from an empty file.

Archive run bundles alongside the observation ledger. Each bundle contains state snapshots, checksums, the frozen pilot and scorer, screenshots, model traces and reviews. Human review labels are curator assertions; checksums detect changes relative to an artifact, but do not authenticate a reviewer or guarantee correctness.
