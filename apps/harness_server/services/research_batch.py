"""Server-side experiment batches.

A batch seeds a state fixture, queues the run, attaches metadata and the
seed, waits for the run to end, then records the post-run oracle read — once
per plan, strictly in sequence because seeding and execution share one device.

This used to run inside the browser tab that submitted it, so a reload or a
closed tab silently dropped the post-run oracle read and every remaining run.
Here it runs on the server and persists its progress, and the UI only polls.
Each step goes through the same HTTP endpoints the UI called (in-process, via
ASGI), so validation and recorded artifacts are unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
from pathlib import Path
import time
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from artemis.config import TRACES_PATH

FixtureKind = Literal["none", "pilot", "qa"]
ACTIVE_RUN_STATUSES = ("running", "queued", "pending")
STATUS_POLL_SECONDS = 2.0
STATUS_UNSEEN_LIMIT = 150  # ~5 minutes of unreadable run status.


class BatchPlan(BaseModel):
    condition_id: str = Field(min_length=1, max_length=80)
    switches: dict[str, bool | str] = Field(default_factory=dict)
    framing: Literal["plain", "observe_only", "release_blocked"] = "plain"
    length: Literal["short", "long"] = "short"
    task: str = Field(default="", max_length=20000)
    fault_seed: bool = False
    repeat: int = Field(default=1, ge=1, le=12)
    pilot_trial_id: str | None = None
    qa_pair_id: str | None = Field(default=None, pattern=r"^qa-[0-9a-f]{20}$")
    variant: Literal["control", "fault"] | None = None


class BatchRequest(BaseModel):
    experiment_name: str = Field(min_length=1, max_length=80)
    device_serial: str = Field(min_length=1, max_length=120)
    fixture_kind: FixtureKind = "none"
    test_class: str = "functional"
    plans: list[BatchPlan] = Field(min_length=1, max_length=600)


class BatchStepError(Exception):
    def __init__(self, detail: str, status: int | None = None):
        super().__init__(detail)
        self.status = status


def framed_task(task: str, framing: str) -> str:
    if framing == "observe_only":
        return f"Observe only. Do not change app state. Test:\n{task}"
    if framing == "release_blocked":
        return (
            "Release-blocked verification: do not report success unless the completion "
            f"condition below is directly verified from observed evidence.\n{task}"
        )
    return task


def _retryable(error: BatchStepError) -> bool:
    message = str(error).lower()
    return error.status in (404, 409) or "trace folder" in message or "still in use" in message


async def retry_until_saved(
    fn: Callable[[], Awaitable[Any]], attempts: int = 60, delay: float = 0.5
) -> Any:
    """Retries while the trace folder is not created yet or the device is still held."""
    last: BatchStepError | None = None
    for _ in range(attempts):
        try:
            return await fn()
        except BatchStepError as error:
            if not _retryable(error):
                raise
            last = error
            await asyncio.sleep(delay)
    raise last or BatchStepError("Could not attach run metadata.")


def _batches_dir() -> Path:
    directory = Path(TRACES_PATH).resolve() / "research_batches"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class BatchRunner:
    """Owns batch state on disk and the asyncio task executing each batch."""

    _tasks: dict[str, asyncio.Task] = {}
    _stop_requested: set[str] = set()

    # --- persistence ---------------------------------------------------------------

    @classmethod
    def _path(cls, batch_id: str) -> Path:
        return _batches_dir() / f"{batch_id}.json"

    @classmethod
    def _write(cls, state: dict[str, Any]) -> None:
        state["updated_at"] = time.time()
        path = cls._path(state["batch_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def report_path(cls, batch_id: str) -> Path:
        return _batches_dir() / f"{batch_id}.report.json"

    @classmethod
    def read(cls, batch_id: str) -> dict[str, Any] | None:
        path = cls._path(batch_id)
        if not path.is_file():
            return None
        state = json.loads(path.read_text(encoding="utf-8"))
        task = cls._tasks.get(batch_id)
        if state.get("status") == "running" and (task is None or task.done()):
            # The process that owned this batch is gone (server restart).
            state.update(
                status="interrupted", message="The server restarted while this batch was running."
            )
            cls._write(state)
        return state

    @classmethod
    def list(cls, limit: int = 20) -> list[dict[str, Any]]:
        paths = sorted(_batches_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [s for s in (cls.read(p.stem) for p in paths[:limit]) if s]

    # --- lifecycle -----------------------------------------------------------------

    @classmethod
    def active_for_device(cls, device_serial: str) -> dict[str, Any] | None:
        for batch_id, task in cls._tasks.items():
            if not task.done():
                state = cls.read(batch_id)
                if state and state.get("device_serial") == device_serial:
                    return state
        return None

    @classmethod
    def start(cls, app: Any, request: BatchRequest) -> dict[str, Any]:
        batch_id = str(uuid4())
        state = {
            "batch_id": batch_id,
            "status": "running",
            "experiment_name": request.experiment_name,
            "device_serial": request.device_serial,
            "fixture_kind": request.fixture_kind,
            "total": len(request.plans),
            "index": 0,
            "completed": 0,
            "message": "Starting batch",
            "error": None,
            "current_session_id": None,
            "session_ids": [],
            "created_at": time.time(),
        }
        cls._write(state)
        cls._tasks[batch_id] = asyncio.create_task(cls._run(app, request, state))
        return state

    @classmethod
    async def stop(cls, app: Any, batch_id: str) -> dict[str, Any] | None:
        state = cls.read(batch_id)
        if not state or state.get("status") != "running":
            return state
        cls._stop_requested.add(batch_id)
        state["message"] = "Stopping after the current run is recorded"
        cls._write(state)
        if state.get("current_session_id"):
            async with cls._client(app) as client:
                try:
                    await cls._post(
                        client, "/api/stop", {"session_id": state["current_session_id"]}
                    )
                except BatchStepError:
                    pass  # The run may already have ended; the loop still stops.
        return state

    # --- execution -----------------------------------------------------------------

    @staticmethod
    def _client(app: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost", timeout=None
        )

    @staticmethod
    async def _request(client: httpx.AsyncClient, method: str, path: str, body: Any = None) -> Any:
        response = await client.request(method, path, json=body)
        if response.status_code >= 400:
            detail = f"Request failed ({response.status_code})"
            try:
                payload = response.json()
                if isinstance(payload.get("detail"), str):
                    detail = payload["detail"]
            except ValueError:
                pass
            raise BatchStepError(detail, response.status_code)
        return response.json()

    @classmethod
    async def _post(cls, client: httpx.AsyncClient, path: str, body: Any) -> Any:
        return await cls._request(client, "POST", path, body)

    @classmethod
    async def _wait_for_end(cls, client: httpx.AsyncClient, session_id: str) -> None:
        # Device interventions are serialized: never seed the next run while this one acts.
        unseen = 0
        while True:
            try:
                status = await cls._request(client, "GET", f"/api/sessions/{session_id}")
                unseen = 0
                if str(status.get("status") or "").lower() not in ACTIVE_RUN_STATUSES:
                    return
            except BatchStepError:
                unseen += 1
                if unseen > STATUS_UNSEEN_LIMIT:
                    raise BatchStepError(
                        "Run status was not available after five minutes."
                    ) from None
            await asyncio.sleep(STATUS_POLL_SECONDS)

    @classmethod
    async def _run(cls, app: Any, request: BatchRequest, state: dict[str, Any]) -> None:
        batch_id = state["batch_id"]
        total = len(request.plans)
        fixture = request.fixture_kind
        pilot = fixture == "pilot"
        try:
            async with cls._client(app) as client:
                manifest = (
                    await cls._request(client, "GET", "/api/research/pilot") if pilot else None
                )
                for index, plan in enumerate(request.plans, start=1):
                    if batch_id in cls._stop_requested:
                        state.update(
                            status="stopped",
                            message=f"Stopped after {state['completed']} of {total} runs",
                        )
                        return
                    state.update(
                        index=index,
                        current_session_id=None,
                        message=f"Preparing {request.experiment_name}/{plan.condition_id}",
                    )
                    cls._write(state)
                    try:
                        await cls._run_plan(client, request, plan, state, manifest)
                    except BatchStepError as error:
                        state.update(
                            status="failed",
                            error=f"Stopped at run {index}/{total}: {error}",
                            message=f"Batch stopped: {error}",
                        )
                        return
                    state["completed"] += 1
                    state["message"] = f"Recorded {state['completed']} of {total}"
                    cls._write(state)
                state.update(status="completed", message=f"Recorded {total} of {total}")
        except Exception as error:  # Never leave a batch marked running.
            state.update(status="failed", error=str(error), message=f"Batch stopped: {error}")
        finally:
            cls._stop_requested.discard(batch_id)
            cls._write(state)
            try:
                await cls._write_report(app, state)
            except Exception as error:  # A report failure never changes the batch outcome.
                state["report_error"] = str(error)
                cls._write(state)

    @classmethod
    async def _run_plan(
        cls,
        client: httpx.AsyncClient,
        request: BatchRequest,
        plan: BatchPlan,
        state: dict[str, Any],
        manifest: dict[str, Any] | None,
    ) -> None:
        fixture = request.fixture_kind
        pilot = fixture == "pilot"
        device = request.device_serial
        instance = None
        if pilot:
            trial = next(
                (t for t in manifest["trials"] if t["trial_id"] == plan.pilot_trial_id), None
            )
            instance = trial and next(
                (i for i in manifest["instances"] if i["pair_id"] == trial["pair_id"]), None
            )
            if not instance:
                raise BatchStepError("Pilot trial has no matching frozen instance.")

        intervention = None
        if pilot:
            body = {
                "task_name": instance["task_name"],
                "device_serial": device,
                "seed": instance["seed"],
                "fault_seed": plan.fault_seed,
                "operation": instance["operation"],
                "pilot_trial_id": plan.pilot_trial_id,
            }
            intervention = await retry_until_saved(
                lambda: cls._post(client, "/api/research/androidworld/seed", body)
            )
        elif fixture == "qa":
            if not plan.qa_pair_id or not plan.variant:
                raise BatchStepError("A QA plan needs a pair and a variant.")
            body = {"pair_id": plan.qa_pair_id, "variant": plan.variant, "device_serial": device}
            intervention = await retry_until_saved(
                lambda: cls._post(client, "/api/research/qa/seed", body)
            )

        frozen = fixture in ("pilot", "qa")
        authored_task = "" if frozen else plan.task.strip()
        current_task = authored_task
        if frozen:
            # The frozen criterion is submitted unchanged: same text for control and fault.
            if not (intervention or {}).get("test_prompt"):
                raise BatchStepError("Fixture returned no test prompt.")
            current_task = intervention["test_prompt"]
        elif (intervention or {}).get("test_prompt"):
            current_task += "\n\n" + intervention["test_prompt"]
        if not current_task.strip():
            raise BatchStepError("The test text is empty.")

        run = await cls._post(
            client,
            "/api/run",
            {
                "goal": current_task if frozen else framed_task(current_task, plan.framing),
                "device_serial": device,
                "experiment_switches": plan.switches,
            },
        )
        session_id = ((run.get("tasks") or [{}])[0] or {}).get("session_id")
        if not session_id:
            raise BatchStepError("Run was not queued. Check device readiness.")
        state["current_session_id"] = session_id
        state["session_ids"].append(session_id)
        variant = plan.variant or (
            ("fault" if plan.fault_seed else "pass") if fixture != "none" else "trace"
        )
        state["message"] = f"Running {plan.condition_id} · {variant} · {plan.length}"
        cls._write(state)

        await retry_until_saved(
            lambda: cls._post(
                client,
                f"/api/sessions/{session_id}/experiment",
                {
                    "condition": f"{request.experiment_name}/{plan.condition_id}",
                    "framing": plan.framing,
                    "test_length": plan.length,
                    "original_task": current_task,
                    "authored_task": authored_task,
                    "repeat_index": plan.repeat,
                    "batch_id": state["batch_id"],
                    "test_class": "functional" if frozen else request.test_class,
                    "switches": plan.switches,
                },
            )
        )
        if intervention:
            await retry_until_saved(
                lambda: cls._post(
                    client,
                    "/api/ground-truth/attach",
                    {
                        "intervention_id": intervention["intervention_id"],
                        "session_id": session_id,
                    },
                )
            )

        await cls._wait_for_end(client, session_id)
        if intervention:
            try:
                await retry_until_saved(
                    lambda: cls._post(
                        client, f"/api/sessions/{session_id}/ground-truth/finalize", {}
                    )
                )
            except BatchStepError:
                pass  # An unreadable post-state stays unknown in the record.

    @classmethod
    async def _write_report(cls, app: Any, state: dict[str, Any]) -> None:
        """One self-contained record of the batch: every run, its truth, verdict and provenance.

        Each row is recomputed from the saved run folder, so the same rows come back
        from ``GET /api/sessions/{id}/trial`` at any later time (offline replay).
        """
        rows = []
        async with cls._client(app) as client:
            for session_id in state.get("session_ids", []):
                try:
                    trial = await cls._request(client, "GET", f"/api/sessions/{session_id}/trial")
                except BatchStepError as error:
                    rows.append({"session_id": session_id, "error": str(error)})
                    continue
                agent, checker = trial.get("agent") or {}, trial.get("checker") or {}
                truth = (
                    [
                        json.loads(line)
                        for line in (Path(TRACES_PATH) / session_id / "ground_truth.jsonl")
                        .read_text(encoding="utf-8")
                        .splitlines()
                        if line.strip()
                    ]
                    if (Path(TRACES_PATH) / session_id / "ground_truth.jsonl").is_file()
                    else []
                )
                pre = next((r for r in truth if r.get("phase") == "pre"), {})
                post = next((r for r in reversed(truth) if r.get("phase") == "post"), {})
                grounding = agent.get("grounding") or {}
                rows.append(
                    {
                        "session_id": session_id,
                        "trace_folder": str(Path(TRACES_PATH) / session_id),
                        "pair_id": agent.get("pair_id"),
                        "variant": agent.get("variant"),
                        "bucket_id": agent.get("family"),
                        "expected_verdict": agent.get("expected_verdict"),
                        "agent_verdict": agent.get("agent_verdict"),
                        "agent_verdict_source": agent.get("agent_verdict_source"),
                        "outcome": agent.get("outcome"),
                        "admission": agent.get("admission"),
                        "exclusion_reason": agent.get("error"),
                        "checker_verdict": checker.get("checker_verdict"),
                        "checker_outcome": checker.get("outcome"),
                        "checker_exclusion_reason": checker.get("error"),
                        "setup_confirmed": agent.get("setup_confirmed"),
                        "post_oracle_correct": agent.get("post_oracle_correct"),
                        "protected_state_changed": agent.get("protected_state_changed"),
                        "state_sha256_before": pre.get("state_sha256"),
                        "state_sha256_after": post.get("state_sha256"),
                        "criterion_sha256": pre.get("criterion_sha256"),
                        "reference_artifact_sha256": pre.get("reference_artifact_sha256"),
                        "mutation_version": pre.get("mutation_version"),
                        "oracle_version": pre.get("oracle_version"),
                        "read_tier": pre.get("planned_read_tier"),
                        "model": agent.get("model"),
                        "condition": agent.get("condition"),
                        "harness_commit": agent.get("harness_commit"),
                        "harness_dirty": agent.get("harness_dirty"),
                        "pass_backed_by_screen": grounding.get("grounded_pass"),
                        "fields_seen": f"{grounding.get('observed_fields')}/{grounding.get('checkable_fields')}"
                        if grounding
                        else None,
                    }
                )
        outcomes: dict[str, int] = {}
        for row in rows:
            key = row.get("outcome") or "unscored"
            outcomes[key] = outcomes.get(key, 0) + 1
        dataset = None
        if state.get("fixture_kind") == "qa":
            from apps.harness_server.services import qa_catalog

            dataset = {
                "suite_id": qa_catalog.catalog()["suite_id"],
                "files_sha256": qa_catalog.catalog()["files"],
            }
        report = {
            "schema_version": "artemis-batch-report/v1",
            "batch_id": state["batch_id"],
            "status": state.get("status"),
            "experiment_name": state.get("experiment_name"),
            "device_serial": state.get("device_serial"),
            "fixture_kind": state.get("fixture_kind"),
            "created_at": state.get("created_at"),
            "written_at": time.time(),
            "dataset": dataset,
            "outcome_counts": outcomes,
            "runs": rows,
            "replay": "Each row is recomputed from its trace folder by GET /api/sessions/{session_id}/trial; no device or model call.",
        }
        path = cls.report_path(state["batch_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(path)
