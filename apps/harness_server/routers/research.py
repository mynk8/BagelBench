"""Research-only state fixtures and screenshot evidence review."""

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from artemis.config import DB_PATH, IMAGES_DIR, TRACES_PATH, WORKSPACE_ROOT
from apps.research_ui.scripts.qa_pilot import load_manifest, sha
from artemis.services.androidworld_fixture import SUPPORTED_TASKS, invoke
from apps.harness_server.services.research_batch import BatchRequest, BatchRunner
from apps.harness_server.services.research_trials import trial_observation
from apps.harness_server.services import qa_catalog

router = APIRouter(tags=["research"])
_BATCH_ID = re.compile(r"[0-9a-f-]{36}")


class AndroidWorldSeed(BaseModel):
    task_name: str
    pilot_trial_id: str | None = None
    device_serial: str = Field(pattern=r"^emulator-\d+$")
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    fault_seed: bool = True
    operation: str = Field(
        default="delete_target", pattern="^(delete_target|change_value|truncate_text|shift_date)$"
    )
    field: str | None = None


@router.get("/api/research/androidworld/tasks")
def tasks():
    return {"tasks": list(SUPPORTED_TASKS)}


@router.post("/api/research/androidworld/seed")
async def seed(request: AndroidWorldSeed):
    if request.task_name not in SUPPORTED_TASKS:
        raise HTTPException(422, "Unsupported AndroidWorld task.")
    payload = request.model_dump()
    provenance = {}
    if request.pilot_trial_id:
        manifest = pilot_manifest()
        trial = next(
            (r for r in manifest["trials"] if r["trial_id"] == request.pilot_trial_id), None
        )
        if not trial:
            raise HTTPException(422, "Unknown frozen pilot trial.")
        instance = next(r for r in manifest["instances"] if r["pair_id"] == trial["pair_id"])
        payload.update(
            task_name=instance["task_name"],
            seed=instance["seed"],
            operation=instance["operation"],
            field=instance["field"],
            fault_seed=trial["variant"] == "fault",
            frozen_instance=instance,
        )
        provenance = {
            "pilot_suite_id": manifest["suite_id"],
            "pilot_trial_id": trial["trial_id"],
            "pair_id": trial["pair_id"],
            "family": trial["family"],
            "variant": trial["variant"],
            "criterion_sha256": sha(instance["test_prompt"]),
        }
    return await _prepare_fixture(payload, provenance)


async def _prepare_fixture(payload: dict, provenance: dict) -> dict:
    """Seed the device, confirm the variant with a pre-run read, and keep the record pending attachment."""
    try:
        result = await asyncio.to_thread(invoke, {"mode": "prepare", **payload})
    except Exception as error:
        raise HTTPException(409, str(error)) from None
    screenshot_data = result.pop("_screenshot_base64", None)
    record = {
        **result,
        **{k: v for k, v in payload.items() if k != "frozen_instance"},
        **provenance,
        "intervention_id": str(uuid4()),
        "phase": "pre",
        "fixture": "androidworld",
        "seeded_fault": payload["fault_seed"],
        "timestamp": time.time(),
        "visibility_status": "unreviewed",
    }
    pending = Path(TRACES_PATH) / "ground_truth_pending"
    pending.mkdir(parents=True, exist_ok=True)
    # A screenshot documents exposure, but does not establish visibility by itself.
    if screenshot_data:
        screenshot = base64.b64decode(screenshot_data)
        name = f"fixture-{record['intervention_id']}.png"
        Path(IMAGES_DIR).mkdir(parents=True, exist_ok=True)
        (Path(IMAGES_DIR) / name).write_bytes(screenshot)
        record["screenshot"] = name
        record["screenshot_sha256"] = hashlib.sha256(screenshot).hexdigest()
    (pending / f"{record['intervention_id']}.json").write_text(json.dumps(record, sort_keys=True))
    return record


class QaSeed(BaseModel):
    pair_id: str = Field(pattern=r"^qa-[0-9a-f]{20}$")
    variant: str = Field(pattern="^(control|fault)$")
    device_serial: str = Field(pattern=r"^emulator-\d+$")


@router.get("/api/research/qa/pairs")
def qa_pairs(app: str | None = None, bucket_id: str | None = None, live_only: bool = False):
    """Frozen QA pair catalog: actor-visible instruction and live-adapter status only."""
    cat = qa_catalog.catalog()
    return {
        "suite_id": cat["suite_id"],
        "dataset_files_sha256": cat["files"],
        "pairs": qa_catalog.list_pairs(app, bucket_id, live_only),
    }


@router.post("/api/research/qa/seed")
async def qa_seed(request: QaSeed):
    try:
        bridge = qa_catalog.seed_request(request.pair_id, request.variant)
    except KeyError as error:
        raise HTTPException(404, str(error)) from None
    except LookupError as error:
        raise HTTPException(422, f"Pair cannot run live: {error}") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    provenance = bridge.pop("provenance")
    payload = {**bridge, "device_serial": request.device_serial}
    return await _prepare_fixture(payload, provenance)


class VisionRequest(BaseModel):
    step_id: str
    phase: str = Field(default="post", pattern="^(pre|post)$")
    question: str = Field(min_length=3, max_length=4000)


@router.post("/api/sessions/{session_id}/vision")
async def vision(session_id: str, request: VisionRequest):
    root = Path(TRACES_PATH).resolve()
    folder = (root / session_id).resolve()
    if folder.parent != root or not folder.is_dir():
        raise HTTPException(404, "Session not found.")
    from apps.harness_server.routers.media import step_repo

    rows = await asyncio.to_thread(step_repo.get_session_steps, session_id)
    step = next((r for r in rows if r.get("step_id") == request.step_id), None)
    if not step:
        raise HTTPException(404, "Step not found.")
    raw = step.get(f"{request.phase}_image_name") or step.get(f"{request.phase}_screenshot")
    if not raw:
        raise HTTPException(404, "Screenshot not recorded.")
    image_root = Path(IMAGES_DIR).resolve()
    path = (image_root / Path(raw).name).resolve()
    if path.parent != image_root or not path.is_file():
        raise HTTPException(404, "Screenshot unavailable.")
    key = os.environ.get("ARTEMIS_VISION_API_KEY")
    model = os.environ.get("ARTEMIS_VISION_MODEL")
    if not key or not model:
        raise HTTPException(
            503, "Set ARTEMIS_VISION_API_KEY and ARTEMIS_VISION_MODEL for screenshot review."
        )
    picture = path.read_bytes()
    mime = "image/jpeg" if picture.startswith(b"\xff\xd8") else "image/png"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "Review only the supplied Android screenshot. Return JSON with observations (list of strings), answer, evidence_sufficiency (sufficient/insufficient), and limitations (list). Describe visible evidence; do not infer hidden app state or use confidence as ground truth.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.question},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64," + base64.b64encode(picture).decode()
                        },
                    },
                ],
            },
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                os.environ.get("ARTEMIS_VISION_BASE_URL", "https://openrouter.ai/api/v1").rstrip(
                    "/"
                )
                + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
            raw_response = response.json()
        answer = json.loads(raw_response["choices"][0]["message"]["content"])
    except Exception:
        raise HTTPException(502, "Vision request failed or returned invalid JSON.") from None
    record = {
        **request.model_dump(),
        "id": str(uuid4()),
        "model": raw_response.get("model", model),
        "timestamp": time.time(),
        "source": "screenshot",
        "classification": "model_reported",
        "screenshot": path.name,
        "screenshot_sha256": hashlib.sha256(picture).hexdigest(),
        "answer": answer,
        "request": payload,
        "response": raw_response,
    }
    with (folder / "vision.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    return record


def pilot_manifest():
    return load_manifest(
        Path(WORKSPACE_ROOT) / "apps/research_ui/datasets/androidworld/pilot_v1.json"
    )


@router.get("/api/research/pilot")
def get_pilot():
    return pilot_manifest()


class VisibilityReview(BaseModel):
    discoverable: bool
    evidence: str = Field(min_length=8, max_length=4000)


@router.post("/api/sessions/{session_id}/ground-truth/visibility-review")
def review_visibility(session_id: str, request: VisibilityReview):
    root = Path(TRACES_PATH).resolve()
    folder = (root / session_id).resolve()
    if folder.parent != root or not (folder / "ground_truth.jsonl").is_file():
        raise HTTPException(404, "Fixture record not found.")
    record = {
        **request.model_dump(),
        "phase": "visibility_review",
        "timestamp": time.time(),
        "source": "human_review",
    }
    with (folder / "ground_truth.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    return record


def _run_status(session_id: str) -> str | None:
    try:
        from apps.harness_server.database.repositories.session_repository import session_repo

        return (session_repo.get_session_by_id(session_id) or {}).get("status")
    except Exception:
        return None


def suite_observations(judge: str = "agent", suite_id: str | None = None) -> list[dict]:
    """Every recorded trial of a frozen suite (the pilot by default), scored only from its own artifacts."""
    suite_id = suite_id or pilot_manifest()["suite_id"]
    records = []
    for path in sorted(Path(TRACES_PATH).glob("*/ground_truth.jsonl")):
        record = trial_observation(
            path.parent, suite_id, _run_status(path.parent.name), judge, Path(DB_PATH)
        )
        if record:
            records.append(record)
    return sorted(records, key=lambda row: row.get("seeded_at") or 0)


def _judge(judge: str) -> str:
    if judge not in ("agent", "checker"):
        raise HTTPException(422, "judge must be 'agent' or 'checker'.")
    return judge


@router.get("/api/research/pilot/observations")
def pilot_observations(judge: str = "agent"):
    from fastapi.responses import Response

    records = suite_observations(_judge(judge))
    return Response(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in records),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="pilot-observations-{judge}.jsonl"'},
    )


@router.get("/api/research/pilot/score")
def pilot_score(judge: str = "agent"):
    """The frozen scorer over every recorded trial, plus each trial's admission state."""
    from apps.research_ui.scripts.score_pilot import admission, score

    manifest = pilot_manifest()
    observations = suite_observations(_judge(judge))
    trials = {t["trial_id"]: t for t in manifest["trials"]}
    # The scorer keeps one observation per trial/condition/model/repeat; later runs of the same slot are reruns.
    latest = {}
    for row in observations:
        latest[(row["trial_id"], row["condition"], row["model"], row["repeat_index"])] = row
    result = score(manifest, list(latest.values())) if latest else {"groups": []}
    rows = [
        {
            **row,
            "admission": admission(trials[row["trial_id"]], row),
            "superseded": latest[
                (row["trial_id"], row["condition"], row["model"], row["repeat_index"])
            ]
            is not row,
        }
        for row in observations
    ]
    current = [row for row in rows if not row["superseded"] and row["grounding"]]
    passes = [row for row in current if row["verdict"] == "PASS"]
    false_passes = [row for row in current if row["outcome"] == "false_pass"]
    grounding_summary = {
        "pass_verdicts": len(passes),
        "grounded_passes": sum(row["grounding"]["grounded_pass"] is True for row in passes),
        "ungrounded_passes": sum(row["grounding"]["grounded_pass"] is False for row in passes),
        "false_passes": len(false_passes),
        "false_passes_with_fault_on_screen": sum(
            (row["grounding"]["fault"] or {}).get("on_screen") is True for row in false_passes
        ),
        "note": "Heuristic over recorded UI-tree text; includes trials not yet admitted. Screens without a UI tree are not searched.",
    }
    return {
        **result,
        "grounding": grounding_summary,
        "judge": judge,
        "suite_id": manifest["suite_id"],
        "scheduled_trials": len(manifest["trials"]),
        "observations": rows,
    }


@router.get("/api/sessions/{session_id}/trial")
def session_trial(session_id: str):
    """How one run scores as a suite trial, for both judges."""
    from apps.research_ui.scripts.score_pilot import admission

    root = Path(TRACES_PATH).resolve()
    folder = (root / session_id).resolve()
    if folder.parent != root or not folder.is_dir():
        raise HTTPException(404, "Session not found.")
    manifest = pilot_manifest()
    trials = {t["trial_id"]: t for t in manifest["trials"]}
    result = {}
    for judge in ("agent", "checker"):
        row = None
        for suite_id in (qa_catalog.catalog()["suite_id"], manifest["suite_id"]):
            row = trial_observation(folder, suite_id, _run_status(session_id), judge, Path(DB_PATH))
            if row:
                break
        # Admission only needs the trial's variant, which every suite records.
        result[judge] = row and {
            **row,
            "admission": admission(trials.get(row["trial_id"]) or {"variant": row["variant"]}, row),
        }
    return result


@router.post("/api/research/batches")
async def start_batch(request: BatchRequest, http_request: Request):
    """Queues a batch that runs on the server, independent of any browser tab."""
    if request.fixture_kind in ("androidworld", "pilot") and not request.device_serial.startswith(
        "emulator-"
    ):
        raise HTTPException(422, "Select a dedicated AndroidWorld emulator.")
    if BatchRunner.active_for_device(request.device_serial):
        raise HTTPException(409, "Another batch is already running on this device.")
    return BatchRunner.start(http_request.app, request)


@router.get("/api/research/batches")
def list_batches(limit: int = 20):
    return {"batches": BatchRunner.list(max(1, min(limit, 100)))}


@router.get("/api/research/batches/{batch_id}")
def get_batch(batch_id: str):
    state = BatchRunner.read(batch_id) if _BATCH_ID.fullmatch(batch_id) else None
    if not state:
        raise HTTPException(404, "Batch not found.")
    return state


@router.post("/api/research/batches/{batch_id}/stop")
async def stop_batch(batch_id: str, http_request: Request):
    state = (
        await BatchRunner.stop(http_request.app, batch_id)
        if _BATCH_ID.fullmatch(batch_id)
        else None
    )
    if not state:
        raise HTTPException(404, "Batch not found.")
    return state


@router.get("/api/research/qa/verify")
def qa_verify(pair_id: str | None = None, bucket_id: str | None = None):
    """Offline reference check of the dataset contract; never a device observation."""
    try:
        return qa_catalog.verify_reference(pair_id, bucket_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from None


@router.get("/api/research/batches/{batch_id}/report")
def batch_report(batch_id: str):
    state = BatchRunner.read(batch_id) if _BATCH_ID.fullmatch(batch_id) else None
    if not state:
        raise HTTPException(404, "Batch not found.")
    report = BatchRunner.report_path(batch_id)
    if not report.is_file():
        raise HTTPException(404, "The report is written when the batch ends.")
    return json.loads(report.read_text(encoding="utf-8"))


def _efficiency(session_id: str) -> dict:
    """Steps, wall time and tokens for one run, from the harness's own records."""
    try:
        from apps.harness_server.database.repositories.session_repository import session_repo

        session = session_repo.get_session_by_id(session_id) or {}
        usage = session_repo.get_session_usage(session_id) or {}
    except Exception:
        session, usage = {}, {}
    try:
        import sqlite3

        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            steps = conn.execute(
                "SELECT COUNT(*) FROM steps WHERE session_id=?", (session_id,)
            ).fetchone()[0]
    except Exception:
        steps = None
    start, end = session.get("start_time"), session.get("end_time")
    return {
        "steps": steps,
        "seconds": (end - start) if start and end else None,
        "tokens": usage.get("total_tokens"),
        "llm_calls": usage.get("llm_calls"),
    }


def _rate(numerator: int, denominator: int) -> dict:
    from apps.research_ui.scripts.score_pilot import proportion

    return proportion(numerator, denominator)


def _mean(values: list) -> float | None:
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def _summarize(rows: list[dict]) -> dict:
    """Benchmark metrics over a set of runs. Only runs with a recorded outcome are counted."""
    counted = [r for r in rows if not r["error"] and r["outcome"] != "unscored"]
    faults = [r for r in counted if r["variant"] == "fault"]
    controls = [r for r in counted if r["variant"] == "control"]
    correct = [r for r in counted if r["outcome"] in ("correct_pass", "correct_fail")]
    pairs: dict = {}
    for r in counted:
        pairs.setdefault((r["pair_id"], r["condition"], r["model"], r["repeat_index"]), {})[
            r["variant"]
        ] = r
    complete = [p for p in pairs.values() if "control" in p and "fault" in p]
    return {
        "runs": len(rows),
        "counted": len(counted),
        "excluded": len(rows) - len(counted),
        "accuracy": _rate(len(correct), len(counted)),
        "wrong_pass": _rate(sum(r["outcome"] == "false_pass" for r in faults), len(faults)),
        "wrong_fail": _rate(sum(r["outcome"] == "false_fail" for r in controls), len(controls)),
        "no_decision": _rate(sum(r["outcome"] == "inconclusive" for r in counted), len(counted)),
        "pair_accuracy": _rate(
            sum(
                p["control"]["outcome"] == "correct_pass"
                and p["fault"]["outcome"] == "correct_fail"
                for p in complete
            ),
            len(complete),
        ),
        "outcomes": {
            k: sum(r["outcome"] == k for r in counted)
            for k in ("correct_pass", "correct_fail", "false_pass", "false_fail", "inconclusive")
        },
        "mean_steps": _mean([r["efficiency"]["steps"] for r in counted]),
        "mean_seconds": _mean([r["efficiency"]["seconds"] for r in counted]),
        "mean_tokens": _mean([r["efficiency"]["tokens"] for r in counted]),
    }


@router.get("/api/research/eval/score")
def eval_score(judge: str = "agent", suite: str = "eval"):
    """Benchmark readout for the eval set: leaderboard, breakdowns and per-run rows.

    Every number is recomputed from saved run folders. Runs that could not be
    scored (cancelled, no state read, no verdict) are excluded with their reason.
    """
    if suite not in ("eval", "pilot"):
        raise HTTPException(422, "suite must be 'eval' or 'pilot'.")
    if suite == "eval":
        suite_id = qa_catalog.catalog()["suite_id"]
        pairs = {
            k: {"app": v["app"], "bucket": v["bucket"], "mechanism": v["mechanism"]}
            for k, v in qa_catalog.catalog()["pairs"].items()
        }
    else:
        manifest = pilot_manifest()
        suite_id = manifest["suite_id"]
        apps = {
            "SimpleCalendarAddOneEvent": "Simple Calendar Pro",
            "ExpenseAddSingle": "Pro Expense",
            "RecipeAddSingleRecipe": "Broccoli",
        }
        pairs = {
            i["pair_id"]: {
                "app": apps.get(i["task_name"], i["task_name"]),
                "bucket": "Record integrity",
                "mechanism": f"{i['operation']}:{i['field']}" if i.get("field") else i["operation"],
            }
            for i in manifest["instances"]
        }
    rows = []
    for row in suite_observations(_judge(judge), suite_id):
        pair = pairs.get(row["pair_id"]) or {}
        rows.append(
            {
                **row,
                "app": pair.get("app"),
                "bucket": pair.get("bucket"),
                "mechanism": pair.get("mechanism"),
                "efficiency": _efficiency(row["session_id"]),
            }
        )

    def group(key):
        out: dict = {}
        for r in rows:
            out.setdefault(key(r), []).append(r)
        return out

    leaderboard = [
        {"model": m, "condition": c, **_summarize(rs)}
        for (m, c), rs in sorted(group(lambda r: (r["model"], r["condition"])).items())
    ]

    def by(key: str) -> list[dict]:
        return [
            {"name": k, **_summarize(rs)}
            for k, rs in sorted(group(lambda r: r[key] or "unknown").items())
        ]

    exclusions: dict = {}
    for r in rows:
        if r["error"]:
            exclusions[r["error"]] = exclusions.get(r["error"], 0) + 1
    return {
        "suite_id": suite_id,
        "judge": judge,
        "overall": _summarize(rows),
        "leaderboard": leaderboard,
        "by_bucket": by("bucket"),
        "by_app": by("app"),
        "by_mechanism": by("mechanism"),
        "exclusions": exclusions,
        "runs": sorted(rows, key=lambda r: r.get("seeded_at") or 0, reverse=True),
    }
