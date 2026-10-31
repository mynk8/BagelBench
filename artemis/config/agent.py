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

"""Agent tools, sub-agent capabilities, and explorer settings configuration."""

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from artemis.config.constants import (
    AGENT_CONFIG_FILENAME,
    DEFAULT_EXPLORER_VERSION,
    ExplorerVersion,
)
from artemis.config.paths import ROOT_DIR, get_config_path
from artemis.llm.google import VideoProcessing
from third_party.mobile_use.utils.file import load_jsonc
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class VideoAnalyzerConfig(BaseModel):
    """Configuration specific to VideoAnalyzer and screen recording."""

    enabled: bool | None = Field(
        default=None,
        description=(
            "Whether continuous screen video recording and video analyzer tools "
            "are enabled. If None, auto-detected based on scrcpy & ffmpeg availability."
        ),
    )
    enable_ledger: bool = Field(
        default=True,
        description="Whether to enable video action ledger state tracking.",
    )
    chunk_size_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        description="Maximum duration of an initial video-analysis chunk.",
    )
    min_chunk_seconds: float = Field(
        default=4.0,
        ge=1.0,
        le=30.0,
        description="Smallest chunk produced by failure-driven bisection.",
    )
    max_split_depth: int = Field(
        default=4,
        ge=0,
        le=8,
        description="Maximum recursive chunk bisection depth after failures.",
    )
    circuit_breaker_threshold: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Consecutive transient model failures before opening the circuit.",
    )
    circuit_breaker_cooldown_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=900.0,
        description="How long an unhealthy video model remains bypassed.",
    )
    action_window_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=10.0,
        description="Dense-perception window on each side of a recorded mobile action.",
    )
    dense_action_fps: float = Field(
        default=4.0,
        ge=1.0,
        le=15.0,
        description="Frame sampling rate around recorded mobile actions.",
    )
    max_dense_action_frames: int = Field(
        default=24,
        ge=0,
        le=120,
        description="Maximum additional action-proximal keyframes per chunk.",
    )
    native_max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        description=(
            "Retries against the native video provider before switching to the "
            "configured universal fallback. A value of 1 means two total attempts."
        ),
    )
    model_call_timeout_seconds: float = Field(
        default=120.0,
        ge=15.0,
        le=600.0,
        description="Hard timeout for one native or universal video-model response.",
    )
    processing: VideoProcessing = Field(
        default="auto",
        description=(
            "How Gemini sub-agents watch a clip. 'agentic' lets the model search,"
            " scan and re-watch the clip on demand (Gemini Interactions API);"
            " 'static' samples it at a fixed frame rate; 'auto' picks agentic on"
            " Gemini 3.6+ Flash models and static everywhere else."
        ),
    )
    agentic_chunk_size_seconds: float = Field(
        default=600.0,
        ge=30.0,
        le=1800.0,
        description=(
            "Maximum clip length handed to one agentic sub-agent. Static mode keeps"
            " using chunk_size_seconds."
        ),
    )
    agentic_call_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        le=1200.0,
        description="Hard timeout for one agentic sub-agent response.",
    )
    model_config = {"extra": "allow"}


class ExplorerConfig(BaseModel):
    """Configuration specific to UI Explorer visual sub-agent (Flash / Pro / Ultra)."""

    default_version: ExplorerVersion = Field(
        default=DEFAULT_EXPLORER_VERSION,
        description="Default Explorer version mode ('flash', 'pro', or 'ultra').",
    )
    flash_mode: ExplorerVersion = Field(
        default="flash",
        description="Explorer version mode when main system runs under Flash profile (FlashRunner).",
    )
    pro_mode: ExplorerVersion = Field(
        default="flash",
        description="Explorer version mode when main system runs under Pro profile (Graph / Operator / Validator).",
    )
    caching: bool | None = Field(
        default=None,
        description=(
            "Gemini explicit context caching for multi-turn Explorer tiers. ``None``"
            " (default) uses the tier's own default: off for pro, on for ultra."
        ),
    )
    model_config = {"extra": "allow"}

    def resolve(
        self,
        explicit_version: str | None = None,
        agent_name: str | None = None,
        profile: str | None = None,
        per_agent_overrides: dict[str, str] | None = None,
    ) -> ExplorerVersion:
        """Resolves active Explorer version with clean precedence rules."""
        if explicit_version:
            v = str(explicit_version).strip().lower()
            if v in ("flash", "pro", "ultra"):
                return v  # type: ignore

        env_v = os.getenv("ARTEMIS_EXPLORER_VERSION", "").strip().lower()
        if env_v in ("flash", "pro", "ultra"):
            return env_v  # type: ignore

        if per_agent_overrides and agent_name and agent_name in per_agent_overrides:
            v = str(per_agent_overrides[agent_name]).strip().lower()
            if v in ("flash", "pro", "ultra"):
                return v  # type: ignore

        if profile in ("flash", "flash_runner") or agent_name in ("flash", "flash_runner"):
            return self.flash_mode
        if profile in ("pro", "operator", "validator") or agent_name in (
            "pro",
            "operator",
            "validator",
        ):
            return self.pro_mode

        return self.default_version


class StepSummarizerConfig(BaseModel):
    """Configuration specific to Flash asynchronous step visual summarization."""

    enabled: bool = Field(
        default=True,
        description="Whether to asynchronously summarize historical steps to replace pruned images.",
    )
    model: str = Field(
        default="gemini-2.5-flash-lite",
        description="Lightweight model used for background step state summarization.",
    )
    prune_history_xml: bool = Field(
        default=True,
        description="Whether to prune outdated heavy UI XML trees from historical turns.",
    )
    retry_limit: int = Field(
        default=3,
        ge=0,
        description=(
            "Maximum retries per step summary after the first attempt; on"
            " exhaustion the step is marked summary_status=failed instead of"
            " retrying forever."
        ),
    )
    model_config = {"extra": "allow"}


class MemoryRuntimeConfig(BaseModel):
    """Scheduling options for the shared step-memory runtime (agent.memory.runtime)."""

    max_concurrency: int = Field(
        default=2,
        ge=1,
        le=16,
        description=(
            "Maximum background summary attempts running concurrently."
            " Default 2 per the 2026-09-01 on-device baseline"
            " (history-baseline-2026-09-01.md §6): the serial queue at 1 pushed"
            " summary-ready P90 past the scrub-edge grace window; lens calls"
            " are independent lightweight-model requests, so 2 is low-risk."
        ),
    )
    retry_limit: int = Field(
        default=3,
        ge=0,
        description=(
            "Maximum retries per summary job after the first attempt; on"
            " exhaustion the job enters an explicit failed state."
        ),
    )
    flush_timeout_s: float = Field(
        default=30.0,
        gt=0,
        description="Upper bound in seconds for draining in-flight summary jobs at shutdown.",
    )
    model_config = {"extra": "allow"}


class MemoryTranscriptConfig(BaseModel):
    """Scrub-edge options for the message transcript (agent.memory.transcript)."""

    enabled: bool = Field(
        default=True,
        description=(
            "Whether the Pro operator builds its prompt from the session"
            " transcript ledger (S/F/A regions + per-turn tail) instead of the"
            " legacy per-turn 2-message rebuild. On by default since M5"
            " (2026-09-01, per the on-device A/B in"
            " history-baseline-2026-09-01.md); this is also the rollback"
            " switch — setting it to false restores the legacy path"
            " byte-for-byte, and L2/L3 chunk compression rides the same flag."
        ),
    )
    image_scrub_depth: int = Field(
        default=3,
        ge=1,
        description=(
            "Depth K of the screenshot scrub edge from the start gate up: the"
            " K-th most recent screenshot (the live one counts as depth 1) is"
            " replaced by its visual summary."
        ),
    )
    image_scrub_depth_relaxed: int = Field(
        default=6,
        ge=1,
        description=(
            "Screenshot scrub depth while the operator's measured context is"
            " below budget*start_ratio (nothing is being replaced yet, so"
            " more raw screenshots stay in view). Must be >= image_scrub_depth;"
            " set equal to it to disable the occupancy-driven depth. A change"
            " of depth never rewrites an already-scrubbed message."
        ),
    )
    pending_grace_steps: int = Field(
        default=3,
        ge=0,
        description=(
            "Extra image-depths a step may retain its screenshot past the"
            " scrub edge while its summary is still pending; afterwards the"
            " image is replaced by a placeholder referencing the DataEngine step."
        ),
    )
    xml_scrub_depth: int | None = Field(
        default=1,
        ge=1,
        description=(
            "Text edge of the scrub: once a message is deeper than this many"
            " image-bearing observations (1 = as soon as a newer observation"
            " exists) its UI element list, plan recitation and per-turn"
            " ephemeral blocks are removed. Kept shallow on purpose: only the"
            " live observation carries an indexed element list, so a stale"
            " [n] index can never be picked up as a target. Screenshots follow"
            " image_scrub_depth / image_scrub_depth_relaxed."
        ),
    )
    context_budget_tokens: int = Field(
        default=80000,
        ge=1024,
        description=(
            "Measured-token budget for the transcript context (provisional"
            " default pending the on-device baseline; §3.4). The soft/hard"
            " ratios below are applied against this budget."
        ),
    )
    start_ratio: float = Field(
        default=0.35,
        ge=0.0,
        lt=1.0,
        description=(
            "Start gate: below budget*start_ratio of the operator's measured"
            " prompt size, closed segments only prepare their capsule in the"
            " background — the original turns stay in the transcript. Ready"
            " chunks replace their turns once the measured context reaches"
            " this ratio (the hard threshold overrides it). 0 restores"
            " swap-as-soon-as-ready."
        ),
    )
    soft_ratio: float = Field(
        default=0.7,
        gt=0.0,
        lt=1.0,
        description=(
            "Soft threshold: when the operator's last measured prompt size"
            " reaches budget*soft_ratio, the oldest open segment is"
            " chunk-compressed (L2)."
        ),
    )
    hard_ratio: float = Field(
        default=0.9,
        gt=0.0,
        le=1.0,
        description=(
            "Hard threshold: when the operator's last measured prompt size"
            " reaches budget*hard_ratio, ready chunks swap as L2 blocks first;"
            " only if that would not bring the estimated context back under the"
            " line does everything closed force-swap (pending chunks included)"
            " and the whole frozen region fold into a recall-only era — L3: the"
            " period paragraph with the per-step index. The fold is permanent;"
            " later L2 chunks are appended after it."
        ),
    )
    min_active_steps: int = Field(
        default=5,
        ge=1,
        description=(
            "Sliding-window floor: no compression trigger may shrink the"
            " active region below this many most-recent raw turns."
        ),
    )
    similarity_hint: bool = Field(
        default=True,
        description=(
            "Whether the operator prompt injects a local historical-state hint"
            " when the current screen's perceptual hash closely matches a much"
            " older step's post-action screen (no model call, no historical"
            " image). Silent when the match is within the recent 3 steps —"
            " that regime belongs to the pixel-level same-screen note."
        ),
    )
    similarity_max_distance: int = Field(
        default=5,
        ge=0,
        le=64,
        description=(
            "Maximum Hamming distance between 64-bit dHash values for the"
            " historical-state hint to fire. Calibrated 2026-09-01 from 460"
            " dHash-stamped on-device steps (16 sessions): same-screen"
            " re-captures cluster at distance <=4, genuinely different screens"
            " mass at >=7 (valley at 5-6); cross-app pairs (guaranteed"
            " different screens) score <=5 in only 0.14% of cases vs 0.24% at"
            " the previous provisional 8."
        ),
    )
    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _ratios_are_ordered(self) -> "MemoryTranscriptConfig":
        """The three thresholds form a ladder against the same budget."""
        if not (0.0 <= self.start_ratio <= self.soft_ratio <= self.hard_ratio <= 1.0):
            raise ValueError(
                "memory.transcript ratios must satisfy"
                " 0 <= start_ratio <= soft_ratio <= hard_ratio <= 1"
                f" (got start_ratio={self.start_ratio}, soft_ratio={self.soft_ratio},"
                f" hard_ratio={self.hard_ratio})."
            )
        if self.image_scrub_depth_relaxed < self.image_scrub_depth:
            raise ValueError(
                "memory.transcript.image_scrub_depth_relaxed must be >= image_scrub_depth"
                f" (got {self.image_scrub_depth_relaxed} < {self.image_scrub_depth})."
            )
        return self


class MemoryRecallConfig(BaseModel):
    """search_history tool options (agent.memory.recall)."""

    enabled: bool = Field(
        default=True,
        description=(
            "Whether the operator (Pro and Flash) gets the search_history tool"
            " for deterministic lookups into cold (compressed/evicted) history."
            " replay_steps and get_step_screenshot are not gated by this flag."
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Upper bound on results per search_history call.",
    )
    max_text_tokens: int = Field(
        default=2000,
        ge=128,
        description=(
            "Estimated-token cap (char/4) on one search_history response;"
            " excerpts are truncated to fit."
        ),
    )
    screen_scan_steps: int = Field(
        default=150,
        ge=0,
        description=(
            "How many most-recent steps have their screenshot OCR/UI-tree text"
            " scanned by search_history (per-image JSON loads are the expensive"
            " part of the sweep). Narrow with step_range to reach older steps."
        ),
    )
    model_config = {"extra": "allow"}


class MemoryReplayConfig(BaseModel):
    """replay_steps tool options (agent.memory.replay)."""

    max_steps: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum steps replayed per replay_steps call.",
    )
    max_tokens: int = Field(
        default=12000,
        ge=128,
        description=(
            "Estimated-token budget (char/4) of one replay_steps response."
            " When exceeded, whole trailing steps are dropped; individual"
            " steps are kept intact."
        ),
    )
    model_config = {"extra": "allow"}


class MemoryChunkingConfig(BaseModel):
    """Segment (L2) chunk compression options (agent.memory.chunking)."""

    max_steps: int = Field(
        default=12,
        ge=1,
        description=(
            "Size-threshold trigger: an open segment of this many steps is"
            " chunk-compressed even without a milestone switch. Also the"
            " maximum steps per chunk when a longer segment is split."
        ),
    )
    target_source_tokens: int = Field(
        default=2000,
        ge=128,
        description=(
            "Size-threshold trigger: estimated source tokens (transcript"
            " characters through the session-calibrated ratio, 4 chars/token"
            " by default) over the open segment's eligible portion that force"
            " a chunk compression."
        ),
    )
    min_steps: int = Field(
        default=3,
        ge=1,
        description=(
            "Minimum turns in a chunk closed by the size or pressure trigger:"
            " below this the eligible turns keep accumulating instead of"
            " becoming one-step chunks (each chunk costs a capsule call)."
            " Milestone closes are exempt (a complete segment is a unit) and"
            " the hard threshold waives it (emergency)."
        ),
    )
    model: str = Field(
        default="gemini-3.8-flash",
        description="Model used for the chunk-level StepCapsuleLens (bands ①+②).",
    )
    max_chunks: int = Field(
        default=8,
        ge=1,
        description=(
            "Maximum full three-band chunk blocks kept in the frozen region;"
            " older chunks merge into eras (headers set-merged, ledgers kept)."
        ),
    )
    max_eras: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Maximum eras kept with their per-segment ledgers; older eras"
            " collapse their ledgers to search_history marker lines. None"
            " (default) follows max_chunks, preserving the pre-M5 equal-value"
            " behavior."
        ),
    )

    @model_validator(mode="after")
    def _min_steps_within_cap(self) -> "MemoryChunkingConfig":
        if self.min_steps > self.max_steps:
            raise ValueError(
                "memory.chunking.min_steps must not exceed max_steps"
                f" (got min_steps={self.min_steps}, max_steps={self.max_steps})."
            )
        return self

    model_config = {"extra": "allow"}


class MemoryConfig(BaseModel):
    """Unified step-memory configuration block (agent.memory)."""

    runtime: MemoryRuntimeConfig = Field(
        default_factory=MemoryRuntimeConfig,
        description="Shared background summarization runtime scheduling options.",
    )
    transcript: MemoryTranscriptConfig = Field(
        default_factory=MemoryTranscriptConfig,
        description="Transcript scrub-edge options.",
    )
    chunking: MemoryChunkingConfig = Field(
        default_factory=MemoryChunkingConfig,
        description="Segment chunk (L2) compression options.",
    )
    recall: MemoryRecallConfig = Field(
        default_factory=MemoryRecallConfig,
        description="search_history tool options.",
    )
    replay: MemoryReplayConfig = Field(
        default_factory=MemoryReplayConfig,
        description="replay_steps tool options.",
    )
    policies: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-agent overrides of the compiled-history ContextPolicy table"
            " (artemis.memory.context_policy); keys are agent names, values"
            " are policy field overrides (e.g. {'planner': {'last_n_detailed': 3}})."
        ),
    )
    model_config = {"extra": "allow"}


class FlashProfileConfig(BaseModel):
    """Configuration options specific to the ⚡ Flash execution profile (FlashRunner/ReactiveRunner)."""

    max_turns: int = Field(
        default=0,
        ge=0,
        description=(
            "Maximum reactive turns for Flash execution; 0 (the default) means"
            " unlimited. Context growth is bounded by the transcript ledger's"
            " scrub edge and chunk compression, not by a turn cap, so a long"
            " task simply runs until it reports its status."
        ),
    )
    explorer_mode: ExplorerVersion = Field(
        default="flash",
        description="Perception mode for Flash runner ('flash' for 1-shot detection).",
    )
    step_summarizer: StepSummarizerConfig = Field(
        default_factory=StepSummarizerConfig,
        description="Asynchronous visual context compressor settings.",
    )
    model_config = {"extra": "allow"}


class AgentGlobalConfig(BaseModel):
    """Global configuration parsed from artemis.jsonc / agent_config.json."""

    # ⚡ Profile-categorized configurations
    flash: FlashProfileConfig = Field(
        default_factory=FlashProfileConfig,
        description="Options for ⚡ Flash reactive runner execution.",
    )

    # 🌐 Core Component Configurations
    explorer: ExplorerConfig = Field(
        default_factory=ExplorerConfig,
        description="UI Explorer sub-agent runtime options.",
    )
    explorer_versions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Advanced per-agent override of the Explorer tier (e.g."
            ' {"validator": "ultra"}). Empty by default so that'
            " ``explorer.flash_mode`` / ``explorer.pro_mode`` decide."
        ),
    )
    denylisted_tools: dict[str, list[str]] = Field(
        default_factory=dict,
        description="List of denylisted tools per agent.",
    )
    video_analyzer: VideoAnalyzerConfig = Field(
        default_factory=VideoAnalyzerConfig,
        description="Video analyzer runtime options.",
    )
    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Unified step-memory runtime and transcript scrub options.",
    )

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def apply_legacy_keys_and_env(cls, data: Any) -> Any:
        """Map legacy ``flash`` keys onto their components and apply env overrides."""
        if not isinstance(data, dict):
            return data

        # ``flash.explorer_mode`` seeds ``explorer.flash_mode`` when that is unset.
        flash_block = data.get("flash")
        if isinstance(flash_block, dict) and "explorer_mode" in flash_block:
            explorer_block = data.setdefault("explorer", {})
            if isinstance(explorer_block, dict):
                explorer_block.setdefault("flash_mode", flash_block["explorer_mode"])

        # Legacy alias: an explicit flash.step_summarizer.retry_limit keeps
        # working by seeding memory.runtime.retry_limit when the new key is
        # absent (an explicit new key wins over the legacy one).
        flash_ss = flash_block.get("step_summarizer") if isinstance(flash_block, dict) else None
        if isinstance(flash_ss, dict) and "retry_limit" in flash_ss:
            mem_block = data.setdefault("memory", {})
            if isinstance(mem_block, dict):
                runtime_block = mem_block.setdefault("runtime", {})
                if isinstance(runtime_block, dict):
                    runtime_block.setdefault("retry_limit", flash_ss["retry_limit"])

        def _parse_bool(var_name: str) -> bool | None:
            v = os.getenv(var_name)
            if v is None:
                return None
            v_clean = v.strip().lower()
            if v_clean in ("1", "true", "yes", "on"):
                return True
            if v_clean in ("0", "false", "no", "off"):
                return False
            return None

        vid_rec_env = _parse_bool("ARTEMIS_VIDEO_RECORDING_ENABLED") or _parse_bool(
            "ARTEMIS_WITH_VIDEO_RECORDING_TOOLS"
        )
        if vid_rec_env is not None:
            data.setdefault("video_analyzer", {})["enabled"] = vid_rec_env

        vid_env = _parse_bool("ARTEMIS_VIDEO_LEDGER_ENABLED")
        if vid_env is not None:
            data.setdefault("video_analyzer", {})["enable_ledger"] = vid_env

        return data

    def get_explorer_version(
        self,
        explicit_version: str | None = None,
        agent_name: str | None = "operator",
        profile: str | None = None,
    ) -> ExplorerVersion:
        """Resolve Explorer version from this configuration."""
        return self.explorer.resolve(
            explicit_version=explicit_version,
            agent_name=agent_name,
            profile=profile,
            per_agent_overrides=self.explorer_versions,
        )


def resolve_explorer_version(
    ctx: Any | None = None,
    explicit_version: str | None = None,
    agent_or_profile_name: str | None = "operator",
) -> ExplorerVersion:
    """Resolves the active Explorer tier for a calling agent or profile.

    Precedence: explicit argument, ``ARTEMIS_EXPLORER_VERSION`` environment
    override, then the user's agent configuration (per-agent override, profile
    mode, default version) found on ``ctx.agent_config`` or, failing that, on
    ``ctx.execution_setup``.  The tier is a user setting: calling agents never
    pass it themselves.
    """
    for source in (
        getattr(ctx, "agent_config", None),
        getattr(ctx, "execution_setup", None),
    ):
        explorer_cfg = getattr(source, "explorer", None)
        if explorer_cfg is not None and hasattr(explorer_cfg, "resolve"):
            return explorer_cfg.resolve(
                explicit_version=explicit_version,
                agent_name=agent_or_profile_name,
                per_agent_overrides=getattr(source, "explorer_versions", None),
            )

    return ExplorerConfig().resolve(
        explicit_version=explicit_version, agent_name=agent_or_profile_name
    )


def load_agent_config(
    config_path: Path | None = None,
) -> AgentGlobalConfig:
    """Load and validate AgentGlobalConfig from artemis.jsonc or agent_config.json.

    Args:
        config_path: Optional explicit file path to configuration file.

    Returns:
        Validated AgentGlobalConfig instance.
    """
    resolved_path = config_path
    if not resolved_path:
        for candidate in ("artemis.jsonc", "artemis.json", AGENT_CONFIG_FILENAME):
            try:
                resolved_path = get_config_path(candidate)
                break
            except FileNotFoundError:
                continue

    if not resolved_path:
        resolved_path = get_config_path(AGENT_CONFIG_FILENAME, ROOT_DIR / AGENT_CONFIG_FILENAME)

    try:
        with open(resolved_path, encoding="utf-8") as f:
            data = load_jsonc(f)
            if os.environ.get("ARTEMIS_MODEL_PROVIDER") == "codex" and isinstance(data, dict):
                agent = data.get("agent", data)
                agent.setdefault("explorer", {}).update(flash_mode="pro", pro_mode="pro")
                agent.setdefault("flash", {})["explorer_mode"] = "pro"
                agent.setdefault("pro", {}).setdefault("explorer", {})["mode"] = "pro"
            if isinstance(data, dict) and "agent" in data:
                return AgentGlobalConfig.model_validate(data["agent"])
            return AgentGlobalConfig.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to load agent config from '{resolved_path}': {e}")
        raise ValueError(f"Failed to parse '{resolved_path}': {e}") from e
