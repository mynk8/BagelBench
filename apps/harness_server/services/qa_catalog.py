"""The frozen Android QA pair catalog (expanded_v1) and its live-adapter routing.

Each pair is one natural-language test with a control and a fault variant that
share the same instruction. Only ``agent_view`` is actor-visible; the variant,
expected truth and setup stay with the harness.

A pair can run on a device only through an adapter that enacts its fixture
requirement for real. Authored reference artifacts are never substituted for
device truth: a pair without a live adapter is refused with the reason.
"""

from __future__ import annotations

from functools import cache
import hashlib
import json
from pathlib import Path
from typing import Any

from artemis.config import WORKSPACE_ROOT

DATASET_DIR = Path(WORKSPACE_ROOT) / "apps/research_ui/datasets/androidworld"
EXPANDED_DIR = DATASET_DIR / "expanded_v1"
SOURCE_INSTANCES = DATASET_DIR / "pilot_showcase_v1.json"

#: Live adapters, keyed by the fixture requirement a pair declares.
LIVE_ADAPTERS = {
    "existing_sqlite_fixture_adapter": "androidworld_sqlite_record_integrity",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@cache
def catalog() -> dict[str, Any]:
    pairs = [
        json.loads(line)
        for line in (EXPANDED_DIR / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tasks = [
        json.loads(line)
        for line in (EXPANDED_DIR / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    quality = json.loads((EXPANDED_DIR / "quality_report.json").read_text(encoding="utf-8"))
    sources = {
        i["pair_id"]: i
        for i in json.loads(SOURCE_INSTANCES.read_text(encoding="utf-8"))["instances"]
    }
    variants: dict[str, dict[str, Any]] = {}
    for task in tasks:
        qa = task["artemis_qa"]
        variants.setdefault(qa["pair_id"], {})[qa["variant"]] = task
    suite_id = tasks[0]["artemis_qa"]["suite_id"] if tasks else None
    return {
        "suite_id": suite_id,
        "pairs": {p["pair_id"]: p for p in pairs},
        "variants": variants,
        "sources": sources,
        "quality": quality,
        "files": {
            name: _sha256(EXPANDED_DIR / name)
            for name in ("pairs.jsonl", "tasks.jsonl", "quality_report.json")
        }
        | {"pilot_showcase_v1.json": _sha256(SOURCE_INSTANCES)},
    }


def live_support(pair: dict[str, Any]) -> dict[str, Any]:
    adapter = LIVE_ADAPTERS.get(pair.get("fixture_requirement", ""))
    if adapter:
        return {"live": True, "adapter": adapter, "reason": None}
    return {
        "live": False,
        "adapter": None,
        "reason": f"No live adapter for fixture requirement '{pair.get('fixture_requirement')}'.",
    }


def summary(pair: dict[str, Any]) -> dict[str, Any]:
    """Catalog row without any harness-only truth or setup detail."""
    support = live_support(pair)
    return {
        "pair_id": pair["pair_id"],
        "app": pair["app"],
        "bucket": pair["bucket"],
        "bucket_id": pair["bucket_id"],
        "mechanism": pair["mechanism"],
        "planned_read_tier": pair.get("planned_read_tier"),
        "fixture_requirement": pair.get("fixture_requirement"),
        "instruction": pair["instruction"],
        "live": support["live"],
        "live_reason": support["reason"],
    }


def list_pairs(
    app: str | None = None, bucket_id: str | None = None, live_only: bool = False
) -> list[dict[str, Any]]:
    rows = [summary(p) for p in catalog()["pairs"].values()]
    return [
        r
        for r in rows
        if (not app or r["app"] == app)
        and (not bucket_id or r["bucket_id"] == bucket_id)
        and (not live_only or r["live"])
    ]


def agent_instruction(pair_id: str, variant: str) -> str:
    """The only text the actor receives; identical for both variants of a pair."""
    return catalog()["variants"][pair_id][variant]["agent_view"]["instruction"]


def seed_request(pair_id: str, variant: str) -> dict[str, Any]:
    """Bridge request that enacts one variant on the device (record integrity only)."""
    cat = catalog()
    pair = cat["pairs"].get(pair_id)
    if not pair:
        raise KeyError(f"Unknown QA pair {pair_id}.")
    if variant not in ("control", "fault"):
        raise ValueError("variant must be 'control' or 'fault'.")
    support = live_support(pair)
    if not support["live"]:
        raise LookupError(support["reason"])
    task = cat["variants"][pair_id][variant]
    source_id = task["config"][0]["parameters"]["source_pair_id"]
    instance = cat["sources"][source_id]
    if instance["test_prompt"] != task["agent_view"]["instruction"]:
        raise ValueError("Source instance prompt differs from the pair's agent instruction.")
    return {
        "task_name": instance["task_name"],
        "seed": instance["seed"],
        "operation": instance["operation"],
        "field": instance["field"],
        "fault_seed": variant == "fault",
        "frozen_instance": instance,
        "provenance": {
            "qa_suite_id": cat["suite_id"],
            "qa_pair_id": pair_id,
            "variant": variant,
            "source_pair_id": source_id,
            "bucket_id": pair["bucket_id"],
            "app": pair["app"],
            "mechanism": pair["mechanism"],
            "verifier_id": pair["verifier_id"],
            "planned_read_tier": pair.get("planned_read_tier"),
            "adapter": support["adapter"],
            "expected_verdict": task["evaluator"]["expected"]["agent_verdict"],
            "reference_artifact_sha256": task["config"][1]["parameters"][
                "reference_artifact_sha256"
            ],
            "dataset_files_sha256": cat["files"],
            "criterion_sha256": hashlib.sha256(
                task["agent_view"]["instruction"].encode()
            ).hexdigest(),
        },
    }


def _generator():
    """The dataset generator's pure verifier; it imports its sibling scripts by name."""
    import sys

    scripts = str(Path(WORKSPACE_ROOT) / "apps/research_ui/scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import generate_qa_buckets

    return generate_qa_buckets


def verify_reference(pair_id: str | None = None, bucket_id: str | None = None) -> dict[str, Any]:
    """Re-run the offline verifier on the authored reference artifacts (no device, no model).

    This shows each pair's predicate separates its control from its fault. It is a
    check of the dataset contract, not an observation of the app.
    """
    gen = _generator()
    pairs = [
        p
        for p in catalog()["pairs"].values()
        if (not pair_id or p["pair_id"] == pair_id)
        and (not bucket_id or p["bucket_id"] == bucket_id)
    ]
    if pair_id and not pairs:
        raise KeyError(f"Unknown QA pair {pair_id}.")
    rows = []
    for p in pairs:
        control, fault = gen.verify(p, p["reference_control"]), gen.verify(p, p["reference_fault"])
        hashes = (
            gen.sha(p["reference_control"]) == p["control_sha256"]
            and gen.sha(p["reference_fault"]) == p["fault_sha256"]
        )
        rows.append(
            {
                "pair_id": p["pair_id"],
                "app": p["app"],
                "bucket_id": p["bucket_id"],
                "bucket": p["bucket"],
                "mechanism": p["mechanism"],
                "verifier_id": p["verifier_id"],
                "control_true": control is True,
                "fault_false": fault is False,
                "artifact_hashes_match": hashes,
                "separates": control is True and fault is False and hashes,
                "live": live_support(p)["live"],
            }
        )
    result = {
        "source": "authored_reference_artifacts",
        "suite_id": catalog()["suite_id"],
        "summary": {k: v for k, v in gen.inspect_pairs(pairs).items()},
        "pairs": rows,
    }
    if pair_id:
        p = pairs[0]
        result["detail"] = {
            "contract": p["contract"],
            "reference_control": p["reference_control"],
            "reference_fault": p["reference_fault"],
            "expected_ui_evidence": p.get("expected_ui_evidence"),
        }
    return result
