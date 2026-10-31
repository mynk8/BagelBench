# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import functools
import hashlib
import io
import json
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from artemis.config import DB_PATH, IMAGES_DIR, TRACES_PATH, WORKSPACE_ROOT

try:
    from harness_server.database.connection import db_session
    from harness_server.database.repositories.session_repository import session_repo
    from harness_server.database.repositories.step_repository import step_repo
    from harness_server.services.media_service import media_service
except ImportError:
    from apps.harness_server.database.connection import db_session
    from apps.harness_server.database.repositories.session_repository import session_repo
    from apps.harness_server.database.repositories.step_repository import step_repo
    from apps.harness_server.services.media_service import media_service

router = APIRouter(tags=["media"])


class GroundTruthAttachRequest(BaseModel):
    intervention_id: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=80)


class ExperimentMetadataRequest(BaseModel):
    condition: str = Field(default="baseline", min_length=1, max_length=120)
    framing: str = Field(default="plain", pattern="^(plain|observe_only|release_blocked)$")
    test_length: str = Field(default="short", pattern="^(short|long)$")
    original_task: str = Field(min_length=1, max_length=10000)
    authored_task: str | None = Field(default=None, max_length=10000)
    repeat_index: int = Field(default=1, ge=1, le=100)
    batch_id: str = ""
    test_class: str = Field(
        default="functional", pattern="^(functional|impossible|destructive_cheat)$"
    )
    switches: dict[str, bool | str] = Field(default_factory=dict)


@router.post("/api/ground-truth/attach")
async def attach_ground_truth(request: GroundTruthAttachRequest):
    """Attach a verified pre-run intervention to its newly created trace."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", request.intervention_id):
        raise HTTPException(status_code=422, detail="Invalid intervention id.")
    folder = (Path(TRACES_PATH).resolve() / request.session_id).resolve()
    if folder.parent != Path(TRACES_PATH).resolve() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Session trace folder not found.")
    source = (
        Path(TRACES_PATH).resolve() / "ground_truth_pending" / f"{request.intervention_id}.json"
    )
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Ground-truth seed record not found.")
    record = json.loads(source.read_text(encoding="utf-8"))
    record.update(session_id=request.session_id, attached_at=time.time())
    destination = folder / "ground_truth.jsonl"
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    source.unlink(missing_ok=True)
    return {"attached": True, "record": record}


@functools.cache
def _harness_revision() -> dict[str, Any]:
    """The code that produced a run, so every result traces back to an exact commit."""
    try:
        root = Path(WORKSPACE_ROOT)
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        )
        return {"harness_commit": commit, "harness_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"harness_commit": None, "harness_dirty": None}


@router.post("/api/sessions/{session_id}/experiment")
async def save_experiment_metadata(session_id: str, request: ExperimentMetadataRequest):
    folder = (Path(TRACES_PATH).resolve() / session_id).resolve()
    if folder.parent != Path(TRACES_PATH).resolve() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Session trace folder not found.")
    effective_switches: dict[str, bool | str] = {
        "ARTEMIS_CHECKER_DEVICE_PROBES": os.environ.get("ARTEMIS_CHECKER_DEVICE_PROBES", "1")
        .strip()
        .lower()
        not in ("0", "false", "off"),
        "ARTEMIS_CHECKER_CLAIM_BLIND": os.environ.get("ARTEMIS_CHECKER_CLAIM_BLIND", "0")
        .strip()
        .lower()
        in ("1", "true", "yes", "on"),
        "ARTEMIS_PASS_GUARD": os.environ.get("ARTEMIS_PASS_GUARD", "0").strip().lower()
        in ("1", "true", "yes", "on"),
        "ARTEMIS_CHECKER_EVIDENCE_MODE": os.environ.get("ARTEMIS_CHECKER_EVIDENCE_MODE", "fused"),
        "ARTEMIS_THINKING_ENABLED": os.environ.get("ARTEMIS_THINKING_ENABLED", "0").strip().lower()
        in ("1", "true", "yes", "on"),
    }
    effective_switches.update(request.switches)
    record = {
        **request.model_dump(exclude={"switches"}),
        "switches": effective_switches,
        "session_id": session_id,
        "recorded_at": time.time(),
        **_harness_revision(),
        "model": {
            "provider": os.environ.get("ARTEMIS_MODEL_PROVIDER", "config"),
            "id": os.environ.get("ARTEMIS_OPENROUTER_MODEL")
            if os.environ.get("ARTEMIS_MODEL_PROVIDER") == "openrouter"
            else os.environ.get("ARTEMIS_DEEPSEEK_MODEL")
            if os.environ.get("ARTEMIS_MODEL_PROVIDER") == "deepseek"
            else None,
        },
    }
    target = folder / "experiment.json"
    target.write_text(
        json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


@router.get("/api/sessions/{session_id}/experiment")
async def get_experiment_metadata(session_id: str):
    folder = (Path(TRACES_PATH).resolve() / session_id).resolve()
    if folder.parent != Path(TRACES_PATH).resolve() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Session not found.")
    path = folder / "experiment.json"
    if not path.is_file():
        return {"condition": "unspecified", "framing": "unknown", "test_length": "unknown"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="Experiment metadata is invalid.") from None


_VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}


@router.get("/api/sessions/{session_id}/research-export")
async def export_research_run(session_id: str):
    """Package the saved run ledger and referenced screenshots for offline replay."""
    session_dir = (Path(TRACES_PATH).resolve() / session_id).resolve()
    if session_dir.parent != Path(TRACES_PATH).resolve() or not session_dir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        steps = await asyncio.to_thread(step_repo.get_session_steps, session_id)
        checks = await asyncio.to_thread(media_service.get_session_checks, session_id)
        usage = await asyncio.to_thread(session_repo.get_session_usage, session_id)
        session = await asyncio.to_thread(session_repo.get_session_by_id, session_id)
        trace_records = await asyncio.to_thread(_read_complete_session_traces, session_id)
    except Exception:
        raise HTTPException(
            status_code=500, detail="The saved run could not be exported."
        ) from None
    files: dict[str, bytes] = {
        "steps.json": json.dumps(steps, ensure_ascii=False, default=str, indent=2).encode(),
        "checks.json": json.dumps(checks, ensure_ascii=False, default=str, indent=2).encode(),
        "usage.json": json.dumps(usage, ensure_ascii=False, default=str, indent=2).encode(),
        "session.json": json.dumps(session, ensure_ascii=False, default=str, indent=2).encode(),
        "llm-traces.jsonl": "\n".join(
            json.dumps(row, ensure_ascii=False, default=str) for row in trace_records
        ).encode(),
    }
    report_script = Path(WORKSPACE_ROOT) / "apps" / "research_ui" / "scripts" / "replay_report.py"
    if report_script.is_file():
        files["analysis/replay_report.py"] = report_script.read_bytes()
    for name in ("score_pilot.py", "qa_pilot.py"):
        source = Path(WORKSPACE_ROOT) / "apps/research_ui/scripts" / name
        if source.is_file():
            files[f"analysis/{name}"] = source.read_bytes()
    pilot = Path(WORKSPACE_ROOT) / "apps/research_ui/datasets/androidworld/pilot_v1.json"
    if pilot.is_file():
        files["pilot_v1.json"] = pilot.read_bytes()
    files["analysis/README.txt"] = (
        b"Offline aggregation: python analysis/replay_report.py run-a.zip run-b.zip --csv report.csv --svg report.svg\nNo model or device calls are made. The script verifies file checksums in each run bundle.\n"
    )
    experiment_file = session_dir / "experiment.json"
    if experiment_file.is_file():
        files["experiment.json"] = experiment_file.read_bytes()
    ground_truth_file = session_dir / "ground_truth.jsonl"
    if ground_truth_file.is_file():
        files["ground_truth.jsonl"] = ground_truth_file.read_bytes()
    vision_file = session_dir / "vision.jsonl"
    if vision_file.is_file():
        files["vision.jsonl"] = vision_file.read_bytes()
    if ground_truth_file.is_file():
        for line in ground_truth_file.read_text().splitlines():
            record = json.loads(line)
            if record.get("screenshot"):
                source = Path(IMAGES_DIR) / Path(record["screenshot"]).name
                if source.is_file():
                    files[f"screenshots/{source.name}"] = source.read_bytes()
    config_file = Path(WORKSPACE_ROOT) / "config" / "artemis.jsonc"
    if config_file.is_file():
        files["config/artemis.jsonc"] = config_file.read_bytes()
    images_root = Path(IMAGES_DIR).resolve()
    for step in steps or []:
        for key in ("pre_image_name", "post_image_name", "pre_screenshot", "post_screenshot"):
            raw = step.get(key)
            if not raw:
                continue
            source = (images_root / Path(str(raw)).name).resolve()
            if source.is_file() and source.is_relative_to(images_root):
                files.setdefault(f"screenshots/{source.name}", source.read_bytes())
    dirty = None
    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=WORKSPACE_ROOT,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
            or None
        )
        dirty = (
            bool(
                subprocess.run(
                    ["git", "status", "--short"],
                    cwd=WORKSPACE_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                ).stdout.strip()
            )
            if commit
            else None
        )
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    try:
        experiment_snapshot = json.loads(
            (session_dir / "experiment.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        experiment_snapshot = {}
    manifest = {
        "schema_version": "artemis-research-run/v3",
        "session_id": session_id,
        "exported_at": time.time(),
        "code_commit": commit,
        "working_tree_dirty": dirty,
        "model": (session or {}).get("model_info") or experiment_snapshot.get("model"),
        "model_environment": {
            k: os.environ.get(k)
            for k in (
                "ARTEMIS_MODEL_PROVIDER",
                "ARTEMIS_DEEPSEEK_MODEL",
                "ARTEMIS_OPENROUTER_MODEL",
                "ARTEMIS_OPENROUTER_ONLY_PROVIDER",
                "ARTEMIS_THINKING_ENABLED",
                "ARTEMIS_OBSERVER_MODEL",
            )
        },
        "device": {k: (session or {}).get(k) for k in ("device_serial", "device_info")},
        "switches": experiment_snapshot.get("switches")
        or {
            k: os.environ.get(k)
            for k in (
                "ARTEMIS_CHECKER_CLAIM_BLIND",
                "ARTEMIS_PASS_GUARD",
                "ARTEMIS_CHECKER_DEVICE_PROBES",
                "ARTEMIS_CHECKER_EVIDENCE_MODE",
                "ARTEMIS_THINKING_ENABLED",
            )
        },
        "independent_outcome": (checks or {}).get("run_outcome")
        or {"status": "unknown", "source": None},
        "sha256": {name: hashlib.sha256(body).hexdigest() for name, body in sorted(files.items())},
    }
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    from fastapi.responses import Response

    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="artemis-{session_id}.zip"'},
    )


def _read_complete_session_traces(session_id: str) -> list[dict[str, Any]]:
    try:
        with db_session(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT trace_id,parent_trace_id,step_id,type,name,status,timestamp,duration,payload FROM traces WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        records = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("payload"), str):
                try:
                    item["payload"] = json.loads(item["payload"])
                except ValueError:
                    pass
            records.append(item)
        return records
    except Exception:
        raise


def _allowed_media_roots() -> list[Path]:
    """Directories the media endpoints are permitted to serve from."""
    roots = []
    for root in (WORKSPACE_ROOT, TRACES_PATH):
        try:
            roots.append(Path(root).resolve())
        except OSError:
            continue
    return roots


def _resolve_media_path(raw_path: str, allowed_suffixes: set[str]) -> Path:
    """Resolve a client-supplied path strictly inside the allowed media roots.

    Every candidate is fully resolved (symlinks, `..`, mixed separators) and
    then re-checked against the allowed roots and an extension allowlist, so a
    crafted URL can never address source code, databases, or dotfiles.
    """
    roots = _allowed_media_roots()
    candidate = Path(raw_path)
    attempts = [candidate] if candidate.is_absolute() else [root / candidate for root in roots]
    for attempt in attempts:
        try:
            resolved = attempt.resolve(strict=True)
        except (OSError, ValueError):
            continue
        if not resolved.is_file():
            continue
        if not any(resolved.is_relative_to(root) for root in roots):
            continue
        if resolved.suffix.lower() not in allowed_suffixes:
            raise HTTPException(status_code=403, detail="File type is not served by the media API.")
        return resolved
    raise HTTPException(status_code=404, detail="Media file not found")


@router.get("/images/{image_name}")
@router.get("/api/images/{image_name}")
async def get_image(image_name: str):
    if not image_name.endswith(".jpg"):
        image_name += ".jpg"
    try:
        images_root = IMAGES_DIR.resolve()
        image_path = (images_root / image_name).resolve(strict=True)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Image not found")
    if not image_path.is_file() or not image_path.is_relative_to(images_root):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path, media_type="image/jpeg")


@router.get("/videos/{video_path:path}")
async def get_video(video_path: str):
    path = _resolve_media_path(video_path, set(_VIDEO_MEDIA_TYPES))
    return FileResponse(path, media_type=_VIDEO_MEDIA_TYPES[path.suffix.lower()])


@router.get("/api/sessions/{session_id}/video")
async def get_session_video(session_id: str):
    # Blocking work (sqlite, filesystem scan, possible ffmpeg conversion) runs
    # off the event loop.
    return await asyncio.to_thread(_get_session_video_sync, session_id)


def _get_session_video_sync(session_id: str):
    video_rec_map = session_repo.get_video_recordings_map()
    video_idx = media_service.build_video_index()
    row = session_repo.get_session_by_id(session_id)
    row_dict = dict(row) if row else {"session_id": session_id}
    recording = session_repo.get_video_recording_for_session(session_id)
    recording_status = str((recording or {}).get("status") or "")

    if recording_status in ("recording", "finalizing"):
        return {
            "session_id": session_id,
            "status": "processing",
            "has_video": False,
            "video_url": None,
            "video_segments": [],
            "retry_after_ms": 750,
        }

    if recording_status == "failed":
        v_url = media_service.resolve_video_url(row_dict, video_rec_map, video_idx)
        if not v_url:
            return {
                "session_id": session_id,
                "status": "failed",
                "has_video": False,
                "video_url": None,
                "video_segments": [],
                "message": recording.get("error") or "Recording finalization failed",
            }
        # If a video was recovered/found, update DB to ready and proceed to serve it
        session_repo.mark_recording_ready(session_id, v_url)

    v_url = media_service.resolve_video_url(row_dict, video_rec_map, video_idx)
    video_segments = media_service.resolve_video_segments(v_url)
    if v_url:
        version = int(
            float((recording or {}).get("end_time") or row_dict.get("end_time") or 0) * 1000
        )
        separator = "&" if "?" in v_url else "?"
        versioned_url = f"{v_url}{separator}v={version}" if version else v_url
        for segment in video_segments:
            segment_separator = "&" if "?" in segment["url"] else "?"
            segment["url"] = (
                f"{segment['url']}{segment_separator}v={version}" if version else segment["url"]
            )
        return {
            "session_id": session_id,
            "status": "ready",
            "has_video": True,
            "video_url": versioned_url,
            "video_segments": video_segments,
        }

    return {
        "session_id": session_id,
        "status": "unavailable",
        "has_video": False,
        "video_url": None,
        "video_segments": [],
    }


@router.get("/api/sessions/{session_id}/checks")
async def get_session_checks(session_id: str):
    """Checker verdict ledger + run outcome (backfill for the Checker panel)."""
    result = media_service.get_session_checks(session_id)
    path = (Path(TRACES_PATH).resolve() / session_id / "ground_truth.jsonl").resolve()
    if path.parent.parent == Path(TRACES_PATH).resolve() and path.is_file():
        try:
            result["ground_truth"] = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError):
            result["ground_truth"] = []
    return result


@router.post("/api/sessions/{session_id}/ground-truth/finalize")
async def finalize_ground_truth(session_id: str):
    folder = (Path(TRACES_PATH).resolve() / session_id).resolve()
    if folder.parent != Path(TRACES_PATH).resolve() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Session not found.")
    path = folder / "ground_truth.jsonl"
    try:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValueError):
        raise HTTPException(
            status_code=404, detail="No pre-run ground-truth record is attached."
        ) from None
    seed = next((row for row in records if row.get("phase") == "pre"), None)
    if not seed:
        raise HTTPException(status_code=404, detail="No pre-run ground-truth record is attached.")
    existing = next((row for row in reversed(records) if row.get("phase") == "post"), None)
    if existing:
        # The post-run read happens once; a repeat must not append a second outcome.
        return existing
    try:
        from artemis.runtime import DeviceExecutionLock

        if DeviceExecutionLock.get_active_owner(seed["device_serial"]):
            raise HTTPException(
                status_code=409, detail="The selected device is still in use by this run."
            )
    except HTTPException:
        raise
    except Exception:
        pass
    if seed.get("fixture") == "androidworld":
        from artemis.services.androidworld_fixture import invoke

        try:
            result = await asyncio.to_thread(
                invoke,
                {
                    "mode": "check",
                    "device_serial": seed["device_serial"],
                    "task_name": seed["task_name"],
                    "snapshot": seed["snapshot"],
                },
            )
        except Exception as error:
            raise HTTPException(409, str(error)) from None
        statuses = media_service.get_session_checks(session_id).get("records", [])
        verdict = (
            str(statuses[-1].get("status", "inconclusive")).lower() if statuses else "inconclusive"
        )
        verdict = {"pass": "passed", "fail": "failed"}.get(verdict, verdict)
        truth = result["target_satisfied"]
        metadata_file = folder / "experiment.json"
        metadata = json.loads(metadata_file.read_text()) if metadata_file.is_file() else {}
        criterion_matched = metadata.get("original_task") == seed.get("test_prompt")
        # A failure may concern an authored criterion outside this fixture's oracle.
        # A satisfied fixture cannot independently establish that the entire test passed.
        classification = (
            ("correct" if truth else "false_pass")
            if verdict == "passed"
            else (
                "false_fail"
                if truth and criterion_matched
                else "inconclusive"
                if truth
                else "correct"
            )
            if verdict == "failed"
            else "inconclusive"
        )
        result.update(
            phase="post",
            fixture="androidworld",
            task_name=seed["task_name"],
            seeded_fault=seed["seeded_fault"],
            oracle_applicable=True,
            checker_verdict=verdict,
            classification=classification,
            target_state_changed=result["state_sha256"] != seed["state_sha256"],
            ground_truth_source="Exact listed fields; unchanged prior rows; AndroidWorld oracle recorded separately",
            timestamp=time.time(),
        )
        with path.open("a") as stream:
            stream.write(json.dumps(result, sort_keys=True) + "\n")
        return result
    raise HTTPException(status_code=409, detail=f"Unsupported fixture: {seed.get('fixture')!r}.")
