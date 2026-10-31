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

"""BAGEL Unified Command Line Interface (CLI)."""

from typing import Annotated

from bagel._version import __version__
from bagel.interfaces.cli.commands.bench import bench_app
from bagel.interfaces.cli.commands.doctor import doctor_command
from bagel.interfaces.cli.commands.helper import helper_app
from third_party.mobile_use.utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
import typer

logger = get_logger(__name__)

app = typer.Typer(
    name="bagel",
    help="☕ Bagel: Android QA benchmark tools.",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)

# Register subcommands
app.command(name="doctor", help="Check system prerequisites, device status, and configuration.")(
    doctor_command
)
app.add_typer(bench_app, name="bench", help="Android QA benchmark: serve, validate, grade, score.")
app.add_typer(
    helper_app, name="helper", help="Manage the Accessibility Helper APK on attached devices."
)


def version_callback(value: bool):
    if value:
        console = Console()
        console.print(
            Panel(
                f"[bold cyan]Bagel Android QA[/bold cyan] v{__version__}\n"
                "[dim]Device tools and benchmark evaluation[/dim]",
                title="☕ Bagel",
                expand=False,
            )
        )
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show Bagel version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """Bagel Android QA benchmark CLI."""
    pass


def cli():
    """Main CLI entrypoint."""
    app()


if __name__ == "__main__":
    cli()
