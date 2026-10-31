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

"""Turn notices and mid-run user guidance for the Flash loop."""

import json
from pathlib import Path
from typing import NamedTuple

from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


#: One-line tail notice for the turn after a turn whose replies carried no visible
#: reasoning text. Thinking-mode models satisfy "reason first" inside their thought
#: channel and emit bare tool calls; the reminder costs no extra model call.
REASONING_REMINDER = (
    "--- Reminder ---\n"
    "Your previous turn carried no visible reasoning text (internal thinking is not"
    " shown). This turn, write one short paragraph of plain prose before calling a"
    " Turn-Ending Action: what the screen shows, whether the last action worked, and"
    " what you do next and why."
)


USER_GUIDANCE_MARKER = "--- User Guidance ---"


#: Prefix of the persistent user-instruction line (see :func:`render_user_guidance`).
USER_INSTRUCTION_PREFIX = "User instruction"


class UserGuidance(NamedTuple):
    """The two observation blocks delivering a mid-run user instruction.

    ``wrapper`` is the per-turn ``--- User Guidance ---`` framing (relay
    notice, rank, release-loop wording): it is marked ephemeral and leaves
    with the recent window. ``body`` is the verbatim instruction as one
    self-contained line; it is added as a regular block so it stays in the
    active window until the turn is chunk-compressed, at which point the
    chunk's ``user_lines`` carry it verbatim. Standing instructions remain
    visible after the turn in which they arrived.
    """

    body: str
    wrapper: str


def render_user_instruction(instruction: str, *, offset_label: str | None = None) -> str:
    """The persistent one-line body: ``User instruction (T+mm:ss): "..."``.

    ``offset_label`` is the session-relative time the instruction was
    delivered when the call site has it; omitted otherwise.
    """
    when = f" ({offset_label})" if offset_label else ""
    return f'{USER_INSTRUCTION_PREFIX}{when}: "{instruction}"'


def render_user_guidance(
    instruction: str,
    *,
    release_loop: bool = False,
    has_plan: bool = True,
    offset_label: str | None = None,
) -> UserGuidance:
    """The observation blocks delivering a mid-run user instruction.

    One rendering for both profiles: the instruction is stated as what it is (an
    external interruption from the user, relayed by the system) rather than as
    advice to be weighed, and it explicitly outranks the plan and its check lines.
    Returns ``(body, wrapper)``; callers add ``wrapper`` with ``ephemeral=True``
    and ``body`` without (see :class:`UserGuidance`).
    """
    rank = (
        " It outranks the task plan and its check lines: edit the plan to match,"
        " check lines included."
        if has_plan
        else " It outranks your current milestones: adjust them to match."
    )
    lines = [
        USER_GUIDANCE_MARKER,
        "The user watching this run sent the instruction quoted below; the system"
        " relays it as an external interruption, like a stop signal." + rank,
        "Act on it from this turn: reconcile it with the current screen and recent"
        " history, then choose the next action. The quoted line stays in your"
        " history as a standing instruction until the user sends another.",
    ]
    if release_loop:
        lines.append(
            "The user has explicitly authorized stopping any ongoing monitoring loop;"
            " you may now wrap up and complete the task."
        )
    return UserGuidance(
        body=render_user_instruction(instruction, offset_label=offset_label),
        wrapper=chr(10).join(lines),
    )


def check_injected_instruction_file(base_dir: str) -> dict | None:
    """Consumes a pending injected-instruction payload, if any.

    Returns the payload dict: `instruction` (str | None) plus the explicit
    `release_loop` stop signal (bool) declared by the injecting caller.
    """
    instruction_path = Path(base_dir) / "injected_instruction.json"
    if instruction_path.exists():
        with open(instruction_path, encoding="utf-8") as f:
            data = json.load(f)
        instruction_path.unlink()
        payload = {
            "instruction": data.get("instruction"),
            "release_loop": bool(data.get("release_loop")),
        }
        logger.info(f"Read and deleted injected instruction payload: {payload}")
        return payload
    return None
