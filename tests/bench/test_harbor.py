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

"""Harbor export: task layout, hidden labels, and scoring joins."""

import json
import re
import tomllib

from artemis.bench.harbor import export_harbor
from artemis.bench.scoring import score_results

CASE = {
    "case_id": "tasks-readonly-delete",
    "app": "tasks",
    "app_package": "org.tasks",
    "prompts": {"directed": "Check that a read-only shared task cannot be deleted."},
    "signature": {"faulty_state": [{"match": {"text": "Quarterly report"}, "present": False}]},
    "builds": {"faulty": {"setup": [["echo", "faulty"]]}, "correct": {"setup": [["echo", "ok"]]}},
    "step_budget": {"directed": 40},
}


def export(tmp_path):
    return export_harbor(
        [CASE],
        tmp_path,
        device_host_url="http://10.0.0.5:8765",
        verifier_token="secret-token",
        repeats=2,
        extra_allowed_hosts=["api.anthropic.com"],
    )


def test_one_task_per_case_build_and_repeat(tmp_path):
    assert export(tmp_path)["tasks"] == 4
    manifest = json.loads((tmp_path / "manifest.json").read_text())["tasks"]
    assert sorted((t["build"], t["repeat"]) for t in manifest) == [
        ("correct", 1),
        ("correct", 2),
        ("faulty", 1),
        ("faulty", 2),
    ]


def test_agent_visible_files_do_not_reveal_the_build(tmp_path):
    export(tmp_path)
    for task_dir in (tmp_path / "tasks").iterdir():
        visible = (task_dir / "instruction.md").read_text() + (task_dir / "task.toml").read_text()
        assert not re.search(r"\b(faulty|correct)\b", visible)
        assert "Quarterly report" not in visible


def test_task_toml_declares_the_device_mcp_server(tmp_path):
    export(tmp_path)
    task_dir = next((tmp_path / "tasks").iterdir())
    config = tomllib.loads((task_dir / "task.toml").read_text())
    (server,) = config["environment"]["mcp_servers"]
    assert server == {
        "name": "android",
        "transport": "streamable-http",
        "url": f"http://10.0.0.5:8765/t/{task_dir.name}/mcp",
    }
    assert config["environment"]["network_mode"] == "allowlist"
    assert config["environment"]["allowed_hosts"] == ["10.0.0.5", "api.anthropic.com"]
    assert config["verifier"]["env"]["BENCH_RECORD_URL"].endswith(f"/t/{task_dir.name}/record")
    assert (task_dir / "tests" / "grade.py").is_file()
    assert "--build" in (task_dir / "tests" / "test.sh").read_text()


def test_slots_keep_setup_host_side(tmp_path):
    export(tmp_path)
    slots = json.loads((tmp_path / "slots.json").read_text())["slots"]
    assert {tuple(s["setup"][0]) for s in slots} == {("echo", "faulty"), ("echo", "ok")}
    assert all(s["step_budget"] == 40 for s in slots)


def test_score_joins_rewards_and_counts_missing_trials(tmp_path):
    export(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())["tasks"]
    results = tmp_path / "job"
    for task in manifest:
        if task["repeat"] == 2 and task["build"] == "correct":
            continue  # trial never ran
        label = "catch" if task["build"] == "faulty" else "correct_clear"
        reward = results / f"{task['slot_id']}__trial" / "verifier" / "reward.json"
        reward.parent.mkdir(parents=True)
        reward.write_text(json.dumps({"reward": 1.0, "label": label}))
    report = score_results(tmp_path / "manifest.json", results)
    assert report["score"] == 0.5
    assert report["missing_trials"] == 1
