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

"""Turn notices for the Flash loop."""

#: One-line tail notice for the turn after a turn whose replies carried no visible
#: reasoning text. Thinking-mode models satisfy "reason first" inside their thought
#: channel and emit bare tool calls; the reminder costs no extra model call.
REASONING_REMINDER = (
    "--- Reminder ---\n"
    "Your previous turn carried no visible reasoning text (internal thinking is not"
    " shown). This turn, write one short paragraph of plain prose before calling a"
    " tool: what the screen shows, whether the last action worked, and what you"
    " check next and why."
)
