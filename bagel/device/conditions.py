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

"""Mobile-condition tools: device states a tester applies, never a shell.

Each tool maps to fixed ``adb shell`` argv templates run by the harness. The agent
chooses the condition (rotate, background, kill, network, permission, font scale,
dark mode); it never supplies a command. App-scoped conditions only ever target
the package under test, fixed per run by the server.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Shell = Callable[[list[str]], Awaitable[str]]
"""Runs one ``adb shell`` argv on the device under test and returns its output."""

_PERMISSION_RE = re.compile(r"^android\.permission\.[A-Z_]+$")
FONT_SCALES = (0.85, 1.0, 1.15, 1.3, 1.5, 2.0)


@dataclass(frozen=True)
class ConditionResult:
    ok: bool
    message: str


class DeviceConditions:
    """Applies tester-visible device conditions to one device and one app."""

    def __init__(self, shell: Shell, app_package: str | None):
        self._shell = shell
        self.app_package = app_package

    async def _run(self, *argvs: list[str]) -> None:
        for argv in argvs:
            await self._shell(argv)

    def _require_app(self) -> str:
        if not self.app_package:
            raise ValueError("No app under test is configured for this run.")
        return self.app_package

    async def rotate(self, orientation: str) -> ConditionResult:
        rotations = {
            "portrait": "0",
            "landscape": "1",
            "reverse_portrait": "2",
            "reverse_landscape": "3",
        }
        if orientation not in rotations:
            return ConditionResult(False, f"orientation must be one of {', '.join(rotations)}")
        await self._run(
            ["settings", "put", "system", "accelerometer_rotation", "0"],
            ["settings", "put", "system", "user_rotation", rotations[orientation]],
        )
        return ConditionResult(True, f"Rotated the device to {orientation}.")

    async def background_app(self) -> ConditionResult:
        await self._run(["input", "keyevent", "KEYCODE_HOME"])
        return ConditionResult(True, "Sent the app to the background (home screen).")

    async def kill_app_process(self) -> ConditionResult:
        """Process death as Android does it: background first, then kill the process."""
        package = self._require_app()
        await self._run(["input", "keyevent", "KEYCODE_HOME"], ["am", "kill", package])
        return ConditionResult(
            True,
            "Backgrounded the app and killed its process. Reopen it from recents or launch it"
            " to see whether its state survived.",
        )

    async def set_network(self, enabled: bool) -> ConditionResult:
        state = "enable" if enabled else "disable"
        await self._run(["svc", "wifi", state], ["svc", "data", state])
        return ConditionResult(True, f"Network {'enabled' if enabled else 'disabled'}.")

    async def set_permission(self, permission: str, granted: bool) -> ConditionResult:
        if not _PERMISSION_RE.match(permission):
            return ConditionResult(False, "permission must look like android.permission.CAMERA")
        package = self._require_app()
        await self._run(["pm", "grant" if granted else "revoke", package, permission])
        return ConditionResult(True, f"{'Granted' if granted else 'Revoked'} {permission}.")

    async def set_font_scale(self, scale: float) -> ConditionResult:
        if scale not in FONT_SCALES:
            return ConditionResult(
                False, f"scale must be one of {', '.join(map(str, FONT_SCALES))}"
            )
        await self._run(["settings", "put", "system", "font_scale", str(scale)])
        return ConditionResult(True, f"Font scale set to {scale}.")

    async def set_dark_mode(self, enabled: bool) -> ConditionResult:
        await self._run(["cmd", "uimode", "night", "yes" if enabled else "no"])
        return ConditionResult(True, f"Dark mode {'on' if enabled else 'off'}.")


async def foreground_activity(shell: Shell) -> str | None:
    """The resumed activity (``package/.Activity``), read harness-side for grading."""
    output = await shell(["dumpsys", "activity", "activities"])
    match = re.search(r"(?:mResumedActivity|topResumedActivity)[^\n]*?\s([\w.]+/[\w.$]+)", output)
    return match.group(1) if match else None
