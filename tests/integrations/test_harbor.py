"""Native Harbor Android tasks: public metadata, private fixtures and pair validation."""

import json
from pathlib import Path
import shutil
import tomllib

import pytest
from typer.testing import CliRunner

from bagel.benchmark.scoring import score_results
from bagel.integrations.harbor import load_task, load_tasks
from bagel.interfaces.cli.main import app

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "android-harbor"


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "tasks"
    for repeat in (1, 2):
        for build in ("correct", "faulty"):
            slot = f"slot{repeat}{0 if build == 'correct' else 1}"
            task = root / slot
            shutil.copytree(TEMPLATE, task)
            config = (task / "task.toml").read_text().replace("replace-with-opaque-id", slot)
            (task / "task.toml").write_text(config)
            private = (task / "tests" / "android.toml").read_text()
            private = private.replace('build = "correct"', f'build = "{build}"')
            private = private.replace("repeat = 1", f"repeat = {repeat}")
            private = private.replace("validated = false", "validated = true")
            (task / "tests" / "android.toml").write_text(private)
    return root


def test_native_tasks_need_no_conversion_or_generated_manifest(dataset):
    tasks = load_tasks(dataset)
    assert len(tasks) == 4
    assert sorted((t.slot.build, t.repeat) for t in tasks) == [
        ("correct", 1),
        ("correct", 2),
        ("faulty", 1),
        ("faulty", 2),
    ]
    assert not (dataset / "slots.json").exists()
    assert not (dataset / "manifest.json").exists()
    assert all(t.slot.setup_cwd == str(t.path) for t in tasks)
    assert all(t.slot.step_budget == 40 for t in tasks)


def test_public_metadata_does_not_contain_oracle_fields(dataset):
    for task in load_tasks(dataset):
        config = tomllib.loads((task.path / "task.toml").read_text())
        public = config["metadata"]["android"]
        assert set(public) == {"version", "app", "app_package", "guidance", "action_budget"}
        assert config["verifier"]["environment_mode"] == "separate"
        assert config["verifier"]["env"]["BENCH_VERIFIER_TOKEN"] == "${BAGEL_BENCH_VERIFIER_TOKEN}"
        assert task.slot.signature is not None


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ("validated = true", "validated = false", "not been validated"),
        ('build = "correct"', 'build = "other"', "case_id and build"),
        ("repeat = 1", "repeat = 0", "positive integer"),
    ],
)
def test_invalid_private_definition_is_rejected(dataset, old, new, error):
    path = dataset / "slot10" / "tests" / "android.toml"
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ValueError, match=error):
        load_task(path.parent.parent)


def test_leaking_a_build_label_into_public_android_metadata_is_rejected(dataset):
    task = dataset / "slot10"
    config = task / "task.toml"
    config.write_text(
        config.read_text().replace("version = 1\n", 'version = 1\nbuild = "correct"\n')
    )
    with pytest.raises(ValueError, match="oracle data"):
        load_task(task)


def test_pair_instructions_must_match(dataset):
    (dataset / "slot11" / "instruction.md").write_text("A different test")
    with pytest.raises(ValueError, match="share their instruction"):
        load_tasks(dataset)


def test_missing_twin_and_duplicate_endpoint_are_rejected(dataset):
    shutil.rmtree(dataset / "slot11")
    with pytest.raises(ValueError, match="one correct and one faulty"):
        load_tasks(dataset)
    shutil.copytree(dataset / "slot10", dataset / "duplicate")
    with pytest.raises(ValueError, match="distinct"):
        load_tasks(dataset)


def test_token_must_not_be_embedded_in_task_file(dataset):
    task = dataset / "slot10"
    path = task / "task.toml"
    path.write_text(
        path.read_text().replace("${BAGEL_BENCH_VERIFIER_TOKEN}", "do-not-embed-credentials")
    )
    with pytest.raises(ValueError, match="environment reference"):
        load_task(task)


def test_native_task_entries_join_harbor_rewards_without_a_manifest(dataset, tmp_path):
    tasks = load_tasks(dataset)
    results = tmp_path / "job"
    for task in tasks:
        if task.repeat == 2 and task.slot.build == "correct":
            continue
        label = "catch" if task.slot.build == "faulty" else "correct_clear"
        path = results / f"{task.path.name}__trial" / "verifier" / "reward.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"reward": 1.0, "label": label}))
    report = score_results([t.score_entry() for t in tasks], results)
    assert report["score"] == 0.5 and report["missing_trials"] == 1


def test_validation_cli_uses_native_harbor_tasks(dataset):
    runner = CliRunner()
    result = runner.invoke(app, ["bench", "validate-tasks", str(dataset)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"tasks": 4, "pairs": 2}
    assert "export-harbor" not in runner.invoke(app, ["bench", "--help"]).output
