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

"""The research pipeline reads the agent's submitted verdict from the bench record."""

import json

import pytest

from apps.harness_server.services.research_trials import declared_verdict


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [("DEFECT", "FAIL"), ("NO_DEFECT", "PASS"), ("INCONCLUSIVE", "INCONCLUSIVE")],
)
def test_bench_verdict_maps_to_research_scale(tmp_path, answer, verdict):
    (tmp_path / "bench").mkdir()
    (tmp_path / "bench" / "verdict.json").write_text(json.dumps({"verdict": answer}))
    assert declared_verdict(tmp_path)["verdict"] == verdict


def test_older_runs_still_read_notes(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "result.md").write_text("Checked the list.\nVERDICT: FAIL\n")
    assert declared_verdict(tmp_path)["verdict"] == "FAIL"


def test_no_answer_is_no_verdict(tmp_path):
    assert declared_verdict(tmp_path)["verdict"] is None
