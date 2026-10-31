#!/usr/bin/env python3
"""Rebuild a grouped Artemis research report from exported run bundles, offline."""

from __future__ import annotations
import argparse
import csv
import hashlib
import html
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path

METRICS = (
    "false_pass",
    "false_fail",
    "inconclusive",
    "mutation_score",
    "target_state_change",
    "tampering",
)


def interval(k: int, n: int) -> tuple[float, float, float]:
    if not n:
        return 0.0, 0.0, 0.0
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return p, max(0.0, mid - half), min(1.0, mid + half)


def load(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        checksums = manifest.get("sha256", {})
        for name, expected in checksums.items():
            if name not in names or hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"{path}: checksum mismatch for {name}")
        experiment = (
            json.loads(archive.read("experiment.json")) if "experiment.json" in names else {}
        )
        truth = []
        if "ground_truth.jsonl" in names:
            truth = [
                json.loads(line)
                for line in archive.read("ground_truth.jsonl").decode().splitlines()
                if line.strip()
            ]
        post = next((r for r in reversed(truth) if r.get("phase") == "post"), {})
        pre = next((r for r in truth if r.get("phase") == "pre"), {})
        integrity = next((r for r in reversed(truth) if r.get("phase") == "integrity_review"), {})
        steps = json.loads(archive.read("steps.json")) if "steps.json" in names else []
        checks = json.loads(archive.read("checks.json")) if "checks.json" in names else {}
        channels = sorted(
            {
                str(r.get("evidence_channel"))
                for r in checks.get("records", [])
                if r.get("evidence_channel")
            }
        )
        model = manifest.get("model") or {}
        model_name = model.get("id") or model.get("model") or "unknown"
        outcome = post.get("classification", "unknown") if post else "unknown"
        target_satisfied = post.get("target_satisfied")
        if (
            target_satisfied is None
            and post
            and "observed_enabled" in post
            and "target_enabled" in post
        ):
            target_satisfied = post["observed_enabled"] == post["target_enabled"]
        return {
            "condition": experiment.get("condition", "unspecified"),
            "model": model_name,
            "test_length": experiment.get("test_length", "unknown"),
            "test_class": experiment.get("test_class", "unknown"),
            "evidence_type": ",".join(channels) or "unknown",
            "framing": experiment.get("framing", "unknown"),
            "outcome": outcome,
            "oracle_applicable": post.get("oracle_applicable", False),
            "target_satisfied": target_satisfied,
            "seeded_fault": post.get("seeded_fault", pre.get("seeded_fault")),
            "checker_verdict": post.get("checker_verdict"),
            "target_state_change": bool(post.get("target_state_changed")) if post else None,
            "tampering_detected": integrity.get("tampering_detected"),
            "session_id": manifest.get("session_id"),
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--csv", type=Path)
    p.add_argument("--svg", type=Path)
    args = p.parse_args()
    rows = [load(path) for path in args.runs]
    groups = defaultdict(list)
    for row in rows:
        groups[
            tuple(
                row[k]
                for k in (
                    "condition",
                    "model",
                    "test_class",
                    "test_length",
                    "evidence_type",
                    "framing",
                )
            )
        ].append(row)
    output = []
    for key, items in sorted(groups.items()):
        entry = dict(
            zip(
                ("condition", "model", "test_class", "test_length", "evidence_type", "framing"), key
            )
        )
        entry["n"] = len(items)
        for metric in METRICS:
            if metric == "tampering":
                observed = [r for r in items if r["tampering_detected"] is not None]
            elif metric == "false_pass":
                observed = [
                    r for r in items if r["oracle_applicable"] and r["target_satisfied"] is False
                ]
            elif metric == "false_fail":
                observed = [
                    r for r in items if r["oracle_applicable"] and r["target_satisfied"] is True
                ]
            elif metric == "inconclusive":
                observed = [r for r in items if r["oracle_applicable"]]
            elif metric == "mutation_score":
                observed = [
                    r for r in items if r["oracle_applicable"] and r["seeded_fault"] is True
                ]
            else:
                observed = [r for r in items if r["target_state_change"] is not None]
            count = sum(
                (
                    r["tampering_detected"] is True
                    if metric == "tampering"
                    else r["outcome"] == "false_pass"
                    if metric == "false_pass"
                    else r["outcome"] == "false_fail"
                    if metric == "false_fail"
                    else r["outcome"] == "inconclusive"
                    if metric == "inconclusive"
                    else r["checker_verdict"] == "failed"
                    if metric == "mutation_score"
                    else r["target_state_change"] is True
                )
                for r in observed
            )
            rate, lo, hi = interval(count, len(observed))
            entry[metric] = count
            entry[metric + "_n"] = len(observed)
            entry[metric + "_rate"] = rate if observed else None
            entry[metric + "_ci95"] = [lo, hi] if observed else None
            entry[metric + "_ci95_low"] = lo if observed else None
            entry[metric + "_ci95_high"] = hi if observed else None
        output.append(entry)
    cols = ["condition", "model", "test_class", "test_length", "evidence_type", "framing", "n"] + [
        column
        for m in METRICS
        for column in (m + "_n", m + "_rate", m + "_ci95_low", m + "_ci95_high")
    ]
    display_cols = [
        "condition",
        "model",
        "test_class",
        "test_length",
        "evidence_type",
        "framing",
        "n",
    ] + [m + "_rate" for m in METRICS]
    print("| " + " | ".join(display_cols) + " |")
    print("| " + " | ".join(["---"] * len(display_cols)) + " |")
    for row in output:
        cells = []
        for c in display_cols:
            if c.endswith("_rate"):
                stem = c[:-5]
                intervals = row[stem + "_ci95"]
                cells.append(
                    "unknown"
                    if intervals is None
                    else f"{row[c]:.1%} [{intervals[0]:.1%}, {intervals[1]:.1%}] (n={row[stem + '_n']})"
                )
            else:
                cells.append(str(row[c]))
        print("| " + " | ".join(cells) + " |")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            for row in output:
                flat = {k: v for k, v in row.items() if k in cols}
                for metric in METRICS:
                    ci = row[metric + "_ci95"]
                    flat[metric + "_ci95_low"], flat[metric + "_ci95_high"] = ci if ci else ("", "")
                writer.writerow(flat)
    if args.svg:
        width = 1320
        row_h = 42
        height = 80 + row_h * len(output)
        colors = ["#be4b49", "#477e69", "#929292", "#527da8", "#d49b3c", "#7c68a6"]
        labels = [
            "False PASS",
            "False FAIL",
            "Inconclusive",
            "Mutation score",
            "State changed",
            "Tampering",
        ]
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fff"/><style>text{{font:12px sans-serif;fill:#333}} .small{{font-size:10px;fill:#666}}</style><text x="20" y="25" font-weight="bold">Artemis research outcomes (95% Wilson intervals in CSV)</text>'
        ]
        for j, (label, color) in enumerate(zip(labels, colors)):
            out.append(
                f'<rect x="{20 + j * 150}" y="39" width="10" height="10" fill="{color}"/><text class="small" x="{35 + j * 150}" y="48">{label}</text>'
            )
        for i, row in enumerate(output):
            y = 84 + i * row_h
            name = f"{row['condition']} · {row['model']} · {row['test_class']} · {row['test_length']} · {row['framing']}"
            out.append(f'<text x="20" y="{y + 12}" class="small">{html.escape(name[:65])}</text>')
            for j, (metric, color) in enumerate(zip(METRICS, colors)):
                x = 490 + j * 115
                rate = row[metric + "_rate"]
                w = (rate or 0) * 72
                if w:
                    out.append(
                        f'<rect x="{x}" y="{y}" width="{w:.1f}" height="14" fill="{color}"/>'
                    )
                label = "unknown" if rate is None else f"{rate:.0%}"
                out.append(f'<text class="small" x="{x + 75}" y="{y + 12}">{label}</text>')
            out.append(f'<text class="small" x="1245" y="{y + 12}">n={row["n"]}</text>')
        out.append("</svg>")
        args.svg.write_text("".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
