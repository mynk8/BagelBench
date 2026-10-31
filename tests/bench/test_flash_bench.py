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

"""Flash in bench mode binds exactly the bench tool surface and one model."""

from artemis.agents.flash.runner import FlashRunner
from artemis.bench.flash import BENCH_EXTENSIONS, BenchActuator, BenchRun
from artemis.bench.server import BENCH_ACTIONS, CONDITION_TOOLS
from artemis.mcp.actuators.mock import MockActuator


def bench_runner(tmp_path) -> FlashRunner:
    actuator = MockActuator()
    ctx = actuator.ctx
    ctx.actuator = BenchActuator(actuator)
    return FlashRunner(
        ctx, goal="Check that a read-only task cannot be deleted.", bench=BenchRun(tmp_path)
    )


def test_bench_tools_match_the_bench_server(tmp_path):
    names = {t.name for t in bench_runner(tmp_path)._get_tools()}
    assert names == BENCH_ACTIONS | set(CONDITION_TOOLS) | {"submit_verdict"}


def test_flash_has_no_helper_models_or_completion_tool(tmp_path):
    from artemis.agents.flash import runner as flash_runner

    runner = bench_runner(tmp_path)
    names = {t.name for t in runner._get_tools()}
    assert not names & {"ask_explorer", "report_task_status", "video_analyzer", "search_history"}
    assert not hasattr(runner, "summarizer")
    assert flash_runner.TERMINAL_TOOL == "submit_verdict"


def test_flash_observes_through_the_recorded_session(tmp_path, monkeypatch):
    """Flash's own observations are recorded steps, so its first screen is citable."""
    import asyncio

    from artemis.bench import server as bench_server
    from artemis.bench.recorder import RunRecorder
    from artemis.mcp.action_session import ActionSession
    from artemis.mcp.action_types import ObserveResult

    async def fake_observe(ctx, controller, settle_ms=400):
        return ObserveResult(ok=True, elements_text="[0] Text: 'Inbox'", elements=[]), b"jpg"

    async def shell(argv):
        return ""

    monkeypatch.setattr(bench_server, "observe_impl", fake_observe)
    runner = bench_runner(tmp_path)
    server = bench_server.build_bench_server(MockActuator(), RunRecorder(tmp_path), shell)

    async def go():
        session = ActionSession(server)
        await session.start()
        runner.ctx.action_session = session
        try:
            return await runner._observe(settle_ms=0)
        finally:
            await session.aclose()

    obs, image = asyncio.run(go())
    assert obs.elements_text == "[0] Text: 'Inbox'" and image == b"jpg"
    assert runner._current_step() == 1


def test_bench_prompt_is_the_tester_prompt(tmp_path):
    runner = bench_runner(tmp_path)
    prompt = runner._render_system_prompt(runner._get_tools())
    assert "QA tester" in prompt and "read-only task" in prompt
    assert "submit_verdict" in prompt and "report_task_status" not in prompt


def test_extension_declarations_cover_every_condition_tool():
    assert {e.name for e in BENCH_EXTENSIONS} == set(CONDITION_TOOLS) | {"submit_verdict"}


def test_flash_loop_runs_to_a_recorded_verdict(tmp_path, monkeypatch):
    """The whole bench-only loop on a mock device with the fake model."""
    import asyncio

    from artemis.bench import server as bench_server
    from artemis.bench.recorder import RunRecorder, load_steps, load_verdict
    from artemis.llm.fake_model import FakeChatModel
    from artemis.mcp.action_session import ActionSession
    from artemis.mcp.action_types import ObserveResult
    from artemis.state import State

    async def fake_observe(ctx, controller, settle_ms=400):
        return ObserveResult(ok=True, elements_text="[0] Text: 'Inbox'", elements=[]), b"jpg"

    async def shell(argv):
        return ""

    monkeypatch.setattr(bench_server, "observe_impl", fake_observe)
    runner = bench_runner(tmp_path)
    monkeypatch.setattr(runner, "_init_llm", lambda: FakeChatModel())
    server = bench_server.build_bench_server(MockActuator(), RunRecorder(tmp_path), shell)

    async def go():
        session = ActionSession(server)
        await session.start()
        runner.ctx.action_session = session
        try:
            return await runner.run(State(initial_goal="Check the inbox."))
        finally:
            await session.aclose()

    result = asyncio.run(go())
    assert result["status"] == "completed"
    assert load_verdict(tmp_path)["verdict"] == "NO_DEFECT"
    assert [s["tool"] for s in load_steps(tmp_path)] == ["observe_screen"]
