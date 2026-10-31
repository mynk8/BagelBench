#!/usr/bin/env python3
"""Generate a checksummed JSON state pair from an AndroidWorld row snapshot.

Input contract: a JSON object containing ``records`` (a list of records with
stable ``id`` fields) and optional ``test_prompt`` / provenance metadata. An
app-specific adapter must still seed these records on-device and run the
AndroidWorld oracle before and after injection.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import random
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def mutate_fixture(fixture: dict[str, Any], operation: str, target_id: str, seed: int,
                   field: str | None = None, value: Any = None) -> dict[str, Any]:
    baseline = copy.deepcopy(fixture)
    fault = copy.deepcopy(fixture)
    records = fault.get("records")
    if not isinstance(records, list):
        raise ValueError("fixture.records must be a list")
    indices = [i for i, row in enumerate(records) if isinstance(row, dict) and str(row.get("id")) == target_id]
    if len(indices) != 1:
        raise ValueError("target_id must identify exactly one record")
    index = indices[0]
    row = records[index]
    rng = random.Random(seed)
    description: dict[str, Any] = {"operation": operation, "target_id": target_id, "seed": seed}

    if operation == "delete_target":
        records.pop(index)
    elif operation == "duplicate_target":
        duplicate = copy.deepcopy(row)
        duplicate["id"] = f"{target_id}-mutation-{seed}"
        if any(str(existing.get("id")) == duplicate["id"] for existing in records if isinstance(existing, dict)):
            raise ValueError("duplicate id already exists in fixture")
        records.insert(index + 1, duplicate)
    elif operation == "change_value":
        if not field or field not in row:
            raise ValueError("change_value requires an existing --field")
        old = row[field]
        if value is None:
            if isinstance(old, bool):
                value = not old
            elif isinstance(old, (int, float)):
                value = old + 1
            elif isinstance(old, str):
                value = old + " (changed)"
            else:
                raise ValueError("change_value needs --value for this field type")
        row[field] = value
        description.update(field=field, before=old, after=value)
    elif operation == "truncate_text":
        if not field or not isinstance(row.get(field), str) or len(row[field]) < 2:
            raise ValueError("truncate_text requires a text --field of at least two characters")
        old = row[field]
        row[field] = old[: max(1, len(old) // 2)]
        description.update(field=field, before=old, after=row[field])
    elif operation == "shift_date":
        if not field or not isinstance(row.get(field), str):
            raise ValueError("shift_date requires a date --field in ISO YYYY-MM-DD format")
        try:
            old_date = dt.date.fromisoformat(row[field])
        except ValueError as error:
            raise ValueError("shift_date requires a date --field in ISO YYYY-MM-DD format") from error
        days = rng.choice((-1, 1))
        row[field] = (old_date + dt.timedelta(days=days)).isoformat()
        description.update(field=field, before=old_date.isoformat(), after=row[field], day_offset=days)
    elif operation == "flip_flag":
        if not field or not isinstance(row.get(field), bool):
            raise ValueError("flip_flag requires a boolean --field")
        old = row[field]
        row[field] = not old
        description.update(field=field, before=old, after=row[field])
    elif operation == "archive_item":
        if not field or not isinstance(row.get(field), bool):
            raise ValueError("archive_item requires a boolean archive/hidden --field")
        old = row[field]
        row[field] = True
        if old is True:
            raise ValueError("target record is already archived")
        description.update(field=field, before=old, after=True)
    else:
        raise ValueError(f"unknown mutation operation: {operation}")

    if canonical(baseline) == canonical(fault):
        raise ValueError("mutation did not change the fixture")
    return {
        "schema_version": "artemis-state-mutation-pair/v1",
        "test_prompt": fixture.get("test_prompt"),
        "provenance": fixture.get("provenance", {}),
        "mutation": description,
        "baseline": {"state": baseline, "sha256": hashlib.sha256(canonical(baseline)).hexdigest()},
        "fault": {"state": fault, "sha256": hashlib.sha256(canonical(fault)).hexdigest()},
        "validation": {
            "state_diff_confirmed": True,
            "app_oracle_confirmed": False,
            "screen_visibility_review": "required",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--operation", required=True, choices=("delete_target", "duplicate_target", "change_value", "truncate_text", "shift_date", "flip_flag", "archive_item"))
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--field")
    parser.add_argument("--value", help="JSON scalar replacement for change_value, for example '499' or 'false'.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        value = json.loads(args.value) if args.value is not None else None
        pair = mutate_fixture(fixture, args.operation, args.target_id, args.seed, args.field, value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(pair, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
