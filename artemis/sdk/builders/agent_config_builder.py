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

"""Builder for AgentConfig objects using a fluent interface."""

import os
from typing import Any, cast

from artemis.config import load_agent_config, settings
from artemis.context import DevicePlatform
from artemis.sdk.types.agent import AgentConfig, ServerConfig
from artemis.utils.video import detect_video_tools_enabled
from third_party.mobile_use.sdk.builders.agent_config_builder import AgentConfigBuilderBase


class AgentConfigBuilder(AgentConfigBuilderBase):
    """Artemis AgentConfig builder; see :class:`AgentConfigBuilderBase` for usage."""

    config_class = AgentConfig

    def __init__(self):
        """Initialize an empty AgentConfigBuilder with Artemis defaults."""
        super().__init__(servers=get_default_servers())
        self._video_recording_tools_enabled: bool = detect_video_tools_enabled()
        self._force_web_accessibility: bool = False
        self._concurrency_mode: str = "per_device"
        self._max_concurrency: int | None = None

        agent_cfg = load_agent_config()
        self._video_analyzer = agent_cfg.video_analyzer
        if agent_cfg.video_analyzer.enabled is not None:
            self._video_recording_tools_enabled = agent_cfg.video_analyzer.enabled
        else:
            self._video_recording_tools_enabled = detect_video_tools_enabled()
        self._flash = agent_cfg.flash

    def for_device_serial(self, device_serial: str) -> "AgentConfigBuilder":
        """Target a specific Android device by its ADB serial number."""
        return self.for_device(DevicePlatform.ANDROID, device_serial)

    def with_concurrency_mode(self, mode: str) -> "AgentConfigBuilder":
        """Configure concurrency mode: 'global' (1 task globally) or 'per_device' (1 task per device)."""
        self._concurrency_mode = str(mode).strip().lower()
        return self

    def with_max_concurrency(self, max_concurrency: int) -> "AgentConfigBuilder":
        """Configure max concurrent tasks limit."""
        self._max_concurrency = max_concurrency
        return self

    def with_video_recording_tools(self, enabled: bool = True) -> "AgentConfigBuilder":
        """Enable or disable video recording tools.

        Args:
            enabled: Whether to enable video recording tools
        """
        self._video_recording_tools_enabled = enabled
        return self

    def with_web_accessibility(self, enabled: bool = True) -> "AgentConfigBuilder":
        """Enable or disable forcing web accessibility for WebViews.

        Args:
            enabled: Whether to force web accessibility
        """
        self._force_web_accessibility = enabled
        return self

    def with_flash_config(self, max_turns: int | None = None) -> "AgentConfigBuilder":
        """Configure the Flash loop.

        Args:
            max_turns: Maximum reactive loop turns (0 = unlimited)
        """
        if max_turns is not None:
            self._flash = self._flash.model_copy(update={"max_turns": max_turns})
        return self

    def _extra_config_fields(self) -> dict[str, Any]:
        return {
            "device_id": (
                self._device_id
                or os.environ.get("ARTEMIS_DEVICE_ID")
                or os.environ.get("ADB_DEVICE_SERIAL")
            ),
            "video_recording_tools_enabled": self._video_recording_tools_enabled,
            "force_web_accessibility": self._force_web_accessibility,
            "flash": self._flash,
            "video_analyzer": self._video_analyzer,
            "concurrency_mode": self._concurrency_mode,
            "max_concurrency": self._max_concurrency,
        }

    def build(self, validate_profiles: bool = True) -> AgentConfig:
        return cast(AgentConfig, super().build(validate_profiles=validate_profiles))


def get_default_servers():

    host = settings.ADB_HOST or os.environ.get("ADB_HOST", "localhost")
    port_val = settings.ADB_PORT
    if not port_val:
        port_str = os.environ.get("ADB_PORT", "5037")
        port_val = int(port_str) if port_str.isdigit() else 5037

    return ServerConfig(
        adb_host=host,
        adb_port=port_val,
    )
