"""Codex CLI model adapter. Artemis owns tool execution and device traces."""

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool


class CodexChatModel(BaseChatModel):
    model_name: str = "gpt-6-luna"
    timeout_seconds: float = 180
    tools: list[dict[str, Any]] = []
    tool_choice: Any = None

    @property
    def _llm_type(self) -> str:
        return "artemis-codex-cli"

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name, "provider": "codex"}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self.model_copy(
            update={"tools": [convert_to_openai_tool(t) for t in tools], "tool_choice": tool_choice}
        )

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        # Isolate each inference from project files. Use existing Codex auth/config.
        with tempfile.TemporaryDirectory(prefix="artemis-codex-") as directory:
            root = Path(directory)
            images = []
            transcript = []
            for message in messages:
                content = message.content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "image_url":
                            image = block["image_url"]
                            url = image if isinstance(image, str) else image["url"]
                            if not url.startswith("data:image/") or ";base64," not in url:
                                raise ValueError(
                                    "Codex requires inline screenshot data; remote image URLs are unsupported"
                                )
                            header, encoded = url.split(",", 1)
                            suffix = ".png" if "png" in header else ".jpg"
                            path = root / f"image-{len(images)}{suffix}"
                            path.write_bytes(base64.b64decode(encoded, validate=True))
                            images.append(path)
                            parts.append(f"[Attached screenshot {len(images)}]")
                        else:
                            raise ValueError(
                                f"Unsupported Codex content block: {block.get('type')}"
                            )
                    content = "\n".join(parts)
                record = {"role": message.type, "content": content}
                if getattr(message, "tool_calls", None):
                    record["tool_calls"] = message.tool_calls
                if getattr(message, "tool_call_id", None):
                    record["tool_call_id"] = message.tool_call_id
                transcript.append(record)
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "content": {"type": "string"},
                    "tool_calls": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "arguments_json": {"type": "string"},
                            },
                            "required": ["name", "arguments_json"],
                        },
                    },
                },
                "required": ["content", "tool_calls"],
            }
            (root / "schema.json").write_text(json.dumps(schema))
            prompt = (
                "You are the model for an Android testing harness. Follow the supplied conversation. "
                "Choose ONLY from the supplied Artemis tools; return tool requests for Artemis to execute. "
                "Do not execute tools, inspect files, or use your own shell/MCP/browser capabilities. "
                "Return JSON matching the output schema. arguments_json is a JSON object encoded as a string. "
                "Do not invent observations, tool results, or private reasoning.\n"
                + json.dumps(
                    {
                        "conversation": transcript,
                        "available_tools": self.tools,
                        "tool_choice": self.tool_choice,
                    }
                )
            )
            command = [
                os.environ.get("ARTEMIS_CODEX_BIN", "codex"),
                "exec",
                "--model",
                self.model_name,
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--output-schema",
                str(root / "schema.json"),
                "--output-last-message",
                str(root / "result.json"),
                "--cd",
                directory,
            ]
            profile = os.environ.get("ARTEMIS_CODEX_PROFILE")
            if profile:
                command += ["--profile", profile]
            for path in images:
                command += ["--image", str(path)]
            command += ["-"]
            try:
                result = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Codex model request timed out") from exc
            if result.returncode or not (root / "result.json").exists():
                # CLI stderr can contain credentials or full prompt data. Do not expose it.
                raise RuntimeError(
                    "Codex inference failed. Check Codex login and configured model access in your terminal."
                )
            response = json.loads((root / "result.json").read_text())
            tools = {tool["function"]["name"]: tool["function"] for tool in self.tools}
            calls = []
            for call in response["tool_calls"]:
                if call["name"] not in tools:
                    raise ValueError("Codex requested a tool outside the supplied Artemis tool set")
                args = json.loads(call["arguments_json"])
                if not isinstance(args, dict):
                    raise ValueError("Codex tool arguments must be a JSON object")
                calls.append(
                    {"name": call["name"], "args": args, "id": f"codex-{uuid.uuid4().hex}"}
                )
            if self.tool_choice in ("required", "any") and not calls:
                raise ValueError("Codex did not return a required tool call")
            forced = self.tool_choice
            if isinstance(forced, dict):
                forced = forced.get("function", {}).get("name")
            if forced == "none" and calls:
                raise ValueError("Codex returned tools when tools were disabled")
            if (
                isinstance(forced, str)
                and forced in tools
                and (not calls or any(c["name"] != forced for c in calls))
            ):
                raise ValueError("Codex did not use the required Artemis tool")
            message = AIMessage(
                content=response["content"],
                tool_calls=calls,
                response_metadata={
                    "model_name": self.model_name,
                    "provider": "codex",
                    "transport": "codex-exec",
                },
            )
            return ChatResult(generations=[ChatGeneration(message=message)])
