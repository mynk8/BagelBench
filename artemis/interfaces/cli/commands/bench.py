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

"""Benchmark commands (artemis bench ...)."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

bench_app = typer.Typer(help="Serve the device to agents, export Harbor tasks, and grade runs.")

TOKEN_ENV = "ARTEMIS_BENCH_VERIFIER_TOKEN"


def _token(token: str | None) -> str:
    value = token or os.environ.get(TOKEN_ENV)
    if not value:
        raise typer.BadParameter(f"Pass --verifier-token or set {TOKEN_ENV}.")
    return value


@bench_app.command("serve")
def serve_command(
    slots: Annotated[Path, typer.Option(help="slots.json written by export-harbor.")],
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
    """Serve one device to agents: /t/<slot>/mcp per exported task."""
    from artemis.bench.server import serve

    serve(
        slots,
        runs_dir,
        serial,
        host=host,
        port=port,
        verifier_token=_token(verifier_token),
        public_hosts=public_host or [],
    )


@bench_app.command("export-harbor")
def export_harbor_command(
    cases: Annotated[Path, typer.Argument(help="JSON list of validated cases.")],
    out_dir: Annotated[Path, typer.Option(help="Output directory.")],
    device_host_url: Annotated[
        str, typer.Option(help="Device host as agents reach it, e.g. http://10.0.0.5:8765.")
    ],
    guidance: Annotated[str, typer.Option(help="directed, feature_hint or open.")] = "directed",
    repeats: int = 3,
    allow_host: Annotated[
        list[str] | None,
        typer.Option(help="Extra hosts the agent may reach, e.g. its model API. Repeatable."),
    ] = None,
    verifier_token: Annotated[str | None, typer.Option(help=f"Defaults to ${TOKEN_ENV}.")] = None,
) -> None:
    """Write one Harbor task per case, build and repeat, plus slots.json and manifest.json."""
    from artemis.bench.harbor import export_harbor

    summary = export_harbor(
        json.loads(cases.read_text(encoding="utf-8")),
        out_dir,
        device_host_url=device_host_url,
        verifier_token=_token(verifier_token),
        guidance=guidance,
        repeats=repeats,
        extra_allowed_hosts=allow_host or [],
    )
    typer.echo(json.dumps(summary, indent=2))


@bench_app.command("grade")
def grade_command(
    record: Annotated[Path, typer.Argument(help="Run directory or JSON record export.")],
    signature: Annotated[Path, typer.Option(help="The case's signature.json.")],
    build: Annotated[str, typer.Option(help="faulty or correct.")],
) -> None:
    """Label one run without a model."""
    from artemis.bench.grading import label_run, load_record, reward_for

    steps, verdict = load_record(record)
    label = label_run(build, steps, verdict, json.loads(signature.read_text(encoding="utf-8")))
    typer.echo(json.dumps({"label": label, "reward": reward_for(label)}))


@bench_app.command("score")
def score_command(
    manifest: Annotated[Path, typer.Option(help="manifest.json written by export-harbor.")],
    results: Annotated[Path, typer.Option(help="Harbor job directory with reward.json files.")],
) -> None:
    """Pair score per case, averaged over apps, with a bootstrap 95% interval."""
    from artemis.bench.scoring import score_results

    typer.echo(json.dumps(score_results(manifest, results), indent=2))
