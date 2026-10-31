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

from typing import Literal

from artemis.config import (
    ExplorerConfig,
    FlashProfileConfig,
    VideoAnalyzerConfig,
)
from artemis.context import DevicePlatform
from artemis.utils.video import detect_video_tools_enabled
from third_party.mobile_use.sdk.types.agent import (
    AgentConfigBase,
    ApiBaseUrl,
    ServerConfig,
)
from third_party.mobile_use.sdk.types.task import AgentProfile
from pydantic import Field

__all__ = ["AgentConfig", "AgentProfile", "ApiBaseUrl", "DevicePlatform", "ServerConfig"]


class AgentConfig(AgentConfigBase):
    """ARTEMIS agent configuration.

    Adds the Checker, Outputter, Explorer, video-analysis and concurrency
    settings to :class:`AgentConfigBase`.
    """

    video_recording_tools_enabled: bool = Field(default_factory=detect_video_tools_enabled)
    force_web_accessibility: bool = False

    flash: FlashProfileConfig = Field(default_factory=FlashProfileConfig)
    explorer: ExplorerConfig = Field(default_factory=ExplorerConfig)
    # Advanced per-agent tier override; empty so the per-profile knobs
    # (``explorer.flash_mode`` / ``explorer.pro_mode``) decide by default.
    explorer_versions: dict[str, Literal["flash", "pro", "ultra"]] = Field(default_factory=dict)
    denylisted_tools: dict[str, list[str]] = Field(default_factory=dict)
    enable_video_ledger: bool = True
    video_analyzer: VideoAnalyzerConfig = Field(default_factory=VideoAnalyzerConfig)
    concurrency_mode: Literal["global", "per_device"] = "per_device"
    max_concurrency: int | None = None

    model_config = {"arbitrary_types_allowed": True}

    def get_explorer_version(
        self,
        explicit_version: str | None = None,
        agent_name: str | None = "operator",
        profile: str | None = None,
    ) -> Literal["flash", "pro", "ultra"]:
        """Resolves active Explorer version using underlying ExplorerConfig and role overrides."""
        return self.explorer.resolve(
            explicit_version=explicit_version,
            agent_name=agent_name,
            profile=profile,
            per_agent_overrides=self.explorer_versions,
        )
