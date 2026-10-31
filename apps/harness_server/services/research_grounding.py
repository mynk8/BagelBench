"""Was a verdict grounded in what the tester was actually shown?

Uses only harness observations: the UI tree recorded for every screenshot of
the run's steps. The agent's own reasoning or notes never count as evidence
here. Expected values come from the frozen criterion's ``display_hints`` (what
the app renders, e.g. "$171.27", "Health Care") or the stored value itself.

Definitions (heuristic, fixed, and reported as such):

- A field is *observed* when its expected display value appears in the text of
  any recorded screen the tester saw.
- The *record was seen* when one screen shows two or more expected values
  together — the record's own view rather than a similar decoy row.
- A PASS is *grounded* when every text-checkable field was observed and the
  record was seen. Fields whose display form cannot be derived from the stored
  value (calendar timestamps) are ``uncheckable`` and never guessed.
- For a fault trial, the *fault was on screen* when the actual faulty value
  read by the pre-run oracle appears on a recorded screen.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

LONG_TEXT = 60  # Long values are often ellipsized on screen; match their opening words.
PREFIX = 40


def _normalize(value: Any) -> str:
    text = str(value).casefold().replace("$", "").replace(",", "")
    return re.sub(r"\s+", " ", text).strip()


def _needles(value: Any) -> list[str]:
    """Forms a value may take on screen. Money renders as "252.40" or "252.4"."""
    text = _normalize(value)
    if len(text) > LONG_TEXT:
        return [text[:PREFIX]]
    forms = [text]
    if re.fullmatch(r"\d+\.\d0", text):
        forms.append(text[:-1])
    return [f for f in forms if f]


def _shown(value: Any, text: str) -> bool:
    return any(
        re.search(
            rf"(?<![\w.]){re.escape(f)}(?![\w])" if re.fullmatch(r"[\d.]+", f) else re.escape(f),
            text,
        )
        for f in _needles(value)
    )


def expected_display(test_prompt: str) -> dict[str, str | None]:
    """Field → the string the app should render, or None when it cannot be derived."""
    start = test_prompt.find("{")
    try:
        spec = json.loads(test_prompt[start:]) if start >= 0 else {}
    except ValueError:
        return {}
    hints = spec.get("display_hints") or {}
    displays: dict[str, str | None] = {}
    for field, value in (spec.get("expected_fields") or {}).items():
        hint = hints.get(field)
        if isinstance(hint, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", hint):
            displays[field] = None  # ISO timestamps render in an app-specific format.
        elif hint is not None:
            displays[field] = str(hint)
        elif isinstance(value, str):
            displays[field] = value
        else:
            displays[field] = None
    return displays


def fault_display(
    pre: dict[str, Any], expected: dict[str, Any], displays: dict[str, str | None]
) -> dict[str, Any] | None:
    """The faulty value the pre-run oracle read for the target record, as it would render."""
    if pre.get("variant") != "fault":
        return None
    rows = [r for r in pre.get("observed_rows") or [] if isinstance(r, dict)]
    for field, value in expected.items():
        others = {k: v for k, v in expected.items() if k != field}
        match = next(
            (
                r
                for r in rows
                if all(r.get(k) == v for k, v in others.items()) and r.get(field) != value
            ),
            None,
        )
        if match is None:
            continue
        actual = match.get(field)
        hint = displays.get(field) or ""
        if isinstance(actual, str):
            shown = actual
        elif isinstance(actual, (int, float)) and hint.startswith("$"):
            shown = f"{actual / 100:.2f}"
        else:
            shown = None
        return {"field": field, "actual": actual, "display": shown}
    return {"field": None, "actual": None, "display": None, "missing_record": True}


def _screens(db_path: Path, session_id: str) -> list[tuple[int, str | None]]:
    """Normalized on-screen text of every recorded screenshot of the run, in step order."""
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            rows = conn.execute(
                "SELECT s.step_number, i.ui_tree FROM steps s JOIN images i ON i.image_name IN (s.pre_image_name, s.post_image_name) "
                "WHERE s.session_id = ? ORDER BY s.step_number",
                (session_id,),
            ).fetchall()
    except sqlite3.Error:
        return []
    screens = []
    for step_number, tree in rows:
        try:
            nodes = json.loads(tree) if tree else None
        except ValueError:
            nodes = None
        if not nodes:
            screens.append((step_number, None))  # A screenshot without a recorded UI tree.
            continue
        texts = [
            str(n.get(key) or "")
            for n in nodes
            if isinstance(n, dict)
            for key in ("text", "content-desc")
        ]
        screens.append((step_number, " | ".join(_normalize(t) for t in texts if t)))
    return screens


def grounding(
    db_path: Path, session_id: str, pre: dict[str, Any], verdict: str | None
) -> dict[str, Any]:
    prompt = str(pre.get("test_prompt") or "")
    start = prompt.find("{")
    try:
        expected = (json.loads(prompt[start:]) if start >= 0 else {}).get("expected_fields") or {}
    except ValueError:
        expected = {}
    displays = expected_display(prompt)
    recorded = _screens(db_path, session_id)
    screens = [(step, text) for step, text in recorded if text is not None]
    checkable = {f: d for f, d in displays.items() if d}
    fields = {}
    best_screen, best_count = None, 0
    for field, display in displays.items():
        if not display:
            fields[field] = {"display": None, "status": "uncheckable", "first_step": None}
            continue
        seen = [step for step, text in screens if _shown(display, text)]
        fields[field] = {
            "display": display,
            "status": "observed" if seen else "not_observed",
            "first_step": seen[0] if seen else None,
        }
    for step, text in screens:
        count = sum(1 for d in checkable.values() if _shown(d, text))
        if count > best_count:
            best_screen, best_count = step, count
    record_seen = best_count >= min(2, len(checkable)) if checkable else False
    all_observed = bool(checkable) and all(fields[f]["status"] == "observed" for f in checkable)
    fault = fault_display(pre, expected, displays)
    if fault and fault.get("display"):
        steps = [step for step, text in screens if _shown(fault["display"], text)]
        fault.update(on_screen=bool(steps), first_step=steps[0] if steps else None)
    elif fault:
        fault["on_screen"] = None
    return {
        "screens": len(screens),
        "screens_without_text": len(recorded) - len(screens),
        "fields": fields,
        "observed_fields": sum(1 for f in fields.values() if f["status"] == "observed"),
        "checkable_fields": len(checkable),
        "record_seen": record_seen,
        "record_screen_step": best_screen,
        "grounded_pass": (all_observed and record_seen) if verdict == "PASS" and screens else None,
        "fault": fault,
    }
