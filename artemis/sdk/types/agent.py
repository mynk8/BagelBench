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

    Adds the screen-recording and concurrency
    settings to :class:`AgentConfigBase`.
    """

    video_recording_tools_enabled: bool = Field(default_factory=detect_video_tools_enabled)
    force_web_accessibility: bool = False

    flash: FlashProfileConfig = Field(default_factory=FlashProfileConfig)
    video_analyzer: VideoAnalyzerConfig = Field(default_factory=VideoAnalyzerConfig)
    concurrency_mode: Literal["global", "per_device"] = "per_device"
    max_concurrency: int | None = None

    model_config = {"arbitrary_types_allowed": True}
