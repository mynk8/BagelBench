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


def test_bench_mode_has_no_helper_models_or_completion_tool(tmp_path):
    runner = bench_runner(tmp_path)
    names = {t.name for t in runner._get_tools()}
    assert not names & {"ask_explorer", "report_task_status", "video_analyzer", "search_history"}
    assert runner.summarizer is None
    assert runner.terminal_tool == "submit_verdict"


def test_bench_prompt_is_the_tester_prompt(tmp_path):
    runner = bench_runner(tmp_path)
    prompt = runner._render_system_prompt(runner._get_tools())
    assert "QA tester" in prompt and "read-only task" in prompt
    assert "submit_verdict" in prompt and "report_task_status" not in prompt


def test_extension_declarations_cover_every_condition_tool():
    assert {e.name for e in BENCH_EXTENSIONS} == set(CONDITION_TOOLS) | {"submit_verdict"}
