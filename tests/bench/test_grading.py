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

"""Model-free grading rules (docs/benchmark-task-recipe.md §0.6)."""

import pytest

from artemis.bench import grading as g

SIGNATURE = {
    "screen": {"activity": "org.tasks/.MainActivity", "anchors": [{"text": "Shared list"}]},
    "faulty_state": [{"match": {"text": "Quarterly report"}, "present": False}],
    "known_issues": [
        {
            "id": "KI-1",
            "screen": {"activity": "org.tasks/.SettingsActivity"},
            "faulty_state": [{"match": {"text_contains": "Translat"}, "present": True}],
        }
    ],
}

FAULT_SCREEN = {"activity": "org.tasks/.MainActivity", "elements": [{"text": "Shared list"}]}
OK_SCREEN = {
    "activity": "org.tasks/.MainActivity",
    "elements": [{"text": "Shared list"}, {"text": "Quarterly report"}],
}
KNOWN_SCREEN = {"activity": "org.tasks/.SettingsActivity", "elements": [{"text": "Translations"}]}


def steps(*screens):
    return [{"step": i, "screen": screen} for i, screen in enumerate(screens, start=1)]


def verdict(answer, flag_step=None):
    return {"verdict": answer, "flag_step": flag_step}


@pytest.mark.parametrize(
    ("build", "screens", "answer", "label"),
    [
        (g.FAULTY, (OK_SCREEN, FAULT_SCREEN), verdict("DEFECT", 2), g.CATCH),
        (g.FAULTY, (OK_SCREEN, FAULT_SCREEN), verdict("DEFECT", 1), g.WRONG_CATCH),
        (g.FAULTY, (FAULT_SCREEN,), verdict("NO_DEFECT"), g.MISS),
        (g.CORRECT, (OK_SCREEN,), verdict("NO_DEFECT"), g.CORRECT_CLEAR),
        (g.CORRECT, (OK_SCREEN,), verdict("DEFECT", 1), g.FALSE_ALARM),
        (g.FAULTY, (FAULT_SCREEN,), verdict("INCONCLUSIVE"), g.ABSTAIN),
        (g.CORRECT, (OK_SCREEN,), None, g.NO_ANSWER),
        (g.FAULTY, (FAULT_SCREEN,), verdict("DEFECT", 7), g.NO_ANSWER),
        (g.CORRECT, (KNOWN_SCREEN,), verdict("DEFECT", 1), g.KNOWN_ISSUE),
    ],
)
def test_label_run(build, screens, answer, label):
    assert g.label_run(build, steps(*screens), answer, SIGNATURE) == label


def test_activity_mismatch_is_not_a_catch():
    other = {**FAULT_SCREEN, "activity": "org.tasks/.EditActivity"}
    assert not g.screen_matches(other, SIGNATURE)


def test_only_right_labels_earn_reward():
    assert {
        label for label in vars(g).values() if isinstance(label, str) and g.reward_for(label)
    } == g.RIGHT


def _runs(case_id, app, pairs):
    runs = []
    for repeat, (faulty, correct) in enumerate(pairs, start=1):
        runs.append(
            {"case_id": case_id, "app": app, "repeat": repeat, "build": g.FAULTY, "label": faulty}
        )
        runs.append(
            {"case_id": case_id, "app": app, "repeat": repeat, "build": g.CORRECT, "label": correct}
        )
    return runs


def test_case_passes_only_when_both_builds_are_right_in_the_same_repeat():
    runs = _runs(
        "c1",
        "tasks",
        [
            (g.CATCH, g.CORRECT_CLEAR),
            (g.CATCH, g.FALSE_ALARM),
            (g.MISS, g.CORRECT_CLEAR),
        ],
    )
    assert g.case_scores(runs) == {"c1": pytest.approx(1 / 3)}


def test_always_defect_and_always_fine_both_score_zero():
    always_defect = _runs("c1", "tasks", [(g.CATCH, g.FALSE_ALARM)] * 3)
    always_fine = _runs("c2", "tasks", [(g.MISS, g.CORRECT_CLEAR)] * 3)
    assert g.benchmark_score(always_defect)["score"] == 0
    assert g.benchmark_score(always_fine)["score"] == 0


def test_benchmark_score_weights_apps_equally():
    runs = _runs("a1", "tasks", [(g.CATCH, g.CORRECT_CLEAR)])
    runs += _runs("a2", "tasks", [(g.CATCH, g.CORRECT_CLEAR)])
    runs += _runs("a3", "tasks", [(g.CATCH, g.CORRECT_CLEAR)])
    runs += _runs("b1", "opentracks", [(g.MISS, g.CORRECT_CLEAR)])
    report = g.benchmark_score(runs, resamples=200)
    assert report["score"] == pytest.approx(0.5)
    assert report["apps"] == 2 and report["cases"] == 4
    assert 0.0 <= report["ci95"][0] <= report["score"] <= report["ci95"][1] <= 1.0


def test_grade_cli_writes_reward(tmp_path):
    import json

    record = tmp_path / "record.json"
    record.write_text(json.dumps({"steps": steps(FAULT_SCREEN), "verdict": verdict("DEFECT", 1)}))
    signature = tmp_path / "signature.json"
    signature.write_text(json.dumps(SIGNATURE))
    out = tmp_path / "logs" / "reward.json"
    assert (
        g.main(
            [
                "--record",
                str(record),
                "--signature",
                str(signature),
                "--build",
                "faulty",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert json.loads(out.read_text()) == {"reward": 1.0, "label": g.CATCH, "build": "faulty"}
