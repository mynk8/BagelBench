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

"""The bench device server over a mock device: tool surface, recording, answer rules."""

import asyncio
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from bagel.transports.mcp import benchmark as bench_server
from bagel.benchmark.recording import RunRecorder, load_steps, load_verdict
from bagel.benchmark.slots import Slot
from bagel.transports.http.benchmark import BenchHost
from bagel.device.actuators.mock import MockActuator


class FakeShell:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def __call__(self, argv: list[str]) -> str:
        self.calls.append(argv)
        if argv[:2] == ["dumpsys", "activity"]:
            return "  mResumedActivity: ActivityRecord{1 u0 org.tasks/.MainActivity t5}\n"
        if argv[:3] == ["pm", "list", "packages"]:
            return "package:org.tasks\npackage:com.android.settings\n"
        return ""


@pytest.fixture
def setup(tmp_path, monkeypatch):
    async def fake_observe(ctx, controller, settle_ms=400):
        from bagel.device.results import ObserveResult

        return (
            ObserveResult(
                ok=True,
                width=1080,
                height=2400,
                elements_text="[0] Text: 'Quarterly report'",
                elements=[{"index": 0, "text": "Quarterly report", "center": [540, 300]}],
            ),
            b"\xff\xd8jpeg",
        )

    monkeypatch.setattr(bench_server, "observe_impl", fake_observe)
    shell = FakeShell()
    recorder = RunRecorder(tmp_path / "run")
    return recorder, shell


def call(server, tool, args=None):
    async def go():
        async with create_connected_server_and_client_session(server) as session:
            if isinstance(tool, list):
                return [await session.call_tool(name, a or {}) for name, a in tool]
            return await session.call_tool(tool, args or {})

    return asyncio.run(go())


def tool_names(server):
    async def go():
        async with create_connected_server_and_client_session(server) as session:
            return {t.name for t in (await session.list_tools()).tools}

    return asyncio.run(go())


def text(result):
    return result.content[0].text


def test_tool_surface_is_ui_only(setup):
    recorder, shell = setup
    names = tool_names(bench_server.build_bench_server(MockActuator(), recorder, shell))
    assert names == bench_server.BENCH_ACTIONS | set(bench_server.CONDITION_TOOLS) | {
        "observe_screen",
        "submit_verdict",
    }
    assert "open_link" not in names
    assert not {n for n in names if "adb" in n or "shell" in n}


def test_every_call_is_a_recorded_numbered_step(setup):
    recorder, shell = setup
    server = bench_server.build_bench_server(MockActuator(), recorder, shell)
    first, second = call(server, [("click", {"target": [500, 300]}), ("observe_screen", {})])
    assert text(first).startswith("[step 1] ")
    assert text(second).startswith("[step 2] ")
    steps = load_steps(recorder.run_dir)
    assert [s["tool"] for s in steps] == ["click", "observe_screen"]
    assert steps[0]["screen"]["activity"] == "org.tasks/.MainActivity"
    assert steps[0]["screen"]["elements"][0]["text"] == "Quarterly report"
    assert (recorder.run_dir / steps[0]["screen"]["screenshot"]).is_file()


def test_verdict_is_final_and_must_flag_a_taken_step(setup):
    recorder, shell = setup
    server = bench_server.build_bench_server(MockActuator(), recorder, shell)
    results = call(
        server,
        [
            ("observe_screen", {}),
            ("submit_verdict", {"verdict": "DEFECT", "flag_step": 5}),
            ("submit_verdict", {"verdict": "DEFECT", "flag_step": 1}),
            ("submit_verdict", {"verdict": "NO_DEFECT"}),
            ("click", {"target": [1, 1]}),
        ],
    )
    assert results[1].isError
    assert not results[2].isError
    assert results[3].isError
    assert results[4].structuredContent["ok"] is False and "over" in text(results[4])
    assert load_verdict(recorder.run_dir)["flag_step"] == 1


def test_action_budget_spares_observation_and_the_verdict(setup):
    recorder, shell = setup
    server = bench_server.build_bench_server(MockActuator(), recorder, shell, step_budget=1)
    results = call(
        server,
        [
            ("click", {"target": [500, 300]}),
            ("click", {"target": [500, 300]}),
            ("observe_screen", {}),
            ("submit_verdict", {"verdict": "NO_DEFECT"}),
        ],
    )
    assert results[0].structuredContent["ok"] is True
    assert results[1].structuredContent["ok"] is False and "budget" in text(results[1])
    assert not results[2].isError
    assert not results[3].isError


def test_conditions_run_fixed_commands_scoped_to_the_app(setup):
    recorder, shell = setup
    server = bench_server.build_bench_server(
        MockActuator(), recorder, shell, app_package="org.tasks"
    )
    results = call(
        server,
        [
            ("kill_app_process", {}),
            ("set_permission", {"permission": "android.permission.CAMERA", "granted": False}),
            (
                "set_permission",
                {"permission": "android.permission.CAMERA; reboot", "granted": False},
            ),
            ("rotate", {"orientation": "sideways"}),
        ],
    )
    issued = [argv for argv in shell.calls if argv[:2] != ["dumpsys", "activity"]]
    assert ["am", "kill", "org.tasks"] in issued
    assert ["pm", "revoke", "org.tasks", "android.permission.CAMERA"] in issued
    assert results[2].isError and results[3].isError
    assert not any("reboot" in " ".join(argv) for argv in issued)


def test_first_call_runs_slot_setup(setup):
    recorder, shell = setup
    started = []

    async def on_first_call():
        started.append(True)

    server = bench_server.build_bench_server(
        MockActuator(), recorder, shell, on_first_call=on_first_call
    )
    call(server, [("observe_screen", {}), ("observe_screen", {})])
    assert started == [True]


def test_host_serves_slot_endpoints_and_guards_the_record(setup):
    from starlette.testclient import TestClient

    recorder, shell = setup
    slots = {"s1": Slot(slot_id="s1", case_id="c1", build="faulty")}
    host = BenchHost(
        slots, recorder.run_dir.parent, MockActuator(), shell, "tok", public_hosts=["testserver"]
    )
    with TestClient(host.app()) as client:
        assert client.get("/t/s1/record").status_code == 401
        assert (
            client.get("/t/nope/record", headers={"Authorization": "Bearer tok"}).status_code == 404
        )
        record = client.get("/t/s1/record", headers={"Authorization": "Bearer tok"})
        assert record.status_code == 200 and record.json() == {"steps": [], "verdict": None}
        init = client.post(
            "/t/s1/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init.status_code == 200
        assert "android" in init.text


def test_host_grades_its_record_only_for_the_verifier(setup):
    from starlette.testclient import TestClient

    recorder, shell = setup
    signature = {
        "screen": {"activity": "org.tasks/.MainActivity"},
        "faulty_state": [{"match": {"text": "Quarterly report"}, "present": True}],
    }
    slot = Slot(slot_id="s1", case_id="c1", build="faulty", signature=signature)
    host = BenchHost(
        {"s1": slot},
        recorder.run_dir.parent,
        MockActuator(),
        shell,
        "tok",
        public_hosts=["testserver"],
    )
    server = host.server_for(slot)
    results = call(
        server,
        [
            ("observe_screen", {}),
            ("submit_verdict", {"verdict": "DEFECT", "flag_step": 1}),
        ],
    )
    assert not results[-1].isError
    with TestClient(host.app()) as client:
        assert client.get("/t/s1/reward").status_code == 401
        response = client.get("/t/s1/reward", headers={"Authorization": "Bearer tok"})
        assert response.status_code == 200
        assert response.json() == {"reward": 1.0, "label": "catch", "build": "faulty"}
        assert (
            client.get("/t/nope/reward", headers={"Authorization": "Bearer tok"}).status_code == 404
        )


@pytest.mark.parametrize("spawn_error", [False, True])
def test_failed_private_setup_does_not_reveal_its_commands(setup, monkeypatch, spawn_error):
    recorder, shell = setup

    class FailedSetup:
        async def wait(self):
            return 1

    async def fail(*args, **kwargs):
        if spawn_error:
            raise FileNotFoundError("private-fault-install")
        return FailedSetup()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail)
    slot = Slot(slot_id="s1", case_id="c1", build="faulty", setup=[["private-fault-install"]])
    host = BenchHost({"s1": slot}, recorder.run_dir.parent, MockActuator(), shell, "tok")
    with pytest.raises(RuntimeError, match="Android setup failed") as error:
        asyncio.run(host._start(slot))
    assert "private-fault-install" not in str(error.value)


def test_manage_app_needs_an_exact_installed_package(setup, monkeypatch):
    recorder, shell = setup
    server = bench_server.build_bench_server(MockActuator(), recorder, shell)
    (result,) = call(server, [("manage_app", {"action": "launch", "app_name": "Tasks"})])
    assert result.structuredContent["ok"] is False
    assert "exact package" in text(result)
    assert not load_steps(recorder.run_dir)[0]["ok"]
