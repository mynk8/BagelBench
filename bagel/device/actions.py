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

"""Device capabilities shared by actuator implementations."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

DEVICE_ACTIONS = frozenset(
    {
        "click",
        "click_sequence",
        "long_press",
        "input_text",
        "swipe",
        "press_key",
        "manage_app",
        "wait_for_delay",
        "wait_for_text",
        "open_link",
        "erase_one_char",
        "focus_and_clear_text",
        "observe_screen",
        "take_screenshot",
        "get_ui_hierarchy",
    }
)


@dataclass(frozen=True)
class ExtensionTool:
    """An optional capability offered by an actuator backend."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
