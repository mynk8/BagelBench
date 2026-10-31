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

"""Flash loop, transcript memory and screen-recording configuration."""

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from artemis.config.constants import AGENT_CONFIG_FILENAME
from artemis.config.paths import ROOT_DIR, get_config_path
from third_party.mobile_use.utils.file import load_jsonc
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class VideoAnalyzerConfig(BaseModel):
    """Session screen recording (``agent.video_analyzer``; the name is historical)."""

    enabled: bool | None = Field(
        default=None,
        description=(
            "Whether the session screen is recorded. If None, auto-detected from"
            " scrcpy and ffmpeg availability."
        ),
    )
    model_config = {"extra": "allow"}


class MemoryTranscriptConfig(BaseModel):
    """Scrub-edge options for the message transcript (agent.memory.transcript)."""

    prune_history_xml: bool = Field(
        default=True,
        description="Whether to prune outdated UI XML trees from historical turns.",
    )
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


class MemoryConfig(BaseModel):
    """Transcript memory configuration block (agent.memory)."""

    transcript: MemoryTranscriptConfig = Field(
        default_factory=MemoryTranscriptConfig,
        description="Transcript scrub-edge options.",
    )
    model_config = {"extra": "allow"}


class FlashProfileConfig(BaseModel):
    """Options for the Flash reference agent loop."""

    max_turns: int = Field(
        default=0,
        ge=0,
        description=(
            "Maximum reactive turns; 0 (the default) means unlimited. A benchmark run"
            " is bounded by its action budget and ends when the model submits a verdict."
        ),
    )
    model_config = {"extra": "allow"}


class AgentGlobalConfig(BaseModel):
    """Global configuration parsed from artemis.jsonc / agent_config.json."""

    flash: FlashProfileConfig = Field(
        default_factory=FlashProfileConfig,
        description="Options for the Flash reference agent loop.",
    )
    video_analyzer: VideoAnalyzerConfig = Field(
        default_factory=VideoAnalyzerConfig,
        description="Session screen recording options.",
    )
    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Transcript memory options.",
    )

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def apply_env_overrides(cls, data: Any) -> Any:
        """Apply the screen-recording environment override."""
        if not isinstance(data, dict):
            return data
        raw = os.getenv("ARTEMIS_VIDEO_RECORDING_ENABLED") or os.getenv(
            "ARTEMIS_WITH_VIDEO_RECORDING_TOOLS"
        )
        if raw is not None and raw.strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
            "0",
            "false",
            "no",
            "off",
        ):
            data.setdefault("video_analyzer", {})["enabled"] = raw.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        return data


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
            if isinstance(data, dict) and "agent" in data:
                return AgentGlobalConfig.model_validate(data["agent"])
            return AgentGlobalConfig.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to load agent config from '{resolved_path}': {e}")
        raise ValueError(f"Failed to parse '{resolved_path}': {e}") from e
