"""Keep domain rules independent of protocol adapters and agent initialization."""

import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("domain", ["benchmark", "device", "diagnostics"])
def test_domains_do_not_import_protocols_or_web_application(domain):
    forbidden = (
        "bagel.transports",
        "bagel.integrations",
        "apps.harness_server",
        "mcp",
        "fastapi",
        "starlette",
    )
    violations = []
    for path in (ROOT / "bagel" / domain).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            for name in names:
                if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")
    assert not violations, "\n".join(violations)


def test_benchmark_records_and_grading_work_without_third_party_packages():
    # -S omits site-packages. The domain and its root package must need only stdlib.
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from bagel.benchmark import grading, recording, scoring, slots; "
            "assert grading.label_run('correct', [], {'verdict': 'NO_DEFECT'}, {}) == 'correct_clear'",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_no_internal_agent_stack_is_shipped():
    import bagel

    assert bagel.__all__ == ["__version__"]
    for name in ("agents", "llm", "memory", "execution", "interfaces/sdk"):
        assert not (ROOT / "bagel" / name).exists()


def test_typecheck_scope_only_names_existing_modules():
    config = json.loads((ROOT / "pyright-core.json").read_text())
    assert all((ROOT / name).exists() for name in config["include"])
