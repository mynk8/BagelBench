# Dataset and harness ownership

This project has distinct domains. Each domain has one canonical owner; other layers consume its records through a versioned contract.

| Domain | Owns | Canonical artifacts | Must not own |
|---|---|---|---|
| **Benchmark definition** | Task IDs, AndroidWorld source task, generated parameters, test instruction, pair membership, mutation declaration, source revision | `pilot_v1.json`, `pilot_showcase_v1.json`, `case_catalog.json`, exported JSONL | Device state truth, model verdicts, UI interpretation |
| **Fixture and mutation** | Emulator reset, AndroidWorld task setup, control/fault state creation, pre/post app-state reads, mutation confirmation | `androidworld_device.py`, `artemis/services/androidworld_fixture.py`, `ground_truth.jsonl` | Agent PASS/FAIL label or human discoverability decision |
| **Agent execution** | Prompt delivery, model/tool calls, actions, screenshots, accessibility observations, reasoning and declared verdict | Artemis session trace, Data Engine, `run_outcome.json` | Hidden expected label or mutation metadata |
| **Verifier contracts** | Deterministic predicates, required inputs, per-read confidence tier, version, fixture admission checks | `verifier_contracts_v1.json`, `oracle_tier_guide_v1.csv`, `qa_pilot.py::strict_oracle`, device adapter | UI display state or claim about agent competence |
| **Human evidence review** | Independent blind answer-key labels, discoverability, adjudication, reviewer agreement | `ground_truth.jsonl`, `oracle_calibration_v1.schema.json`, `oracle_calibration_summary_v1.schema.json` | Database truth or model verdict |
| **Scoring** | Admission/exclusion rules, false PASS/FAIL labels, tier-specific metrics, paired intervals and sensitivity bounds | `score_pilot.py`; run observations built by `research_trials.py` | Re-reading device state or inferring missing truth from the variant name |
| **Experiment orchestration** | Serial run ordering, condition/switches/repeats, attach fixture to session, post-run finalization | `research_batch.py`, `/api/research/batches` | Task semantics, oracle implementation, metric definitions |
| **Research UI** | Task selection, live observation, review inputs, run/score presentation | `apps/research_ui/src`, `apps/admin_console/routers/research.py` | Canonical task/verifier data; UI must render backend records, not recalculate ground truth |
| **Release and provenance** | CSV/JSONL exports, schemas, source notices, checksums, dataset card and presentation views | `package_android_qa.py`, `bundle_manifest.json`, `RUNBOOK.md` | Agent outcomes or unrecorded claims about test coverage |

## Data flow

1. The benchmark-definition domain samples a valid parameter set from a pinned AndroidWorld task generator and pairs a control with one declared fault mutation.
2. The fixture domain resets the emulator, applies the source task setup, applies the fault when requested, and reads the independent app-state oracle before the agent starts.
3. The execution domain receives only the natural-language test and live observations. It records the agent's behavior and verdict.
4. The fixture domain reads app state again. The human-review domain labels discoverability separately.
5. The scoring domain admits or excludes each observation from recorded evidence, then compares the agent verdict to the pre-run truth.
6. The release domain packages source manifests, task records, verifier code/contracts, review status, and checksums.

## Ground-truth authority

- AndroidWorld's pinned task generator owns valid parameter generation.
- The Artemis fixture adapter owns whether a mutation landed in the emulator and whether the exact criterion is true before/after a run.
- A screenshot or accessibility tree establishes exposed evidence, not persisted data correctness.
- A human review owns the discoverability label; it cannot override the independent state oracle.
- The benchmark score is computed only by the offline scorer from saved records. A missing oracle read is an infrastructure exclusion, not an agent INCONCLUSIVE.

## Current ownership state

The record-integrity slice has a concrete task generator, emulator fixture adapter, exact-field state verifier, run orchestrator, scorer, and UI review path. Persistence, action-effect, navigation, reachability, layout, presentation, permission-state, and deceptive-success contracts are documented for future slices; they now have generated reference pairs and executable offline predicates, while their live adapters remain pending. Account and membership cases are out of scope. The expanded showcase pool contains generated paired specifications from AndroidWorld's valid parameter generators. Only the fixture records listed in `device_seed_observations.csv` describe device state that has actually been seeded and oracle-read so far. Read tiers describe evidence method; measured accuracy and reviewer agreement must be reported separately.
