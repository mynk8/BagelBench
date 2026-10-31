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

"""Allowed actions and device conditions for benchmark agents."""

#: Device actions available to every benchmark agent. No shell, external URL,
#: app-data access or helper-model calls are exposed.
BENCH_ACTIONS = frozenset(
    {
        "click",
        "click_sequence",
        "long_press",
        "input_text",
        "swipe",
        "press_key",
        "manage_app",
        "wait_for_delay",
    }
)

CONDITION_TOOLS = (
    "rotate",
    "background_app",
    "kill_app_process",
    "set_network",
    "set_permission",
    "set_font_scale",
    "set_dark_mode",
)
