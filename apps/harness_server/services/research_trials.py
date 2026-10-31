"""One scored observation per frozen-suite trial, built only from recorded artifacts.

A trial is independently checkable when four records exist and agree on what
they describe: the frozen criterion (pilot manifest), the pre-run oracle read
that confirmed the seeded state, the tester's declared verdict, and the post-run
oracle read. The tester verdict and the oracle never feed each other: the
verdict comes from the agent's own notes, the truth from adb/sqlite reads that
the actor and Checker never see.

Two judges are scored separately:

- ``agent``: the tester agent's declared verdict — the last ``VERDICT: PASS|FAIL|
  INCONCLUSIVE`` line it wrote in a run note. This is the verdict the test asks for.
- ``checker``: Artemis's Checker on its final pass. Its items are planner-derived
  sub-goals, not the frozen criterion, so it is a secondary judge.

Missing or broken evidence is an explicit ``error`` reason, never a verdict: a
crashed Checker is not INCONCLUSIVE, and a cancelled run is not scored.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Literal

from apps.harness_server.services.research_grounding import grounding

Judge = Literal["agent", "checker"]

# "VERDICT: PASS", "## Verdict = FAIL", "**VERDICT:** INCONCLUSIVE — reason".
VERDICT_LINE = re.compile(
    r"^[\s#>*_=-]*(?:final\s+)?(?:verdict|result)[\s*_]*[:=][\s*_]*(PASS|FAIL|INCONCLUSIVE)\b(?!\s*/)",
    re.IGNORECASE | re.MULTILINE,
)
# A verdict heading with the value leading the next line: "## FINAL RESULT" / "PASS — reason".
VERDICT_HEADING = re.compile(
    r"^[\s#>*_=-]*(?:final\s+)?(?:verdict|result)[\s*_:=]*\n[\s>*_-]*\**(PASS|FAIL|INCONCLUSIVE)\**(?=[ \t]*$|[ \t]*[—–:(-])",
    re.IGNORECASE | re.MULTILINE,
)
HARNESS_ERROR = re.compile(r"^\s*(check raised an exception|final check error)", re.IGNORECASE)
NON_VERDICT_NOTES = {"task_plan.md"}


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValueError):
        return []


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


#: The bench answer mapped onto the research PASS/FAIL scale (a defect fails the test).
BENCH_TO_RESEARCH = {"DEFECT": "FAIL", "NO_DEFECT": "PASS", "INCONCLUSIVE": "INCONCLUSIVE"}


def declared_verdict(folder: Path) -> dict[str, Any]:
    """The tester's own verdict.

    Current runs end with ``submit_verdict``, recorded in ``bench/verdict.json``.
    Runs recorded before that read the last VERDICT line (or verdict heading plus
    value line) in the most recently written note.
    """
    bench_file = folder / "bench" / "verdict.json"
    if bench_file.is_file():
        try:
            answer = json.loads(bench_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            answer = {}
        verdict = BENCH_TO_RESEARCH.get(str(answer.get("verdict")))
        return {
            "verdict": verdict,
            "source": {"file": "bench/verdict.json", **answer} if verdict else None,
            "candidates": 1 if verdict else 0,
            "conflicting": False,
        }
    candidates = []
    notes = sorted(
        (p for p in (folder / "notes").glob("*.md") if p.name not in NON_VERDICT_NOTES),
        key=lambda p: (p.stat().st_mtime, p.name),
    )
    for note in notes:
        text = note.read_text(encoding="utf-8", errors="replace")
        matches = sorted(
            [*VERDICT_LINE.finditer(text), *VERDICT_HEADING.finditer(text)],
            key=lambda m: m.start(1),
        )
        for match in matches:
            line = text.count("\n", 0, match.start(1)) + 1
            candidates.append(
                {
                    "note": note.name,
                    "line": line,
                    "verdict": match.group(1).upper(),
                    "text": text.splitlines()[line - 1].strip()[:300],
                }
            )
    if not candidates:
        return {"verdict": None, "source": None, "candidates": 0, "conflicting": False}
    final = candidates[-1]
    return {
        "verdict": final["verdict"],
        "source": final,
        "candidates": len(candidates),
        "conflicting": len({c["verdict"] for c in candidates}) > 1,
    }


def checker_verdict(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The Checker's final pass, aggregated: any failed item fails, all passed passes."""
    final = [r for r in records if r.get("checkpoint_id") == "final"]
    if final:
        last_attempt = final[-1].get("attempt_id")
        final = [r for r in final if r.get("attempt_id") == last_attempt]
    if not final:
        return {"verdict": None, "error": "no_final_checker_pass", "items": 0}
    if any(HARNESS_ERROR.match(str(r.get("evidence") or "")) for r in final):
        return {"verdict": None, "error": "checker_crashed", "items": len(final)}
    statuses = [str(r.get("status") or "").lower() for r in final]
    verdict = (
        "FAIL"
        if "failed" in statuses
        else "PASS"
        if all(s == "passed" for s in statuses)
        else "INCONCLUSIVE"
    )
    return {"verdict": verdict, "error": None, "items": len(final)}


def classify(verdict: str | None, oracle_correct: bool | None) -> str:
    """Outcome of one verdict against the post-run oracle."""
    if verdict is None or oracle_correct is None:
        return "unscored"
    if verdict == "INCONCLUSIVE":
        return "inconclusive"
    if verdict == "PASS":
        return "correct_pass" if oracle_correct else "false_pass"
    return "false_fail" if oracle_correct else "correct_fail"


def trial_observation(
    folder: Path,
    suite_id: str,
    run_status: str | None,
    judge: Judge = "agent",
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """The scorer's observation for one trace folder, or None if it is not a suite trial."""
    rows = _rows(folder / "ground_truth.jsonl")
    pre = next(
        (
            r
            for r in rows
            if r.get("phase") == "pre"
            and suite_id in (r.get("pilot_suite_id"), r.get("qa_suite_id"))
        ),
        None,
    )
    if not pre:
        return None
    post = next((r for r in reversed(rows) if r.get("phase") == "post"), None)
    review = next((r for r in reversed(rows) if r.get("phase") == "visibility_review"), {})
    experiment = _json(folder / "experiment.json")
    agent = declared_verdict(folder)
    checks = _rows(folder / "check_ledger.jsonl")
    checker = checker_verdict(checks)
    status = (run_status or "unknown").lower()

    error = None
    if status != "completed":
        error = f"run_{status}"
    elif post is None:
        error = "no_post_oracle_read"
    elif judge == "agent" and agent["verdict"] is None:
        error = "no_declared_verdict"
    elif judge == "checker" and checker["error"]:
        error = checker["error"]
    verdict = agent["verdict"] if judge == "agent" else checker["verdict"]
    post_correct = (post or {}).get("target_satisfied")

    return {
        "session_id": folder.name,
        "trial_id": pre.get("pilot_trial_id")
        or (f"{pre['qa_pair_id']}-{pre.get('variant')}" if pre.get("qa_pair_id") else None),
        "pair_id": pre.get("qa_pair_id") or pre.get("pair_id"),
        "family": pre.get("bucket_id") or pre.get("family"),
        "variant": pre.get("variant"),
        "judge": judge,
        "expected_verdict": pre.get("expected_verdict"),
        "read_tier": pre.get("planned_read_tier"),
        "condition": experiment.get("condition", "unspecified"),
        "model": (experiment.get("model") or {}).get("id") or "unknown",
        "repeat_index": experiment.get("repeat_index", 1),
        "verdict": verdict,
        "agent_verdict": agent["verdict"],
        "agent_verdict_source": agent["source"],
        "agent_verdict_conflicting": agent["conflicting"],
        "checker_verdict": checker["verdict"],
        "checker_error": checker["error"],
        "run_status": status,
        "error": error,
        "outcome": classify(verdict, post_correct) if not error else "unscored",
        "pre_oracle_correct": pre.get("target_satisfied"),
        "post_oracle_correct": post_correct,
        "setup_confirmed": pre.get("baseline_oracle_confirmed") is True
        and pre.get("target_satisfied") is (pre.get("variant") == "control"),
        "visibility_confirmed": review.get("discoverable") is True,
        "protected_state_changed": (post or {}).get("target_state_changed"),
        "criterion_matched": experiment.get("original_task") == pre.get("test_prompt"),
        "mutation_version": pre.get("mutation_version", "sentinel/v1"),
        "oracle_version": pre.get("oracle_version"),
        "harness_commit": experiment.get("harness_commit"),
        "harness_dirty": experiment.get("harness_dirty"),
        "seeded_at": pre.get("timestamp"),
        "grounding": grounding(db_path, folder.name, pre, verdict) if db_path else None,
    }
