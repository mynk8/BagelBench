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

"""FlashRunner: the benchmark's reference agent.

One model runs an observe-think-act loop as a QA tester. Every device call goes
through the recording bench server (:mod:`artemis.bench`) via the run context's
action session, so Flash has exactly the tool surface external harnesses get, and
the run ends when the model calls ``submit_verdict``. No helper model is called.

Conversation shape: the prompt is built every turn from a session
:class:`TranscriptLedger` -- a byte-stable system prefix, the committed earlier
turns (old UI lists stripped at depth 1, old screenshots scrubbed), and a fresh
tail carrying the current observation under a ``# CURRENT OBSERVATION`` header
with its step number. Per-turn notices (the reasoning reminder after a silent
turn, the no-tool-call nudge, the final-turn warning) are marked ephemeral so the
ledger's scrub edge deletes them once they leave the recent window.
"""

import asyncio
import base64
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import uuid

from jinja2 import Template
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from artemis.bench.flash import BenchRun
from artemis.bench.recorder import load_steps, load_verdict
from artemis.bench.server import BENCH_ACTIONS
from artemis.mcp.action_manifest import filter_declarations
from artemis.agents.flash.guidance import REASONING_REMINDER
from artemis.agents.flash.tool_declarations import (
    CLICK_SEQUENCE_TOOL,
    DEVICE_TOOL_DECLARATIONS,
    prune_intermediate_screenshots,
)
from artemis.config import MemoryTranscriptConfig, load_agent_config
from artemis.context import ArtemisContext
from artemis.controllers.unified_controller import UnifiedMobileController
from artemis.data_engine.trace import trace
from artemis.state import State
from artemis.llm.structured import ParseFailure, parse_structured
from artemis.mcp.action_executor import McpActionExecutor
from artemis.memory.transcript import PRO_UI_LIST_MARKER, TranscriptLedger, mark_ephemeral
from artemis.services.llm import (
    RobustChatModelWrapper,
    acomplete,
    get_google_llm,
    get_llm,
    invoke_llm_with_timeout_message,
)
from artemis.tools.tool_wrapper import tool_result_messages
from artemis.utils.coordinates import (
    COORDINATE_SPACE_KEY,
    COORDINATE_SPACE_NORMALIZED,
    parse_swipe_parameters,
)
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

TERMINAL_TOOL = "submit_verdict"

_NO_TOOL_CALL_NOTICE = (
    "You did not call any tools last turn. Please make progress by calling an"
    f" action tool or '{TERMINAL_TOOL}'."
)

_FINAL_TURN_WARNING = f"[WARNING] This is your final turn; only '{TERMINAL_TOOL}' is available."


@dataclass
class _TurnRecord:
    """What one reactive turn produced, for committing it into the ledger.

    ``step_keys`` are the DataEngine step ids recorded this turn (one per
    executed action; the tool_call_id stands in without a DataEngine) — the
    first keys the observation screenshot to its visual-transition summary,
    all of them feed the chunk ledger. ``actions`` collects the outcome of
    every device action so the turn's execution result can be rendered.
    """

    step_keys: list[str] = field(default_factory=list)
    actions: list[tuple[str, str, str]] = field(default_factory=list)

    def result(self) -> dict | None:
        """The turn's execution result in the validator-report shape.

        ``None`` unless an action failed: Flash executes synchronously and each
        action's tool message already carries its outcome, so a result message
        would only repeat it. A failure is worth its own message because it
        carries the error the turn ended on.
        """
        for name, status, text in self.actions:
            if status != "success":
                # Executor messages name the action themselves ("Error
                # executing click: ..."); prefix only the ones that don't.
                return {"status": "failed", "error": text if name in text else f"{name}: {text}"}
        return None


class FlashRunner:
    """Reactive, ultra-fast agent execution loop supporting all VLM providers."""

    def __init__(
        self,
        ctx: ArtemisContext,
        goal: str,
        bench: BenchRun,
        max_turns: int | None = None,
    ):
        self.ctx = ctx
        self.goal = goal
        self.bench = bench
        try:
            cfg = load_agent_config()
            self.max_turns = max_turns if max_turns is not None else cfg.flash.max_turns
            self.prune_history_xml = cfg.memory.transcript.prune_history_xml
            self.transcript_cfg = cfg.memory.transcript
        except Exception:
            self.max_turns = max_turns if max_turns is not None else 0
            self.prune_history_xml = True
            self.transcript_cfg = MemoryTranscriptConfig()

        self.controller = UnifiedMobileController(ctx)
        self.executor = McpActionExecutor(ctx, self.controller)

    @property
    def turn_limit(self) -> int | None:
        """The reactive turn cap, or ``None`` when the loop is unbounded."""
        try:
            limit = int(self.max_turns) if self.max_turns is not None else 0
        except (TypeError, ValueError):
            return None
        return limit if limit > 0 else None

    def _get_tools(self) -> list:
        """The bench tool surface: bench device actions plus the bench extensions
        (mobile conditions and ``submit_verdict``) the actuator declares."""
        tools = [t for t in DEVICE_TOOL_DECLARATIONS if t.name in BENCH_ACTIONS]
        tools.insert(1, CLICK_SEQUENCE_TOOL)
        return filter_declarations(tools, self.ctx.actuator, "flash")

    def _prune_intermediate_screenshots(self, messages: list[BaseMessage]) -> None:
        """Prunes binary screenshot blocks from intermediate observation messages."""
        prune_intermediate_screenshots(messages)

    # ------------------------------------------------------------------
    # run() setup helpers
    # ------------------------------------------------------------------

    def _build_ledger(self) -> TranscriptLedger:
        """Builds the session transcript ledger (scrub edge only, no summary model).

        The ``T+mm:ss`` clock is anchored to the DataEngine session start.
        """
        engine = getattr(self.ctx, "data_engine", None)
        session_start = getattr(engine, "session_start_time", None) if engine else None
        cfg = self.transcript_cfg
        ledger = TranscriptLedger(
            step_memory=None,
            prune_history_xml=self.prune_history_xml,
            image_scrub_depth=getattr(cfg, "image_scrub_depth", 3),
            pending_grace_steps=getattr(cfg, "pending_grace_steps", 3),
            xml_scrub_depth=getattr(cfg, "xml_scrub_depth", 1),
            image_scrub_depth_relaxed=getattr(cfg, "image_scrub_depth_relaxed", None),
            context_budget_tokens=getattr(cfg, "context_budget_tokens", None),
            start_ratio=getattr(cfg, "start_ratio", None),
            session_start=session_start if isinstance(session_start, (int, float)) else None,
        )
        try:
            self.ctx.transcript_ledger = ledger
        except (AttributeError, TypeError, ValueError):
            pass
        return ledger

    #: The model of the current run; decides how screenshot tool results travel.
    _llm = None

    def _init_llm(self):
        """Initializes the Universal LLM via the Service Layer."""
        try:
            return get_llm(self.ctx, name="operator")
        except Exception as e:
            logger.warning(f"Failed to get operator LLM from config, using default: {e}")

            return RobustChatModelWrapper(get_google_llm(model_name="gemini-2.5-flash"), self.ctx)

    def _render_system_prompt(self, tools_declaration: list) -> str:
        """Renders the tester prompt from flash_runner.md.

        Tool-teaching segments are gated on the available tool set so an absent
        tool leaves no trace in the prompt.
        """
        prompt_path = Path(__file__).parent / "flash_runner.md"
        prompt_template = prompt_path.read_text(encoding="utf-8")
        available_tools = frozenset(t.name for t in tools_declaration)
        return Template(prompt_template).render(goal=self.goal, available_tools=available_tools)

    # ------------------------------------------------------------------
    # Per-turn helpers (observe / think)
    # ------------------------------------------------------------------

    def _build_tail(
        self,
        ledger: TranscriptLedger,
        turns: int,
        img_bytes,
        xml_list,
        *,
        notices: list[str] | None = None,
        is_final: bool = False,
        previous_turn_silent: bool = False,
    ) -> HumanMessage:
        """Builds this turn's observation tail.

        The header names the step whose screen this is, so the model can cite it
        as ``flag_step``. The test is stated once, in the system prompt. Every
        per-turn notice is marked ephemeral so it leaves with the recent window.
        """
        # ``turns`` is kept for call-site symmetry: the tail has the same shape
        # on every turn.
        blocks: list[str | dict] = [
            {
                "type": "text",
                "text": (
                    f"# CURRENT OBSERVATION [step {self._current_step()}]"
                    f" [{ledger.elapsed_label()}]"
                ),
            }
        ]
        if img_bytes:
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            blocks.append({"type": "text", "text": "--- Current Screenshot ---"})
            blocks.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            )
        if xml_list:
            blocks.append({"type": "text", "text": f"{PRO_UI_LIST_MARKER}\n{xml_list}"})
        ephemeral: list[int] = []
        # (text, ephemeral) in tail order.
        per_turn: list[tuple[str, bool]] = [(text, True) for text in (notices or [])]
        if is_final:
            per_turn.append((_FINAL_TURN_WARNING, True))
        if previous_turn_silent:
            per_turn.append((REASONING_REMINDER, True))
        for text, is_ephemeral in per_turn:
            if is_ephemeral:
                ephemeral.append(len(blocks))
            blocks.append({"type": "text", "text": text})
        tail = HumanMessage(content=blocks)
        if ephemeral:
            mark_ephemeral(tail, ephemeral)
        return tail

    def _extract_response_text(self, response) -> str:
        """Extracts the natural-language thought text from the model response."""
        raw_text = response.content if isinstance(response.content, str) else ""
        if isinstance(response.content, list):
            raw_text = "".join(
                b.get("text", "") for b in response.content if isinstance(b, dict) and "text" in b
            )
        return raw_text

    def _extract_response_thinking(self, response) -> str:
        """Extracts the model's native thinking blocks (thought summaries), if any.

        Providers running with ``include_thoughts`` return them as ``thinking``
        content blocks next to the ``text`` blocks; they are recorded on the step
        as ``operator_native_thinking`` and never fed back as reply text.
        """
        if not isinstance(response.content, list):
            return ""
        parts = [
            str(b.get("thinking") or "")
            for b in response.content
            if isinstance(b, dict) and b.get("type") == "thinking"
        ]
        return "\n".join(p for p in parts if p.strip())

    def _token_usage_from_response(self, response) -> dict | None:
        """Extracts token usage metadata from the model response, if present."""
        step_token_usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            u = response.usage_metadata
            pr = u.get("input_tokens") or u.get("prompt_tokens") or 0
            co = u.get("output_tokens") or u.get("completion_tokens") or 0
            to = u.get("total_tokens") or (pr + co)
            if to > 0:
                step_token_usage = {
                    "prompt_tokens": int(pr),
                    "completion_tokens": int(co),
                    "total_tokens": int(to),
                }
        elif hasattr(response, "response_metadata") and isinstance(
            response.response_metadata, dict
        ):
            u = response.response_metadata.get("usage_metadata") or response.response_metadata.get(
                "token_usage"
            )
            if isinstance(u, dict):
                pr = (
                    u.get("input_tokens")
                    or u.get("prompt_tokens")
                    or u.get("prompt_token_count")
                    or 0
                )
                co = (
                    u.get("output_tokens")
                    or u.get("completion_tokens")
                    or u.get("candidates_token_count")
                    or 0
                )
                to = u.get("total_tokens") or u.get("total_token_count") or (pr + co)
                if to > 0:
                    step_token_usage = {
                        "prompt_tokens": int(pr),
                        "completion_tokens": int(co),
                        "total_tokens": int(to),
                    }
        return step_token_usage

    def _estimate_token_usage(self, messages: list[BaseMessage], raw_text: str) -> dict:
        """Approximates token usage from message sizes when metadata is absent."""
        calc_prompt_chars = 0
        calc_images = 0
        for msg in messages:
            c = getattr(msg, "content", "")
            if isinstance(c, str):
                calc_prompt_chars += len(c)
            elif isinstance(c, list):
                for block in c:
                    if isinstance(block, dict):
                        if block.get("type") == "image_url" or "image_url" in block:
                            calc_images += 1
                        else:
                            calc_prompt_chars += len(str(block.get("text", "")))
                    else:
                        calc_prompt_chars += len(str(block))
        prompt_tokens = (calc_prompt_chars // 4) + (calc_images * 258)
        completion_tokens = len(raw_text) // 4
        return {
            "prompt_tokens": max(1, prompt_tokens),
            "completion_tokens": max(1, completion_tokens),
            "total_tokens": max(1, prompt_tokens + completion_tokens),
        }

    def _resolve_token_usage(
        self, response, messages: list[BaseMessage], raw_text: str
    ) -> tuple[dict, bool]:
        """Token usage for the call and whether the provider measured it.

        Falls back to an estimate when the response carries no usage
        metadata; the flag lets the caller keep an estimate out of the
        ledger's chars-per-token calibration (an estimate is itself derived
        from character counts, so calibrating on it would be circular).
        """
        step_token_usage = self._token_usage_from_response(response)
        if step_token_usage and step_token_usage.get("total_tokens", 0) > 0:
            return step_token_usage, True
        return self._estimate_token_usage(messages, raw_text), False

    def _record_llm_trace(self, step_token_usage: dict, raw_text: str) -> None:
        """Records the llm_call trace for this turn in the DataEngine."""
        if self.ctx.data_engine:
            current_step_id = getattr(self.ctx.data_engine, "current_step_id", None)
            self.ctx.data_engine.record_trace(
                type="llm_call",
                name="FlashRunner",
                payload={"token_usage": step_token_usage, "response": raw_text},
                step_id=current_step_id,
                status="success",
            )

    def _resolve_tool_calls(self, response, raw_text: str) -> list:
        """Returns native tool calls, falling back to text parsing if absent."""
        tool_calls = response.tool_calls or []

        # Fallback text parsing if tool_calls not parsed natively
        if not tool_calls and "```json" in raw_text:
            parsed = parse_structured(raw_text)
            if isinstance(parsed, ParseFailure):
                logger.warning(
                    "FlashRunner response contained a JSON block that could"
                    f" not be parsed: {parsed.error}"
                )
            elif isinstance(parsed, dict) and "name" in parsed:
                tool_calls = [
                    {
                        "name": parsed["name"],
                        "args": parsed.get("args", {}),
                        "id": str(uuid.uuid4()),
                    }
                ]
        return tool_calls

    # ------------------------------------------------------------------
    # Per-tool-call helpers (act / record / report)
    # ------------------------------------------------------------------

    async def _capture_post_screenshot(
        self, exec_result, name: str, action_names, state: State | None = None
    ):
        """Returns the post-action screenshot, capturing a fallback if needed.

        When a device action produced no observation (a failed action, ...) the
        screen is observed through the recorded session, so the next tail
        carries the indexed UI list and a step number the model can cite.
        Nothing is captured for non-action tools.
        """
        post_img_bytes = exec_result.screenshot_bytes
        if post_img_bytes or name not in action_names or name == TERMINAL_TOOL:
            return post_img_bytes
        obs, screenshot_bytes = await self._observe(settle_ms=0)
        if obs is None:
            return post_img_bytes
        post_img_bytes = screenshot_bytes
        if not exec_result.ui_elements_text:
            exec_result.ui_elements_text = obs.elements_text
        if not exec_result.screenshot_path and obs.screenshot_path:
            exec_result.screenshot_path = obs.screenshot_path
        if state is not None:
            if obs.hierarchy_ok:
                state.indexed_points = [el["center"] for el in obs.elements]
                state.indexed_elements = obs.elements
            if obs.screenshot_path:
                state.latest_screenshot = obs.screenshot_path
        return post_img_bytes

    def _extract_normalized_coordinates(self, name: str, args: dict, resolved=None):
        """Extracts and enriches coordinate metadata for the recorded action.

        ``resolved`` is the normalized point the executor sent a point action
        to; it is the coordinate of record when the model addressed an element
        by index (the arguments then carry no point at all).
        """
        norm_coords = None
        norm_start = None
        norm_end = None
        if name in ("click", "tap", "long_press", "input_text") and (
            isinstance(resolved, (list, tuple)) and len(resolved) == 2
        ):
            return [int(resolved[0]), int(resolved[1])], None, None
        if name == "swipe":
            kind, target_val, _ = parse_swipe_parameters(args)
            if kind == "coords" and isinstance(target_val, list) and len(target_val) == 4:
                norm_coords = target_val
                norm_start = target_val[:2]
                norm_end = target_val[2:]
            elif kind == "direction" and isinstance(target_val, str):
                g_lower = target_val.lower()
                if "up" in g_lower:
                    norm_coords = [600, 700, 600, 300]
                elif "down" in g_lower:
                    norm_coords = [600, 300, 600, 700]
                elif "left" in g_lower:
                    norm_coords = [750, 500, 250, 500]
                elif "right" in g_lower:
                    norm_coords = [250, 500, 750, 500]
                if norm_coords:
                    norm_start = norm_coords[:2]
                    norm_end = norm_coords[2:]
        elif name in ("click", "tap", "long_press", "input_text"):
            target = args.get("target") or args.get("coordinates")
            if isinstance(target, (list, tuple)) and len(target) == 2:
                norm_coords = list(target)
            elif isinstance(target, str):
                nums = re.findall(r"-?\d+(?:\.\d+)?", target)
                if len(nums) == 2:
                    norm_coords = [int(float(nums[0])), int(float(nums[1]))]
        return norm_coords, norm_start, norm_end

    def _build_action_record(self, name: str, args: dict, exec_result) -> dict:
        """The action as the step record and the visual lens see it.

        Flash records the model's own 0–1000 coordinates verbatim (an index
        target records the point the executor resolved it to); the explicit
        space marker keeps every later normalization pass (agent-friendly
        steps, MCP inspector) a no-op on this record. The tool arguments ride
        along under ``args``, and the target semantics the executor validated
        (observed element fields for an index, the model's own
        ``target_description`` for a point) land top level in the shape Pro
        records.
        """
        metadata = getattr(exec_result, "metadata", None) or {}
        resolved = metadata.get("target_coordinates")
        norm_coords, norm_start, norm_end = self._extract_normalized_coordinates(
            name, args, resolved=resolved
        )
        given = args.get("target") or args.get("coordinates") or args.get("sequence")
        if isinstance(given, (int, float)) and not isinstance(given, bool):
            given = None  # An element index is not a coordinate.
        action_dict = {
            "action": name,
            "coordinates": given or norm_coords,
            COORDINATE_SPACE_KEY: COORDINATE_SPACE_NORMALIZED,
            "args": args,
        }
        if norm_coords:
            action_dict["normalized_coordinates"] = norm_coords
        if norm_start and norm_end:
            action_dict["normalized_start_coordinates"] = norm_start
            action_dict["normalized_end_coordinates"] = norm_end
        action_dict.update(metadata.get("target_semantics") or {})
        return action_dict

    def _record_action_step(
        self,
        name: str,
        args: dict,
        exec_result,
        raw_text: str,
        step_token_usage: dict,
        pre_screenshot_bytes,
        xml_list,
        post_img_bytes,
        native_text: str | None = None,
        action_dict: dict | None = None,
    ):
        """Records telemetry / step in DataEngine; returns the step id or None."""
        recorded_step_id = None
        engine = self.ctx.data_engine
        if engine is None:
            return None
        try:
            if engine.current_step_id is None:
                engine.allocate_step_id()

            if action_dict is None:
                action_dict = self._build_action_record(name, args, exec_result)

            succeeded = exec_result.status == "success"
            last_execution_result = {
                "status": "dispatched" if succeeded else "failed",
                "result": exec_result.text_summary,
            }
            if not succeeded:
                last_execution_result["error"] = exec_result.text_summary

            extra_metadata: dict = {"token_usage": step_token_usage}

            recorded_step_id = engine.record_step(
                pre_screenshot_bytes=pre_screenshot_bytes,
                post_screenshot_bytes=post_img_bytes,
                ui_tree=(exec_result.ui_elements_text or xml_list),
                action_taken=action_dict,
                operator_raw_thinking=raw_text,
                operator_native_thinking=native_text or None,
                last_execution_result=last_execution_result,
                extra_metadata=extra_metadata,
            )
        except Exception as step_err:
            logger.warning(f"Error recording step in FlashRunner: {step_err}")
        return recorded_step_id

    async def _execute_and_record_action(
        self,
        name: str,
        args: dict,
        tc_id: str,
        state: State,
        messages: list[BaseMessage],
        raw_text: str,
        step_token_usage: dict,
        pre_screenshot_bytes,
        xml_list,
        action_sequence: int,
        turn: _TurnRecord,
        native_text: str | None = None,
        index_elements: list[dict] | None = None,
    ):
        """Executes one tool call, records it, and updates loop state.

        The tool message carries the outcome text only; the post-action
        screenshot and UI list become the next turn's observation tail.
        ``index_elements`` is the turn's element snapshot index targets
        resolve against (see :meth:`_process_tool_calls`); ``None`` resolves
        against the state's current list. Returns the (possibly updated)
        pre_screenshot_bytes, xml_list, and action_sequence for the next
        iteration.
        """
        # Dynamic dispatch set: manifest device actions plus any backend
        # extension tools, so extension steps are recorded like actions.
        action_names = self.executor.action_tool_names
        try:
            exec_result = await self.executor.execute(
                name, args, tc_id, state, index_elements=index_elements
            )

            post_img_bytes = await self._capture_post_screenshot(
                exec_result, name, action_names, state
            )

            # One record shape for the DataEngine step and the visual lens.
            action_dict = (
                self._build_action_record(name, args, exec_result) if name in action_names else None
            )

            # Record telemetry / step in DataEngine
            recorded_step_id = None
            if self.ctx.data_engine and name in action_names:
                recorded_step_id = self._record_action_step(
                    name,
                    args,
                    exec_result,
                    raw_text,
                    step_token_usage,
                    pre_screenshot_bytes,
                    xml_list,
                    post_img_bytes,
                    native_text=native_text,
                    action_dict=action_dict,
                )

            if name in action_names:
                turn.step_keys.append(str(recorded_step_id) if recorded_step_id else str(tc_id))
                turn.actions.append((name, exec_result.status, exec_result.text_summary))

            if post_img_bytes:
                pre_screenshot_bytes = post_img_bytes
            if exec_result.ui_elements_text:
                xml_list = exec_result.ui_elements_text

            # Helper tools may return multimodal blocks (a step screenshot);
            # device actions always report text — their post screenshot is the
            # next observation tail, never a tool-message image. The image
            # carrier follows the model's provider (tool_result_messages).
            raw_blocks = exec_result.raw_result if name not in action_names else None
            content = (
                raw_blocks
                if isinstance(raw_blocks, list) and raw_blocks
                else exec_result.text_summary or f"Action '{name}' dispatched."
            )
            messages.extend(
                tool_result_messages(
                    tc_id, content, name=name, status=exec_result.status, llm=self._llm
                )
            )

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            if name in action_names:
                turn.step_keys.append(str(tc_id))
                turn.actions.append((name, "error", f"Error executing tool {name}: {e}"))
            messages.append(
                ToolMessage(
                    tool_call_id=tc_id,
                    name=name,
                    content=f"Error executing tool {name}: {e}",
                    status="error",
                )
            )
        return pre_screenshot_bytes, xml_list, action_sequence

    async def _invoke_model(self, llm, current_tools: list, messages: list[BaseMessage]):
        """Binds the active tools and invokes the model through the LLM gateway."""
        # Bind active tools
        bound_llm = llm.bind_tools(current_tools)

        # Invoke Model. Streaming, live-token UI deltas, classified
        # retries, and pause/resume are all owned by the LLM gateway
        # (acomplete); a typed LLMCallError propagates if it gives up.
        return await invoke_llm_with_timeout_message(
            acomplete(bound_llm, messages), timeout_seconds=10, hard_timeout=180
        )

    async def _process_tool_calls(
        self,
        tool_calls: list,
        state: State,
        messages: list[BaseMessage],
        raw_text: str,
        step_token_usage: dict,
        pre_screenshot_bytes,
        xml_list,
        action_sequence: int,
        turn: _TurnRecord,
        native_text: str | None = None,
    ):
        """Dispatches the turn's tool calls.

        Every index target of the turn resolves against the element list the
        model decided on: the list of the observation this turn was built
        from, snapshotted here before the first action. Each action still
        refreshes ``state.indexed_elements`` (that refreshed list is what the
        next observation shows), so without the snapshot ``click(5)`` after
        ``click(3)`` would be resolved against the screen after the first
        click.

        Returns (final_report, pre_screenshot_bytes, xml_list, action_sequence);
        final_report is non-None only once ``submit_verdict`` was accepted.
        """
        action_names = self.executor.action_tool_names
        index_elements = self._turn_index_snapshot(state)
        for tc in tool_calls:
            name = tc["name"].split(":")[-1] if ":" in tc["name"] else tc["name"]
            args = tc.get("args") or {}
            tc_id = tc.get("id") or str(uuid.uuid4())
            logger.info(f"Executing Flash tool: {name}({args})")

            elements_before = getattr(state, "indexed_elements", None)
            before_len = len(elements_before) if isinstance(elements_before, list) else 0
            pre_screenshot_bytes, xml_list, action_sequence = await self._execute_and_record_action(
                name,
                args,
                tc_id,
                state,
                messages,
                raw_text,
                step_token_usage,
                pre_screenshot_bytes,
                xml_list,
                action_sequence,
                turn,
                native_text=native_text,
                index_elements=index_elements,
            )
            if name not in action_names:
                index_elements = self._extend_index_snapshot(state, index_elements, before_len)
            if name == TERMINAL_TOOL:
                verdict = load_verdict(self.bench.run_dir)
                if verdict is not None:
                    return (
                        {
                            "status": "completed",
                            "explanation": "Verdict submitted.",
                            "verdict": verdict,
                        },
                        pre_screenshot_bytes,
                        xml_list,
                        action_sequence,
                    )
        return None, pre_screenshot_bytes, xml_list, action_sequence

    @staticmethod
    def _turn_index_snapshot(state: State) -> list[dict]:
        """The element list this turn's index targets resolve against.

        The state's list object itself, so in-place appends (explorer
        candidates) before any action join the snapshot; an empty list is
        installed on the state when there is none, for the same reason.
        """
        elements = getattr(state, "indexed_elements", None)
        if not isinstance(elements, list):
            elements = []
            try:
                state.indexed_elements = elements
            except (AttributeError, TypeError, ValueError):
                pass
        return elements

    @staticmethod
    def _extend_index_snapshot(state: State, snapshot: list[dict], before_len: int) -> list[dict]:
        """Re-takes the snapshot after a helper tool appended candidates to a
        list that is no longer the snapshot (an action replaced it first).

        Appends into the snapshot itself need nothing: the explorer numbered
        them against the snapshot. Only growth of a different list object
        moves the snapshot, since that is the list the new numbers refer to.
        """
        current = getattr(state, "indexed_elements", None)
        if not isinstance(current, list) or current is snapshot:
            return snapshot
        if len(current) > before_len:
            return current
        return snapshot

    async def _prepare_conversation(self, state: State, tools_declaration: list):
        """Installs the static prefix and captures the initial device state."""
        ledger = self._build_ledger()
        ledger.set_static_prefix(
            [SystemMessage(content=self._render_system_prompt(tools_declaration))]
        )

        # The first screen is a recorded step too, so it can be flagged.
        obs, img_bytes = await self._observe(settle_ms=400, state=state)
        return ledger, img_bytes, (obs.elements_text if obs else None)

    async def _observe(self, settle_ms: int, state: State | None = None):
        """Observes through the recorded bench session; ``(None, None)`` on failure."""
        session = self.ctx.action_session
        if session is None:
            logger.warning("FlashRunner has no bench session to observe through.")
            return None, None
        try:
            obs = await session.observe(settle_ms=settle_ms)
        except Exception as err:
            logger.warning(f"FlashRunner observation failed: {err}")
            return None, None
        if not obs.ok:
            logger.warning(f"FlashRunner observation failed: {obs.message}")
            return None, None
        image = None
        if obs.screenshot_path:
            try:
                image = Path(obs.screenshot_path).read_bytes()
            except OSError as err:
                logger.warning(f"Could not read observed screenshot: {err}")
        if state is not None:
            if obs.hierarchy_ok:
                state.indexed_points = [el["center"] for el in obs.elements]
                state.indexed_elements = obs.elements
            if obs.screenshot_path:
                state.latest_screenshot = obs.screenshot_path
        return obs, image

    def _current_step(self) -> int:
        """The step whose screen the model is looking at: the latest recorded step."""
        return len(load_steps(self.bench.run_dir))

    @staticmethod
    def _commit_turn(ledger: TranscriptLedger, turn: _TurnRecord | None) -> None:
        """Commits the previous turn once its step ids and outcomes are known."""
        if turn is None:
            return
        ledger.commit_staged(
            step_key=turn.step_keys[0] if turn.step_keys else None,
            validator_result=turn.result(),
            extra_step_keys=turn.step_keys[1:],
        )

    @trace(type="agent", name="FlashRunner")
    async def run(self, state: State) -> dict:
        limit = self.turn_limit
        logger.info(
            f"Starting Artemis Flash reactive loop for goal: {self.goal}"
            f" (turn limit: {limit if limit else 'unlimited'})"
        )

        # 1. Initialize Universal LLM via Service Layer
        llm = self._init_llm()
        self._llm = llm

        tools_declaration = self._get_tools()
        report_only_tools = [t for t in tools_declaration if t.name == TERMINAL_TOOL]

        ledger, img_bytes, xml_list = await self._prepare_conversation(state, tools_declaration)

        turns = 0
        action_sequence = 0
        final_report = None
        current_pre_screenshot_bytes = img_bytes
        current_xml_list = xml_list
        previous_turn: _TurnRecord | None = None
        pending_notices: list[str] = []

        while limit is None or turns < limit:
            turns += 1
            logger.info(f"--- Artemis Flash Turn {turns}{f'/{limit}' if limit else ''} ---")

            if self.ctx.data_engine:
                self.ctx.data_engine.allocate_step_id()

            # Commit the previous turn: its step ids and outcomes exist now.
            self._commit_turn(ledger, previous_turn)
            previous_turn = None

            # Tool restriction on the final turn (bounded loops only)
            is_final = limit is not None and turns == limit
            tail = self._build_tail(
                ledger,
                turns,
                current_pre_screenshot_bytes,
                current_xml_list,
                notices=pending_notices,
                is_final=is_final,
                # The ledger judged the turn it just committed: a bare tool
                # call (or thinking only) earns a one-line reminder, no bounce.
                previous_turn_silent=bool(getattr(ledger, "last_turn_silent", False)),
            )
            pending_notices = []

            # S + F + A + tail: chunk compression and the scrub edge advance here.
            messages = ledger.render([tail])
            turn_base = len(messages) - 1
            current_tools = report_only_tools if is_final else tools_declaration

            response = await self._invoke_model(llm, current_tools, messages)

            if response is None:
                break

            messages.append(response)

            # Extract thought and tool calls
            raw_text = self._extract_response_text(response)
            native_text = self._extract_response_thinking(response)

            # Extract token usage metadata from response
            step_token_usage, measured = self._resolve_token_usage(response, messages, raw_text)
            # The ledger's compaction thresholds read the runner's own prompt
            # size, never the session-wide meter (which any agent overwrites).
            # The prompt as sent (``messages`` minus the just-appended reply)
            # rides along so the ledger can calibrate its chars-per-token
            # ratio — only from a provider measurement, never from the
            # estimate (same as the Pro operator).
            ledger.record_prompt_tokens(
                step_token_usage.get("prompt_tokens"),
                messages=messages[:-1] if measured else None,
            )

            self._record_llm_trace(step_token_usage, raw_text)

            tool_calls = self._resolve_tool_calls(response, raw_text)

            if not tool_calls:
                logger.info(
                    f"FlashRunner received response without tool calls at turn {turns}:"
                    f" {raw_text[:100]}..."
                )
                if is_final:
                    final_report = {"status": "failed", "explanation": raw_text}
                    break
                pending_notices.append(_NO_TOOL_CALL_NOTICE)
                ledger.stage_turn(messages[turn_base:])
                previous_turn = _TurnRecord()
                continue

            # Process tool calls
            turn = _TurnRecord()
            (
                final_report_from_calls,
                current_pre_screenshot_bytes,
                current_xml_list,
                action_sequence,
            ) = await self._process_tool_calls(
                tool_calls,
                state,
                messages,
                raw_text,
                step_token_usage,
                current_pre_screenshot_bytes,
                current_xml_list,
                action_sequence,
                turn,
                native_text=native_text,
            )
            ledger.stage_turn(messages[turn_base:])
            previous_turn = turn
            if final_report_from_calls is not None:
                return final_report_from_calls

        if final_report is None:
            explanation = (
                "Max turns reached without a verdict."
                if limit is not None and turns >= limit
                else "The model returned no response; the reactive loop stopped."
            )
            final_report = {"status": "failed", "explanation": explanation}
        return final_report
