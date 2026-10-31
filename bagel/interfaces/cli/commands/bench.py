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

"""Benchmark commands (bagel bench ...)."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

bench_app = typer.Typer(
    help="Serve the device to agents, validate native Harbor tasks, and grade runs."
)

TOKEN_ENV = "BAGEL_BENCH_VERIFIER_TOKEN"


def _token(token: str | None) -> str:
    value = token or os.environ.get(TOKEN_ENV)
    if not value:
        raise typer.BadParameter(f"Pass --verifier-token or set {TOKEN_ENV}.")
    return value


@bench_app.command("serve")
def serve_command(
    tasks: Annotated[Path, typer.Option(help="Native Harbor task dataset directory.")],
    serial: Annotated[str, typer.Option(help="Device under test, e.g. emulator-5554.")],
    runs_dir: Annotated[Path, typer.Option(help="Where run records are written.")] = Path(
        "traces/bench"
    ),
    host: str = "127.0.0.1",
    port: int = 8765,
    public_host: Annotated[
        list[str] | None,
        typer.Option(help="Host name or IP agents use to reach this server. Repeatable."),
    ] = None,
    verifier_token: Annotated[str | None, typer.Option(help=f"Defaults to ${TOKEN_ENV}.")] = None,
) -> None:
    """Serve one device to agents: /t/<slot>/mcp per native task."""
    from bagel.transports.http.benchmark import serve
    from bagel.integrations.harbor import load_tasks

    definitions = load_tasks(tasks)
    serve(
        {task.slot.slot_id: task.slot for task in definitions},
        runs_dir,
        serial,
        host=host,
        port=port,
        verifier_token=_token(verifier_token),
        public_hosts=public_host or [],
    )


@bench_app.command("validate-tasks")
def validate_tasks_command(
    tasks: Annotated[Path, typer.Argument(help="Native Harbor task dataset directory.")],
) -> None:
    """Validate the Android contract and paired tasks without running a device or model."""
    from bagel.integrations.harbor import load_tasks

    definitions = load_tasks(tasks)
    typer.echo(json.dumps({"tasks": len(definitions), "pairs": len(definitions) // 2}))


@bench_app.command("grade")
def grade_command(
    record: Annotated[Path, typer.Argument(help="Run directory or JSON record export.")],
    signature: Annotated[Path, typer.Option(help="The case's signature.json.")],
    build: Annotated[str, typer.Option(help="faulty or correct.")],
) -> None:
    """Label one run without a model."""
    from bagel.benchmark.grading import label_run, load_record, reward_for

    steps, verdict = load_record(record)
    label = label_run(build, steps, verdict, json.loads(signature.read_text(encoding="utf-8")))
    typer.echo(json.dumps({"label": label, "reward": reward_for(label)}))


@bench_app.command("score")
def score_command(
    tasks: Annotated[Path, typer.Option(help="Native Harbor task dataset directory.")],
    results: Annotated[Path, typer.Option(help="Harbor job directory with reward.json files.")],
) -> None:
    """Pair score per case, averaged over apps, with a bootstrap 95% interval."""
    from bagel.benchmark.scoring import score_results

    from bagel.integrations.harbor import load_tasks

    definitions = load_tasks(tasks)
    typer.echo(
        json.dumps(score_results([task.score_entry() for task in definitions], results), indent=2)
    )
