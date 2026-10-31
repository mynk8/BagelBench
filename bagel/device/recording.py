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

"""Build the scrcpy command for optional driver-level recording."""

from pathlib import Path


def build_scrcpy_record_command(
    scrcpy_executable: str,
    device_id: str,
    output_path: Path,
    video_bit_rate: str = "2M",
    lock_capture_orientation: bool = True,
) -> list[str]:
    """Build the shared scrcpy command used by all recording paths.

    Each recording segment locks the orientation present when scrcpy starts.
    The recording supervisor starts a new segment when Android rotates, so a
    segment never contains multiple coded sizes while still displaying the app
    in its natural orientation.
    """
    command = [
        scrcpy_executable,
        "--serial",
        device_id,
        "--no-window",
        "--record",
        str(output_path),
        "--record-format",
        "mkv",
        "--video-bit-rate",
        video_bit_rate,
    ]
    if lock_capture_orientation:
        command.append("--capture-orientation=@")
    return command
