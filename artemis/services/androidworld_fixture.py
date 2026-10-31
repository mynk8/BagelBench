"""AndroidWorld state interventions isolated from the agent's Python environment."""

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from artemis.config import WORKSPACE_ROOT

PINNED_REVISION = "55ddaf5edc6f6c25673aed343907d5b9dca66f84"

SUPPORTED_TASKS = ("SimpleCalendarAddOneEvent", "ExpenseAddSingle", "RecipeAddSingleRecipe")


def invoke(request: dict) -> dict:
    serial = request.get("device_serial", "")
    if not re.fullmatch(r"emulator-\d+", serial):
        raise ValueError("Select a dedicated AndroidWorld emulator (emulator-NNNN).")
    from artemis.runtime import DeviceExecutionLock

    lock = DeviceExecutionLock(device_id=serial, description="AndroidWorld state fixture")
    lock.acquire(blocking=False)
    try:
        root = Path(
            os.environ.get(
                "ARTEMIS_ANDROIDWORLD_PATH", str(Path(WORKSPACE_ROOT).parent / "android_world")
            )
        ).resolve()
        interpreter = os.environ.get("ARTEMIS_ANDROIDWORLD_PYTHON", str(root / ".venv/bin/python"))
        if not Path(interpreter).is_file():
            raise ValueError(
                "AndroidWorld Python environment is missing. Set ARTEMIS_ANDROIDWORLD_PYTHON."
            )
        try:
            revision = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            dirty = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                    "--",
                    "android_world",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
            generated = {
                f"?? android_world/task_evals/information_retrieval/proto/{name}_pb2{suffix}.py"
                for name in ("state", "task")
                for suffix in ("", "_grpc")
            }
            dirty = [line for line in dirty if line not in generated]
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Cannot verify AndroidWorld source checkout.") from error
        if revision != PINNED_REVISION or dirty:
            raise ValueError(
                "AndroidWorld source must be clean and at the pinned revision " + PINNED_REVISION
            )
        request = {
            **request,
            "dataset_revision": revision,
            "adb_path": shutil.which("adb") or "adb",
            "grpc_port": int(os.environ.get("ARTEMIS_ANDROIDWORLD_GRPC_PORT", "8554")),
        }
        with tempfile.TemporaryDirectory(prefix="artemis-aw-") as temporary:
            incoming, outgoing = Path(temporary) / "request.json", Path(temporary) / "result.json"
            incoming.write_text(json.dumps(request))
            bridge = Path(WORKSPACE_ROOT) / "apps/research_ui/scripts/androidworld_device.py"
            env = {**os.environ, "PYTHONPATH": str(root)}
            subprocess.run(
                [interpreter, str(bridge), str(incoming), str(outgoing)],
                env=env,
                capture_output=True,
                timeout=180,
                check=True,
            )
            result = json.loads(outgoing.read_text())
        if result.get("error"):
            raise ValueError(result["error"])
        if request["mode"] == "prepare":
            try:
                screenshot = subprocess.run(
                    [request["adb_path"], "-s", serial, "exec-out", "screencap", "-p"],
                    capture_output=True,
                    timeout=15,
                    check=True,
                ).stdout
                if screenshot.startswith(b"\x89PNG\r\n\x1a\n"):
                    result["_screenshot_base64"] = base64.b64encode(screenshot).decode("ascii")
            except (OSError, subprocess.SubprocessError):
                pass
        return result
    finally:
        lock.release()
