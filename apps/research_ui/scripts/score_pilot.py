#!/usr/bin/env python3
"""Score a frozen QA pilot without device or model calls.

Exclusion precedence: missing observation, recorded execution error (a
cancelled run, no post-run oracle read, no declared verdict, a crashed judge),
missing/invalid required fields, setup failure (including variant/pre-oracle mismatch),
unreviewed visibility, criterion mismatch, changed protected state (including
pre/post oracle disagreement), then admitted. Unknown truth is never inferred
from the variant. A complete pair has one admitted control and one admitted
fault in the same condition/model/repeat; paired success requires PASS on the
control and FAIL on the fault. Wilson intervals describe the observed binary
proportions; they do not establish independent-repeat inference.
"""

import argparse
import csv
import json
import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA = "artemis-qa-pilot/v1"
VERDICTS = {"PASS", "FAIL", "INCONCLUSIVE"}
BOOLEANS = (
    "pre_oracle_correct",
    "post_oracle_correct",
    "setup_confirmed",
    "visibility_confirmed",
    "protected_state_changed",
    "criterion_matched",
)
STATES = (
    "missing_observation",
    "missing_or_invalid_fields",
    "execution_error",
    "setup_failure",
    "visibility_unreviewed",
    "criterion_mismatch",
    "protected_state_changed",
    "admitted",
)


def proportion(numerator, denominator):
    if not denominator:
        return {"numerator": numerator, "denominator": denominator, "rate": None, "wilson_95": None}
    z = 1.959963984540054
    p = numerator / denominator
    scale = 1 + z * z / denominator
    center = (p + z * z / (2 * denominator)) / scale
    half = (
        z * math.sqrt(p * (1 - p) / denominator + z * z / (4 * denominator * denominator)) / scale
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": p,
        "wilson_95": [max(0.0, center - half), min(1.0, center + half)],
    }


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported manifest schema")
    if not isinstance(manifest.get("suite_id"), str) or not manifest["suite_id"]:
        raise ValueError("Manifest suite_id is required")
    if "instances" in manifest:
        identity = dict(manifest)
        suite_id = identity.pop("suite_id")
        encoded = json.dumps(
            identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if suite_id != "suite-" + hashlib.sha256(encoded).hexdigest()[:20]:
            raise ValueError("Pilot manifest checksum mismatch")
    trials = manifest.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("Manifest trials must be a nonempty list")
    by_id, pairs = {}, defaultdict(dict)
    for trial in trials:
        if not isinstance(trial, dict):
            raise ValueError("Invalid manifest trial")
        trial_id, pair_id, family, variant = (
            trial.get(k) for k in ("trial_id", "pair_id", "family", "variant")
        )
        if not all(
            isinstance(x, str) and x for x in (trial_id, pair_id, family)
        ) or variant not in ("control", "fault"):
            raise ValueError("Invalid manifest trial fields")
        if trial_id in by_id or variant in pairs[pair_id]:
            raise ValueError("Duplicate trial or pair variant")
        by_id[trial_id] = trial
        pairs[pair_id][variant] = trial
    for pair in pairs.values():
        if (
            set(pair) != {"control", "fault"}
            or pair["control"]["family"] != pair["fault"]["family"]
        ):
            raise ValueError("Each pair must have a control and fault in the same family")
    return by_id, pairs


def admission(trial, observation):
    if observation is None:
        return "missing_observation"
    if observation.get("error"):
        return "execution_error"
    if observation.get("verdict") not in VERDICTS or any(
        type(observation.get(k)) is not bool for k in BOOLEANS
    ):
        return "missing_or_invalid_fields"
    if not observation["setup_confirmed"] or observation["pre_oracle_correct"] != (
        trial["variant"] == "control"
    ):
        return "setup_failure"
    if not observation["visibility_confirmed"]:
        return "visibility_unreviewed"
    if not observation["criterion_matched"]:
        return "criterion_mismatch"
    if (
        observation["protected_state_changed"]
        or observation["pre_oracle_correct"] != observation["post_oracle_correct"]
    ):
        return "protected_state_changed"
    return "admitted"


def score(manifest, observations):
    trials, pairs = validate_manifest(manifest)
    groups = defaultdict(dict)
    for obs in observations:
        if not isinstance(obs, dict) or obs.get("trial_id") not in trials:
            raise ValueError("Observation references an unknown trial")
        condition, model = obs.get("condition"), obs.get("model")
        repeat = obs.get("repeat_index", 1)
        if (
            not all(isinstance(x, str) and x for x in (condition, model))
            or type(repeat) is not int
            or repeat < 1
        ):
            raise ValueError("Observation needs condition, model and positive repeat_index")
        group = groups[(condition, model, repeat)]
        if obs["trial_id"] in group:
            raise ValueError("Duplicate observation for trial, condition, model and repeat")
        group[obs["trial_id"]] = obs
    summaries = []
    for (condition, model, repeat), seen in sorted(groups.items()):
        states = {
            trial_id: admission(trial, seen.get(trial_id)) for trial_id, trial in trials.items()
        }
        counts = Counter(states.values())
        admitted = [
            (trials[tid], seen[tid]) for tid, state in states.items() if state == "admitted"
        ]
        faults = [obs for trial, obs in admitted if not obs["pre_oracle_correct"]]
        controls = [obs for trial, obs in admitted if obs["pre_oracle_correct"]]
        decisive = [obs for _, obs in admitted if obs["verdict"] != "INCONCLUSIVE"]
        errors = sum(
            (not obs["pre_oracle_correct"] and obs["verdict"] == "PASS")
            or (obs["pre_oracle_correct"] and obs["verdict"] == "FAIL")
            for obs in decisive
        )
        complete_pairs = []
        for pair in pairs.values():
            control_id, fault_id = pair["control"]["trial_id"], pair["fault"]["trial_id"]
            if states[control_id] == states[fault_id] == "admitted":
                complete_pairs.append((seen[control_id], seen[fault_id]))
        metrics = {
            "fault_detection": proportion(sum(o["verdict"] == "FAIL" for o in faults), len(faults)),
            "false_pass": proportion(sum(o["verdict"] == "PASS" for o in faults), len(faults)),
            "false_fail": proportion(sum(o["verdict"] == "FAIL" for o in controls), len(controls)),
            "inconclusive": proportion(
                sum(o["verdict"] == "INCONCLUSIVE" for _, o in admitted), len(admitted)
            ),
            "decisive_coverage": proportion(len(decisive), len(admitted)),
            "error_among_decisive": proportion(errors, len(decisive)),
            "paired_accuracy": proportion(
                sum(c["verdict"] == "PASS" and f["verdict"] == "FAIL" for c, f in complete_pairs),
                len(complete_pairs),
            ),
            "admission_coverage": proportion(len(admitted), len(trials)),
            "protected_state_change": proportion(
                sum(o.get("protected_state_changed") is True for o in seen.values()),
                sum(type(o.get("protected_state_changed")) is bool for o in seen.values()),
            ),
        }
        summaries.append(
            {
                "condition": condition,
                "model": model,
                "repeat_index": repeat,
                "scheduled_trials": len(trials),
                "observed_trials": len(seen),
                "admitted_trials": len(admitted),
                "scheduled_pairs": len(pairs),
                "complete_valid_pairs": len(complete_pairs),
                "ranking_eligible": len(admitted) == len(trials)
                and len(complete_pairs) == len(pairs),
                "states": {state: counts[state] for state in STATES},
                "metrics": metrics,
                "trial_states": states,
            }
        )
    return {
        "schema_version": SCHEMA,
        "suite_id": manifest["suite_id"],
        "interval_note": "Wilson 95% intervals are descriptive; repeated observations are not independent inference.",
        "groups": summaries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        observations = [
            json.loads(line)
            for line in args.observations.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result = score(manifest, observations)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "condition",
                    "model",
                    "repeat_index",
                    "metric",
                    "numerator",
                    "denominator",
                    "rate",
                    "wilson_low",
                    "wilson_high",
                ],
            )
            writer.writeheader()
            for group in result["groups"]:
                for name, metric in group["metrics"].items():
                    interval = metric["wilson_95"] or [None, None]
                    writer.writerow(
                        {
                            **{k: group[k] for k in ("condition", "model", "repeat_index")},
                            "metric": name,
                            **{k: metric[k] for k in ("numerator", "denominator", "rate")},
                            "wilson_low": interval[0],
                            "wilson_high": interval[1],
                        }
                    )


if __name__ == "__main__":
    main()
