#!/usr/bin/env python3
"""Construct and verify reference happy/fault pairs across nine Android QA domains.

Reference artifacts are deterministic contract examples, not captured device reads.
AndroidWorld supplies target values; Bagel authors the transitions and UI faults.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone, UTC
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata

from qa_pilot import PROFILES, REVISION, canonical, load_manifest, sha, strict_oracle
from androidworld_device import near_miss_text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "apps/research_ui/datasets/androidworld"
VERSION = "artemis-qa-reference-pairs/v1"
BUCKETS = {
    "record_integrity": "Record integrity",
    "persistence_lifecycle": "Persistence / lifecycle",
    "action_effect_side_effects": "Action effects / side effects",
    "navigation_transitions": "Navigation transitions",
    "control_reachability": "Control reachability",
    "visual_layout": "Visual layout",
    "presentation_consistency": "Presentation consistency",
    "permission_state": "Permission state",
    "success_signal_truth": "Success signal truth",
}
VERIFIERS = dict(
    zip(
        BUCKETS,
        [
            "record_integrity.sqlite_exact_preserve.v1",
            "persistence.lifecycle_snapshot.v1",
            "action_effects.expected_delta.v1",
            "navigation.transition_contract.v1",
            "controls.accessibility_contract.v1",
            "layout.geometry_review.v1",
            "presentation.stored_vs_rendered.v1",
            "permission.package_appops.v1",
            "feedback.signal_vs_durable_state.v1",
        ],
    )
)
PACKAGES = {
    "SimpleCalendarAddOneEvent": "com.simplemobiletools.calendar.pro",
    "ExpenseAddSingle": "com.arduia.expense",
    "RecipeAddSingleRecipe": "com.flauschcode.broccoli",
}
VOLATILE = {
    "ExpenseAddSingle": ["modified_date"],
    "SimpleCalendarAddOneEvent": ["last_updated"],
    "RecipeAddSingleRecipe": [],
}
PERMISSIONS = [
    ("READ_CONTACTS", "Contacts"),
    ("READ_CALENDAR", "Calendar"),
    ("POST_NOTIFICATIONS", "Notifications"),
]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def csv_write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            )


def projected(rows, ignore):
    return sorted(canonical({k: v for k, v in row.items() if k not in ignore}) for row in rows)


def field_change(row, field):
    old = row[field]
    row[field] = old + 100 if isinstance(old, (int, float)) else near_miss_text(old)


def rect_area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def geometry_valid(a):
    if a.get("coordinate_unit") != "dp":
        return False
    viewport = [0, 0, *a["viewport"]]
    if any(rect_area(n["bounds"]) == 0 for n in a["nodes"]):
        return False
    for node in a["nodes"]:
        r = node["bounds"]
        if rect_area(r) == 0 or intersection(r, viewport) != rect_area(r):
            return False
        if node["role"] == "button" and min(r[2] - r[0], r[3] - r[1]) < a["min_touch_dp"]:
            return False
        for other in a["nodes"]:
            if (
                node["id"] != other["id"]
                and intersection(r, other["bounds"]) / min(rect_area(r), rect_area(other["bounds"]))
                > a["max_overlap"]
            ):
                return False
        if any(intersection(r, o) > 0 for o in a["occluders"]):
            return False
    return True


def normalize_display(value, kind):
    text = " ".join(unicodedata.normalize("NFKC", str(value)).split())
    if kind == "usd_cents":
        if not re.fullmatch(r"\$\d+\.\d{2}", text):
            raise ValueError("Expected explicit USD currency and two decimal places")
        return int(Decimal(text[1:]) * 100)
    if kind == "unix_seconds_utc":
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            raise ValueError("Timezone required")
        return int(parsed.timestamp())
    return text


def verify(pair, a):
    """Pure, offline predicate over reference artifacts or matching saved reads."""
    bucket, contract = pair["bucket_id"], pair["contract"]

    def scoped(rows):
        return projected(
            [{k: row[k] for k in contract["fields"]} for row in rows],
            contract.get("ignore_fields", []),
        )

    if bucket == "record_integrity":
        return strict_oracle(a["baseline"], a["rows"], a["targets"], contract["fields"])
    if bucket == "persistence_lifecycle":
        return a["boundary_completed"] and all(
            scoped(s) == scoped(contract["expected_rows"]) for s in a["snapshots"]
        )
    if bucket in ("action_effect_side_effects", "success_signal_truth"):
        return scoped(a["rows"]) == scoped(contract["expected_rows"])
    if bucket == "navigation_transitions":
        return (
            a["screen_fingerprints"] == contract["expected_screens"]
            and a["rows"] == contract["expected_rows"]
        )
    if bucket == "control_reachability":
        n = a["node"]
        return bool(
            n
            and n["present"]
            and n["visible"]
            and n["enabled"]
            and n["clickable"]
            and rect_area(n["bounds"]) > 0
            and intersection(n["bounds"], [0, 0, *a["viewport"]]) == rect_area(n["bounds"])
            and a["safe_tap_effect_confirmed"]
        )
    if bucket == "visual_layout":
        return geometry_valid(a)
    if bucket == "presentation_consistency":
        try:
            return (
                normalize_display(a["displayed"], contract["normalizer"])
                == contract["normalized_expected"]
            )
        except (ValueError, ArithmeticError):
            return False
    if bucket == "permission_state":
        return (
            a["boundary_completed"]
            and a["boundary"] == contract["boundary"]
            and a["package"] == contract["package"]
            and a["permission"] == contract["permission"]
            and a["granted"] == contract["expected_granted"]
        )
    raise ValueError(bucket)


def base_pair(
    item, bucket, mechanism, instruction, control, fault, contract, tier, requirement, observation
):
    profile = PROFILES[item["task_name"]]
    source = {
        "dataset": "Google Research AndroidWorld",
        "revision": REVISION,
        "task_name": item["task_name"],
        "source_pair_id": item["pair_id"],
        "seed": item["seed"],
        "target": item["params"]["row_objects"][0],
        "params_sha256": sha(item["params"]),
    }
    record = {
        "schema_version": VERSION,
        "bucket_id": bucket,
        "bucket": BUCKETS[bucket],
        "app": profile["app"],
        "package": PACKAGES[item["task_name"]],
        "source": source,
        "mechanism": mechanism,
        "template_id": f"{bucket}.{mechanism}",
        "instruction": instruction,
        "contract": contract,
        "verifier_id": VERIFIERS[bucket],
        "offline_predicate": "generate_qa_buckets.py::verify",
        "reference_control": control,
        "reference_fault": fault,
        "planned_read_tier": tier,
        "case_answer_key_tier": None,
        "fixture_requirement": requirement,
        "expected_ui_evidence": observation,
        "artifact_origin": "authored_reference_contract_from_androidworld_values",
        "device_execution": "not_recorded_for_this_reference_pair",
        "human_calibration": "not_collected",
        "agent_results": "not_collected",
        "source_generated_states_are_distinct_from_authored_ui_transitions": True,
    }
    record["pair_id"] = "qa-" + sha(record)[:20]
    record["control_sha256"], record["fault_sha256"] = sha(control), sha(fault)
    record["reference_control_truth"] = verify(record, control)
    record["reference_fault_truth"] = verify(record, fault)
    return record


def derive(item, bucket, index):
    task, profile = item["task_name"], PROFILES[item["task_name"]]
    target = deepcopy(item["params"]["row_objects"][0])
    protected = deepcopy(item["params"].get("noise_row_objects", [])[:2])
    rows = protected + [target]
    fields = profile["fields"]
    label = str(target[fields[0]])
    app = profile["app"]
    expected = {k: target[k] for k in fields}
    ignore = VOLATILE[task]
    conclusion = " Return PASS only when every stated check holds; FAIL for an established violation; otherwise INCONCLUSIVE."
    contract = {
        "fields": fields,
        "ignore_fields": ignore,
        "snapshot_scope": "Target plus two named protected source records; runtime adapter must resolve this scope from source_pair_id. Other seeded rows are monitored by the separate protected-state audit.",
    }
    requirement, tier = "app_fault_hook_and_state_adapter", "A"
    observation = (
        "Reopen target and inspect the stated fields; retain screen/tree and pre/post state reads."
    )

    if bucket == "record_integrity":
        mechanism = item["operation"] + (":" + item["field"] if item["field"] else "")
        control = {"baseline": protected, "targets": [target], "rows": deepcopy(rows)}
        fault = deepcopy(control)
        if item["operation"] == "delete_target":
            fault["rows"].pop()
        elif item["operation"] == "truncate_text":
            value = target[item["field"]]
            fault["rows"][-1][item["field"]] = value[: max(1, len(value) // 2)]
        elif item["operation"] == "shift_date":
            for f in ("start_ts", "end_ts"):
                fault["rows"][-1][f] += 86400
        else:
            field_change(fault["rows"][-1], item["field"])
        instruction = item["test_prompt"]
        requirement = "existing_sqlite_fixture_adapter"
    elif bucket == "persistence_lifecycle":
        mechanism, boundary = [
            ("reopen_lost_record", "close and reopen the detail screen"),
            ("force_stop_lost_value", "force-stop and relaunch the app"),
            ("rotation_stale_text", "rotate and restore the screen"),
            ("resume_truncated_text", "background and resume the app"),
            ("relaunch_duplicate", "exit and relaunch the app"),
        ][index]
        contract.update(expected_rows=rows, boundary=boundary)
        control = {"boundary_completed": True, "snapshots": [deepcopy(rows), deepcopy(rows)]}
        fault = deepcopy(control)
        if index == 0:
            fault["snapshots"][-1].pop()
        elif index == 4:
            fault["snapshots"][-1].append(deepcopy(target))
        else:
            field_change(fault["snapshots"][-1][-1], fields[-1 if index == 3 else 0])
        instruction = (
            f'In {app}, inspect "{label}" and confirm these fields: {canonical(expected)}. Then {boundary}. Reopen the same record and verify exactly one matching record remains and all listed fields survive. Do not add, edit, or delete records; unrelated records must remain unchanged.'
            + conclusion
        )
        requirement = "lifecycle_boundary_fault_hook_and_state_adapter"
    elif bucket == "action_effect_side_effects":
        mechanism = [
            "no_op_edit",
            "wrong_target_edit",
            "duplicate_commit",
            "collateral_change",
            "cancel_commits",
        ][index]
        before = deepcopy(rows)
        changed = deepcopy(target)
        field_change(changed, fields[0])
        after = deepcopy(protected) + [changed]
        if index == 4:
            after = deepcopy(rows)
        contract.update(expected_rows=after, before_rows=before)
        control, fault = {"rows": deepcopy(after)}, {"rows": deepcopy(after)}
        if index == 0:
            fault["rows"] = before
        elif index == 1:
            fault["rows"] = deepcopy(before)
            field_change(fault["rows"][0], fields[0])
        elif index == 2:
            fault["rows"].append(deepcopy(changed))
        elif index == 3:
            field_change(fault["rows"][0], fields[0])
        else:
            fault["rows"].pop()
        action = (
            f'edit {fields[0]} from "{target[fields[0]]}" to "{changed[fields[0]]}" and save'
            if index != 4
            else "open the delete confirmation and choose Cancel"
        )
        instruction = (
            f'In {app}, find "{label}", {action}. Verify the target outcome is exactly {canonical({k: after[-1][k] for k in fields})}, there is one target record, and these unrelated records remain unchanged: {canonical([{k: r.get(k) for k in fields} for r in protected])}.'
            + conclusion
        )
    elif bucket == "navigation_transitions":
        mechanism = [
            "wrong_destination",
            "back_wrong_origin",
            "cancel_changes_state",
            "search_wrong_target",
            "reopen_wrong_record",
        ][index]
        detail = "detail:" + sha(expected)[:12]
        routes = [
            ["list", detail],
            ["list", detail, "list"],
            ["list", detail, "delete_dialog", detail],
            ["list", "search:" + label, detail],
            ["list", detail, "list", detail],
        ]
        screens = routes[index]
        contract.update(
            expected_screens=screens,
            expected_rows=rows,
            fingerprint_recipe="Reviewed semantic locator from target title/text and UI roles; hash normalized hierarchy nodes on the pinned build. These reference keys are authored, not captured fingerprints.",
        )
        control = {"screen_fingerprints": screens, "rows": deepcopy(rows)}
        fault = deepcopy(control)
        if index == 2:
            fault["rows"].pop()
        else:
            fault["screen_fingerprints"] = screens[:-1] + ["unexpected_screen"]
        steps = [
            "open its detail from the list",
            "open its detail, then press Back and confirm the list returns",
            "open its delete dialog, press Cancel, and confirm the same detail returns without data change",
            "search for its exact title and open the unique matching result",
            "open its detail, return to the list, and open it again",
        ][index]
        instruction = (
            f'In {app}, locate "{label}" and {steps}. Verify the detail belongs to {canonical(expected)} and no records change.'
            + conclusion
        )
        requirement, tier = "reviewed_screen_fingerprint_and_navigation_fault_hook", "B"
    elif bucket == "control_reachability":
        mechanism = [
            "missing_control",
            "disabled_control",
            "hidden_control",
            "offscreen_control",
            "tap_no_effect",
        ][index]
        node = {
            "present": True,
            "visible": True,
            "enabled": True,
            "clickable": True,
            "bounds": [16, 100, 344, 156],
            "locator": {"role": "record_row", "text": label},
        }
        control = {"node": node, "viewport": [360, 800], "safe_tap_effect_confirmed": True}
        fault = deepcopy(control)
        if index == 0:
            fault["node"] = None
        elif index == 1:
            fault["node"]["enabled"] = False
        elif index == 2:
            fault["node"]["visible"] = False
        elif index == 3:
            fault["node"]["bounds"] = [380, 100, 708, 156]
        else:
            fault["safe_tap_effect_confirmed"] = False
        instruction = (
            f'In {app}, locate the list entry "{label}". Verify it is visible, enabled, fully on-screen, and opens the matching detail when tapped. Do not edit or delete records.'
            + conclusion
        )
        requirement, tier = "UI_contract_locator_and_control_fault_hook", "B"
        observation = (
            "Before/after raw hierarchy and screenshot; a safe tap must open the matching detail."
        )
    elif bucket == "visual_layout":
        mechanism = [
            "button_clipped",
            "text_clipped",
            "keyboard_occlusion",
            "row_overlap",
            "touch_target_too_small",
        ][index]
        control = {
            "coordinate_unit": "dp",
            "viewport": [360, 800],
            "min_touch_dp": 48,
            "max_overlap": 0.05,
            "occluders": [],
            "nodes": [
                {"id": "target", "role": "button", "bounds": [16, 100, 344, 156], "text": label},
                {
                    "id": "secondary",
                    "role": "text",
                    "bounds": [16, 180, 344, 236],
                    "text": str(target[fields[-1]]),
                },
            ],
        }
        fault = deepcopy(control)
        if index == 0:
            fault["nodes"][0]["bounds"] = [320, 100, 410, 156]
        elif index == 1:
            fault["nodes"][1]["bounds"] = [-40, 180, 344, 236]
        elif index == 2:
            fault["occluders"] = [[0, 400, 360, 800]]
            fault["nodes"][0]["bounds"] = [16, 440, 344, 496]
        elif index == 3:
            fault["nodes"][1]["bounds"] = [16, 110, 344, 166]
        else:
            fault["nodes"][0]["bounds"] = [16, 100, 344, 124]
        instruction = (
            f'In {app}, inspect the target "{label}" at the pinned device profile. Verify the required row and its text are fully inside the viewport, are not covered by the keyboard, and overlap by no more than 5% of the smaller element. The clickable target must be at least 48 dp in each dimension.'
            + conclusion
        )
        requirement, tier = "authored_layout_fault_build_and_captured_bounds_screenshot_review", "C"
        observation = "Capture raw pixel bounds and device density, normalize bounds and viewport to dp, then apply the geometric predicate. Reference rectangles are authored examples; harmfulness requires blinded screenshot review."
    elif bucket == "presentation_consistency":
        mechanism = [
            "wrong_primary_text",
            "wrong_secondary_value",
            "truncated_required_text",
            "stale_value",
            "wrong_format_or_value",
        ][index]
        field = fields[[0, 1, -1, 0, -1][index]]
        if task == "ExpenseAddSingle" and index in (1, 4):
            field = "amount"
        if task == "SimpleCalendarAddOneEvent" and index in (1, 4):
            field = "start_ts"
        raw = target[field]
        kind = (
            "usd_cents"
            if field == "amount"
            else "unix_seconds_utc"
            if field in ("start_ts", "end_ts")
            else "text"
        )
        displayed = (
            f"${raw / 100:.2f}"
            if kind == "usd_cents"
            else datetime.fromtimestamp(raw, UTC).isoformat()
            if kind == "unix_seconds_utc"
            else str(raw)
        )
        contract.update(
            field=field,
            stored_value=raw,
            normalizer=kind,
            locale="en-US",
            timezone="UTC",
            normalized_expected=normalize_display(displayed, kind),
        )
        control = {"displayed": displayed}
        if kind == "usd_cents":
            bad = displayed.replace("$", "€") if index == 4 else f"${(raw + 100) / 100:.2f}"
        elif kind == "unix_seconds_utc":
            bad = (
                displayed.replace("+00:00", "")
                if index == 4
                else datetime.fromtimestamp(raw + 86400, UTC).isoformat()
            )
        elif index == 2:
            bad = displayed[: max(1, len(displayed) // 2)]
        elif index == 3:
            bad = (
                str(protected[0].get(field))
                if protected and protected[0].get(field) != raw
                else displayed + " (previous value)"
            )
        else:
            bad = near_miss_text(displayed)
        fault = {"displayed": bad}
        instruction = (
            f'In {app}, open "{label}" and verify that displayed {field} is {displayed!r}. Compare the complete value, including units and formatting; use locale en-US and UTC where applicable. Do not change data.'
            + conclusion
        )
        requirement, tier = "rendered_field_locator_normalizer_and_presentation_fault_hook", "B"
    elif bucket == "success_signal_truth":
        mechanism = [
            "saved_but_missing",
            "saved_wrong_value",
            "saved_duplicate",
            "saved_with_collateral_damage",
            "saved_wrong_destination",
        ][index]
        contract.update(
            expected_rows=rows,
            feedback_condition_levels=["shown", "absent"],
            same_fault_state_across_feedback_levels=True,
        )
        control = {
            "rows": deepcopy(rows),
            "signal": {
                "kind": "persistent_snackbar",
                "text": "Saved",
                "issued_ms": 1000,
                "removed_ms": 5000,
            },
            "delivered_observations": [
                {"model_call_id": "reference-call", "capture_ms": 1500, "snackbar_in_tree": True}
            ],
        }
        fault = deepcopy(control)
        if index == 0:
            fault["rows"].pop()
        elif index == 1:
            field_change(fault["rows"][-1], fields[0])
        elif index == 2:
            fault["rows"].append(deepcopy(target))
        elif index == 3:
            field_change(fault["rows"][0], fields[0])
        else:
            fault["rows"].pop()
            fault["other_destination"] = [target]
        instruction = (
            f"In {app}, save this target record: {canonical(expected)}. Verify it exists exactly once after reopening, every stated field matches, and unrelated records remain unchanged. Use the saved result to decide the verdict."
            + conclusion
        )
        requirement, tier = "patched_save_path_and_persistent_feedback_exposure_capture", "B"
        observation = "Reference signal timestamps are authored. Runtime must capture signal in observations delivered to the model and report exposure misses."
    else:
        raise ValueError(bucket)
    return base_pair(
        item,
        bucket,
        mechanism,
        instruction,
        control,
        fault,
        contract,
        tier,
        requirement,
        observation,
    )


def permission_pair(item, permission, group, desired, context_index):
    full = "android.permission." + permission
    package = PACKAGES[item["task_name"]]
    state = "allowed" if desired else "denied"
    boundary = [
        "inspect the current state",
        "force-stop and relaunch the app, then inspect again",
        "background and resume the app, then inspect again",
        "restart the app process and return to Settings",
        "rotate Settings and re-open the app permission page",
    ][context_index]
    contract = {
        "package": package,
        "permission": full,
        "expected_granted": desired,
        "min_api": 33 if permission == "POST_NOTIFICATIONS" else 23,
        "boundary": boundary,
    }
    control = {
        "package": package,
        "permission": full,
        "granted": desired,
        "boundary": boundary,
        "boundary_completed": True,
    }
    fault = {**control, "granted": not desired}
    instruction = f"In Android Settings, inspect the permissions for Simple Calendar Pro: {boundary}. Verify that the {group} permission is {state}. Do not change the permission. Return PASS if the permission matches, FAIL for an established mismatch, or INCONCLUSIVE if its state cannot be determined."
    return base_pair(
        item,
        "permission_state",
        permission.lower() + ("_granted" if desired else "_denied") + f"_context_{context_index}",
        instruction,
        control,
        fault,
        contract,
        "A",
        "pm_grant_revoke_with_api_and_manifest_preconditions",
        "Agent sees permission group in Settings. Verifier reads exact package permission; capture both for admission.",
    )


def audit_permissions(aapt, apk):
    output = subprocess.run(
        [str(aapt), "dump", "permissions", str(apk)], check=True, capture_output=True, text=True
    ).stdout
    declared = re.findall(r"uses-permission: name='([^']+)'", output)
    for permission, _ in PERMISSIONS:
        if "android.permission." + permission not in declared:
            raise ValueError("Missing declared permission " + permission)
    return {
        "package": PACKAGES["SimpleCalendarAddOneEvent"],
        "apk_name": apk.name,
        "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "permissions": declared,
        "tool": "aapt dump permissions",
        "raw_output": output,
    }


def construct(items, exemplars):
    pairs = [derive(item, "record_integrity", 0) for item in items]
    groups = defaultdict(list)
    for item in items:
        groups[item["task_name"]].append(item)
    for bucket in BUCKETS:
        if bucket in ("record_integrity", "permission_state"):
            continue
        for group in groups.values():
            eligible = [
                item for item in group if len(item["params"].get("noise_row_objects", [])) >= 2
            ]
            if len(eligible) < exemplars:
                raise ValueError("Insufficient protected-record source examples")
            for i, item in enumerate(eligible[:exemplars]):
                for mechanism in range(5):
                    pairs.append(derive(item, bucket, mechanism))
    for context_index, item in enumerate(groups["SimpleCalendarAddOneEvent"][: exemplars + 1]):
        for permission, group in PERMISSIONS:
            for desired in (False, True):
                pairs.append(permission_pair(item, permission, group, desired, context_index))
    return pairs


def inspect_pairs(pairs):
    issues = []
    identities = Counter(p["pair_id"] for p in pairs)
    semantics = Counter(
        sha(
            {
                k: p[k]
                for k in ("bucket_id", "app", "instruction", "reference_control", "reference_fault")
            }
        )
        for p in pairs
    )
    for p in pairs:
        identity = {
            k: v
            for k, v in p.items()
            if k
            not in (
                "pair_id",
                "control_sha256",
                "fault_sha256",
                "reference_control_truth",
                "reference_fault_truth",
            )
        }
        if p["pair_id"] != "qa-" + sha(identity)[:20]:
            issues.append([p["pair_id"], "pair_contract_hash_mismatch"])
        if not verify(p, p["reference_control"]) or verify(p, p["reference_fault"]):
            issues.append([p["pair_id"], "oracle_does_not_separate"])
        if (
            sha(p["reference_control"]) != p["control_sha256"]
            or sha(p["reference_fault"]) != p["fault_sha256"]
        ):
            issues.append([p["pair_id"], "artifact_hash_mismatch"])
        if p["control_sha256"] == p["fault_sha256"]:
            issues.append([p["pair_id"], "no_artifact_delta"])
        if p["source"]["revision"] != REVISION:
            issues.append([p["pair_id"], "source_revision_mismatch"])
        if not p["instruction"] or not p["fixture_requirement"]:
            issues.append([p["pair_id"], "missing_contract"])
    return {
        "pair_count": len(pairs),
        "variant_count": len(pairs) * 2,
        "issues": issues,
        "duplicate_pair_ids": sum(v - 1 for v in identities.values()),
        "duplicate_reference_pairs": sum(v - 1 for v in semantics.values()),
        "bucket_counts": dict(Counter(p["bucket_id"] for p in pairs)),
        "app_counts": dict(Counter(p["app"] for p in pairs)),
        "template_count": len({(p["bucket_id"], p["app"], p["mechanism"]) for p in pairs}),
        "unique_source_parameter_sets": len({p["source"]["params_sha256"] for p in pairs}),
        "control_true_count": sum(p["reference_control_truth"] for p in pairs),
        "fault_false_count": sum(not p["reference_fault_truth"] for p in pairs),
    }


def export(pairs, out, audit, iterations):
    out.mkdir(parents=True, exist_ok=True)
    report = inspect_pairs(pairs)
    if report["issues"] or report["duplicate_pair_ids"] or report["duplicate_reference_pairs"]:
        raise ValueError(report)
    suite_id = "qa-suite-" + sha([p["pair_id"] for p in pairs])[:20]
    (out / "pairs.jsonl").write_text("".join(canonical(p) + "\n" for p in pairs))
    trials = []
    for p in pairs:
        for variant in ("control", "fault"):
            trials.append(
                {
                    "id": p["pair_id"] + "-" + variant,
                    "instruction": p["instruction"],
                    "source": "AndroidWorld " + REVISION + "; Bagel authored QA contract",
                    "related_apps": [p["app"]],
                    "agent_view": {
                        "instruction": p["instruction"],
                        "platform": "android",
                        "app": p["app"],
                    },
                    "config": [
                        {"type": "androidworld_initialize_task", "parameters": p["source"]},
                        {
                            "type": "apply_reference_qa_contract",
                            "parameters": {
                                "variant": variant,
                                "fixture_requirement": p["fixture_requirement"],
                                "reference_artifact_sha256": p[variant + "_sha256"],
                            },
                        },
                    ],
                    "evaluator": {
                        "func": "generate_qa_buckets.verify",
                        "result": {"type": "saved_contract_artifacts"},
                        "expected": {
                            "criterion_true": variant == "control",
                            "agent_verdict": "PASS" if variant == "control" else "FAIL",
                        },
                        "options": {
                            "verifier_id": p["verifier_id"],
                            "oracle_kind": p["bucket_id"],
                            "oracle_version": VERSION,
                            "reference_pair_id": p["pair_id"],
                        },
                    },
                    "artemis_qa": {
                        "schema_version": "artemis-osworld-profile/v1",
                        "suite_id": suite_id,
                        "case_id": p["pair_id"],
                        "pair_id": p["pair_id"],
                        "variant": variant,
                        "family": p["bucket_id"],
                        "verifier_id": p["verifier_id"],
                        "agent_result_status": "not_collected",
                        "device_validation_status": "reference_contract_pair; device_execution_requires_declared_adapter",
                        "ground_truth_hidden_from_actor_and_checker": True,
                        "pair_control_and_fault_share_instruction": True,
                    },
                }
            )
    (out / "tasks.jsonl").write_text("".join(canonical(t) + "\n" for t in trials))
    catalog = []
    for p in pairs:
        catalog.append(
            {
                "pair_id": p["pair_id"],
                "bucket_id": p["bucket_id"],
                "bucket": p["bucket"],
                "app": p["app"],
                "source_task": p["source"]["task_name"],
                "source_seed": p["source"]["seed"],
                "source_pair_id": p["source"]["source_pair_id"],
                "mechanism": p["mechanism"],
                "test_case": p["instruction"],
                "expected_target": p["source"]["target"],
                "verifier_id": p["verifier_id"],
                "happy_reference": p["reference_control"],
                "fault_reference": p["reference_fault"],
                "predicate_contract": p["contract"],
                "reference_control_truth": p["reference_control_truth"],
                "reference_fault_truth": p["reference_fault_truth"],
                "planned_read_tier": p["planned_read_tier"],
                "case_answer_key_tier": "assigned_from_runtime_reads",
                "fixture_requirement": p["fixture_requirement"],
                "artifact_origin": p["artifact_origin"],
                "device_execution": p["device_execution"],
                "human_calibration": p["human_calibration"],
                "control_sha256": p["control_sha256"],
                "fault_sha256": p["fault_sha256"],
                "source_revision": REVISION,
            }
        )
    csv_write(out / "pair_catalog.csv", catalog)
    counts = Counter(p["bucket_id"] for p in pairs)
    csv_write(
        out / "bucket_distribution.csv",
        [
            {
                "bucket_id": b,
                "bucket": label,
                "matched_pairs": counts[b],
                "variants": 2 * counts[b],
                "source_apps": len({p["app"] for p in pairs if p["bucket_id"] == b}),
                "app_mechanism_templates": len(
                    {(p["app"], p["mechanism"]) for p in pairs if p["bucket_id"] == b}
                ),
                "reference_predicate_separation": "control_true_and_fault_false",
                "device_execution": "see_separate_fixture_observations",
            }
            for b, label in BUCKETS.items()
        ],
    )
    apps = sorted({p["app"] for p in pairs})
    csv_write(
        out / "app_bucket_distribution.csv",
        [
            {
                "app": app,
                **{b: sum(p["app"] == app and p["bucket_id"] == b for p in pairs) for b in BUCKETS},
                "total_pairs": sum(p["app"] == app for p in pairs),
            }
            for app in apps
        ],
    )
    mix = Counter((p["bucket_id"], p["app"], p["mechanism"]) for p in pairs)
    csv_write(
        out / "mutation_distribution.csv",
        [
            {"bucket_id": b, "app": app, "mechanism": m, "matched_pairs": n}
            for (b, app, m), n in sorted(mix.items())
        ],
    )
    dump(out / "permission_manifest_audit.json", audit)
    dump(
        out / "quality_report.json",
        {
            **report,
            "suite_id": suite_id,
            "scope": "offline reference-contract consistency, not device execution or human oracle calibration",
            "all_pairs_share_same_instruction_between_variants": True,
            "curation_rules": [
                "Use at least two actual source distractor records for side-effect and wrong-target cases.",
                "Reject semantically duplicate reference pairs even when their source seeds differ.",
                "Permission cases vary lifecycle context; unrelated record seeds alone do not create new permission cases.",
                "Reject any mutation whose reference artifacts are identical or whose oracle truth does not flip.",
            ],
        },
    )
    (out / "generation_iterations.jsonl").write_text(
        "".join(canonical(i) + "\n" for i in iterations)
    )
    (out / "README.md").write_text(f"""# Android QA reference case set

{report["pair_count"]} matched pairs / {report["variant_count"]} variants across 9 QA buckets and 3 apps. AndroidWorld supplies 150 frozen record parameter sets; Bagel derives the QA contracts, lifecycle/transition examples, UI/reference artifacts, and mutations. There are {report["template_count"]} distinct app × bucket × mutation templates; parameter variations are not independent app workflows.

Every reference control evaluates true and every reference fault evaluates false under `generate_qa_buckets.py::verify`. `quality_report.json` and `generation_iterations.jsonl` record the generation/inspection loop. Run `python scripts/androidworld/generate_qa_buckets.py` from the repository to regenerate. The generated data is deterministic; no model calls are made.

`pairs.jsonl` contains both full reference artifacts and exact contracts. `tasks.jsonl` has the OSWorld-shaped variant envelope. `pair_catalog.csv` is one row per pair; the distribution CSVs show bucket, app, and mechanism coverage. `permission_manifest_audit.json` records the actual Calendar APK permission declarations and hash.

Reference artifacts are authored examples. UI rectangles, screen fingerprints, feedback timestamps, and before/after effects in this set are not captures from running the apps. The existing SQLite adapter supports record seeding; the other domains require the named fixture hooks, locators, or patched builds before live execution. Keep these generated reference-pair counts separate from observed emulator fixture reads and agent verdicts. Case answer-key tiers are assigned from actual required reads at execution, and human calibration remains a separate study.

Offline replay from the release folder: `python scripts/generate_qa_buckets.py --replay-dir expanded`. This recomputes each predicate, contract ID, and artifact hash without a device or model call.

Coverage targets were set before the loop: 60 pairs in each of seven new multiapp buckets (3 apps × 5 mechanisms × 4 applicable source examples), 30 Calendar permission pairs (3 manifest-declared permission groups × 2 states × 5 lifecycle contexts), plus the existing 150 record pairs. New multiapp cases require at least two source distractor rows so wrong-target and collateral mutations are distinct. Expense and Broccoli have no dangerous runtime permission in the cached manifests, so they get no permission cases. Accounts are excluded.

Source: Google Research AndroidWorld at {REVISION}, Apache-2.0. The source parameters and upstream task identity are retained on every pair.
""")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DATA / "expanded_v1")
    parser.add_argument(
        "--replay-dir",
        type=Path,
        help="Recheck saved reference pairs offline without AndroidWorld, APK, device, or model calls.",
    )
    parser.add_argument(
        "--aapt",
        type=Path,
        default=Path(
            "/home/lucky11/.local/share/docker/volumes/e2e-android-sdk/_data/build-tools/35.0.1/aapt"
        ),
    )
    parser.add_argument(
        "--calendar-apk",
        type=Path,
        default=Path("/tmp/android_world/app_data/com.simplemobiletools.calendar.pro_238.apk"),
    )
    args = parser.parse_args()
    if args.replay_dir:
        pairs = [
            json.loads(line)
            for line in (args.replay_dir / "pairs.jsonl").read_text().splitlines()
            if line
        ]
        report = inspect_pairs(pairs)
        print(json.dumps(report, sort_keys=True))
        if report["issues"] or report["duplicate_pair_ids"] or report["duplicate_reference_pairs"]:
            raise SystemExit(1)
        return
    items = load_manifest(DATA / "pilot_showcase_v1.json")["instances"]
    audit = audit_permissions(args.aapt, args.calendar_apk)
    iterations = []
    for examples in range(1, 5):
        pairs = construct(items, examples)
        inspected = inspect_pairs(pairs)
        iterations.append(
            {"iteration": examples, "source_examples_per_multiapp_template": examples, **inspected}
        )
        print(
            json.dumps(
                {
                    "iteration": examples,
                    "pairs": len(pairs),
                    "separated_pairs": inspected["fault_false_count"],
                    "issues": len(inspected["issues"]),
                }
            )
        )
        if inspected["issues"] or inspected["duplicate_reference_pairs"]:
            raise ValueError(inspected)
    report = export(pairs, args.out_dir, audit, iterations)
    print(json.dumps({"output": str(args.out_dir), **report}, sort_keys=True))


if __name__ == "__main__":
    main()
