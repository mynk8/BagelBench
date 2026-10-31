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

"""Flash's device tool declarations and the tool execution result envelope.

Execution itself lives in :class:`artemis.mcp.action_executor.McpActionExecutor`.
"""

import base64
import json
from typing import Any, Literal

from google.genai import types as genai_types
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field

from artemis.core.tool_declaration import ToolDeclaration
from artemis.mcp.action_specs import tool_declaration
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class ToolExecutionResult(BaseModel):
    """Standardized result produced by executing a mobile automation or utility tool."""

    tool_call_id: str
    tool_name: str
    status: Literal["success", "error", "cancelled"]
    text_summary: str
    screenshot_bytes: bytes | None = None
    screenshot_path: str | None = None
    ui_elements_text: str | None = None
    raw_result: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_langchain_tool_message(self) -> ToolMessage:
        """Converts execution result into a standardized multimodal LangChain ToolMessage."""
        content_blocks: list[dict[str, Any]] = [
            {"type": "text", "text": self.text_summary or f"Action '{self.tool_name}' dispatched."}
        ]
        if self.ui_elements_text:
            content_blocks.append(
                {
                    "type": "text",
                    "text": f"--- UI Element List ---\n{self.ui_elements_text}",
                }
            )
        if self.screenshot_bytes:
            b64_img = base64.b64encode(self.screenshot_bytes).decode("utf-8")
            content_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                }
            )
        return ToolMessage(
            tool_call_id=self.tool_call_id,
            name=self.tool_name,
            content=content_blocks,
            status=self.status,
        )


def prune_intermediate_screenshots(messages: list[Any]) -> None:
    """Prunes heavy binary screenshot blocks from intermediate observation messages.

    Keeps the latest screenshot across the conversation history to preserve context budget.
    Supports both LangChain BaseMessage and google.genai.types.Content formats.
    """
    if not messages:
        return

    # Check for google.genai.types.Content objects
    if hasattr(messages[0], "parts"):
        user_indices_with_images = []
        for idx in range(1, len(messages)):
            content = messages[idx]
            if getattr(content, "role", None) == "user" and getattr(content, "parts", None):
                for part in content.parts:
                    if getattr(part, "inline_data", None) is not None:
                        user_indices_with_images.append(idx)
                        break

        if len(user_indices_with_images) > 1:
            indices_to_prune = user_indices_with_images[:-1]
            for idx in indices_to_prune:
                content = messages[idx]
                new_parts = []
                for part in content.parts:
                    if getattr(part, "inline_data", None) is not None:
                        try:
                            new_parts.append(
                                genai_types.Part.from_text(
                                    text=(
                                        "[Screenshot of intermediate step omitted for performance]"
                                    )
                                )
                            )
                        except Exception as exc:
                            logger.debug(
                                "Could not build placeholder text part for pruned screenshot;"
                                " dropping it: %s",
                                exc,
                                exc_info=True,
                            )
                    else:
                        new_parts.append(part)
                content.parts = new_parts
        return

    # LangChain BaseMessage format
    last_img_msg_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        msg_content = getattr(msg, "content", None)
        if isinstance(msg_content, list):
            has_image = any(
                isinstance(block, dict) and block.get("type") in ("image_url", "image")
                for block in msg_content
            )
            if has_image:
                last_img_msg_idx = idx
                break

    for idx in range(len(messages)):
        if idx == last_img_msg_idx:
            continue
        msg = messages[idx]
        msg_content = getattr(msg, "content", None)
        if isinstance(msg_content, list):
            msg.content = [
                b
                for b in msg_content
                if not (isinstance(b, dict) and b.get("type") in ("image_url", "image"))
            ]


def normalize_coordinate_target(target: Any) -> int | list[int] | Any:
    """Normalizes coordinate targets or index references to standard types.

    Supports:
    - Integer index: e.g. 1 or "1" -> 1
    - Coordinate list: e.g. [500, 280] or ["500", "280"] -> [500, 280]
    - Serialized coordinate string: e.g. "[500, 280]" or "500, 280" -> [500, 280]
    """
    if isinstance(target, int):
        return target

    if isinstance(target, (list, tuple)):
        if len(target) == 2:
            try:
                return [int(target[0]), int(target[1])]
            except (ValueError, TypeError):
                pass
        elif len(target) == 1:
            return normalize_coordinate_target(target[0])

    if isinstance(target, str):
        cleaned = target.strip()
        if cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit()):
            return int(cleaned)
        try:
            parsed = json.loads(cleaned)
            return normalize_coordinate_target(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        if "," in cleaned:
            parts = [p.strip().strip("[]() ") for p in cleaned.split(",")]
            if len(parts) == 2:
                try:
                    return [int(parts[0]), int(parts[1])]
                except (ValueError, TypeError):
                    pass

    return target


# Device-action declarations are generated from the canonical manifest
# (artemis/mcp/action_specs.py); the historical constant names remain the public API.
CLICK_TOOL = tool_declaration("click")

CLICK_SEQUENCE_TOOL = tool_declaration("click_sequence")

LONG_PRESS_TOOL = tool_declaration("long_press")

INPUT_TEXT_TOOL = tool_declaration("input_text")

SWIPE_TOOL = tool_declaration("swipe")

PRESS_KEY_TOOL = tool_declaration("press_key")

MANAGE_APP_TOOL = tool_declaration("manage_app")

WAIT_FOR_DELAY_TOOL = tool_declaration("wait_for_delay")

DEVICE_TOOL_DECLARATIONS: list[ToolDeclaration] = [
    CLICK_TOOL,
    LONG_PRESS_TOOL,
    INPUT_TEXT_TOOL,
    SWIPE_TOOL,
    PRESS_KEY_TOOL,
    MANAGE_APP_TOOL,
    WAIT_FOR_DELAY_TOOL,
]
