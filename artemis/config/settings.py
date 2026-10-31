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

"""Application settings and environment variable configuration management."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings

from artemis.config.constants import (
    DEFAULT_ADB_HOST,
    DEFAULT_ADB_PORT,
    DEFAULT_MODEL,
    DEFAULT_PROFILE,
    ENV_DATA_ENGINE_DB_PATH,
)
from artemis.config.paths import (
    GLOBAL_APP_DIR,
    get_data_engine_db_path,
    get_default_traces_path,
    get_env_file,
    get_temp_dir,
)
from third_party.mobile_use.utils.logger import get_logger

# Installed wheels load .env from the user directory, outside site-packages.
_canonical_env = get_env_file()
load_dotenv(dotenv_path=_canonical_env, verbose=True)
_global_env = GLOBAL_APP_DIR / ".env"
if _global_env.exists() and _global_env.resolve() != _canonical_env.resolve():
    load_dotenv(dotenv_path=_global_env, verbose=True)

logger = get_logger(__name__)


def is_placeholder_key(val: str | SecretStr | None) -> bool:
    """Check if an API credential is empty or an unconfigured placeholder value."""
    if val is None:
        return True
    raw_str = val.get_secret_value() if isinstance(val, SecretStr) else str(val)
    raw_str = raw_str.strip().lower()
    if not raw_str:
        return True
    if raw_str in (
        "api_key",
        "your_api_key",
        "your_api_key_here",
        "your_gemini_api_key_here",
        "your_google_cloud_vision_api_key_here",
        "your_openai_api_key_here",
        "your_anthropic_api_key_here",
        "your_openrouter_api_key_here",
        "your_xai_api_key_here",
        "none",
        "empty",
        "null",
        "undefined",
    ):
        return True
    if (
        (raw_str.startswith("your_") and raw_str.endswith("_here"))
        or (raw_str.startswith("<") and raw_str.endswith(">"))
        or (raw_str.startswith("[") and raw_str.endswith("]"))
    ):
        return True
    return False


class Settings(BaseSettings):
    """Centralized ARTEMIS runtime settings loaded from environment and .env files."""

    # LLM Provider Authentication
    OPENAI_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    GOOGLE_API_KEY: SecretStr | None = None
    GEMINI_API_KEY: SecretStr | None = None
    GCP_API_KEY: SecretStr | None = None
    ANTHROPIC_API_KEY: SecretStr | None = None
    XAI_API_KEY: SecretStr | None = None
    OPEN_ROUTER_API_KEY: SecretStr | None = None

    # Google Cloud Vision OCR Authentication
    OCR_API_KEY: SecretStr | None = None
    VISION_API_KEY: SecretStr | None = None
    API_KEY: SecretStr | None = None

    # Custom Provider Endpoints
    OPENAI_BASE_URL: str | None = None

    # Android ADB Connectivity
    ADB_HOST: str | None = Field(default=DEFAULT_ADB_HOST)
    ADB_PORT: int | None = Field(default=DEFAULT_ADB_PORT)
    ADB_DEVICE_SERIAL: str | None = None
    # UI hierarchy backend: "auto" = Accessibility Helper with UIAutomator2
    # fallback, "helper" = helper only, "uiautomator" = UIAutomator2 only.
    ARTEMIS_HIERARCHY_BACKEND: str = Field(default="auto")
    # Whether a task may install / upgrade the Accessibility Helper APK on a device
    # it holds. False = only attach to a helper installed by `artemis helper install`.
    ARTEMIS_HELPER_AUTO_INSTALL: bool = Field(default=True)

    # Execution Defaults
    PROJECT_NAME: str | None = None
    ARTEMIS_DEFAULT_PROFILE: str = Field(default=DEFAULT_PROFILE)
    ARTEMIS_DEFAULT_MODEL: str = Field(default=DEFAULT_MODEL)

    # Explorer Tool Settings (the tier itself is configured in artemis.jsonc or
    # via ARTEMIS_EXPLORER_VERSION; see artemis.config.agent.ExplorerConfig)
    EXPLORER_CACHING: bool | None = Field(
        default=None,
        description=(
            "Environment-level override for Explorer context caching; unset"
            " defers to the agent configuration and the tier default."
        ),
    )

    # LLM Reliability
    LLM_PAUSE_TIMEOUT_SECONDS: float = Field(
        default=900.0,
        description=(
            "How long a task waits in the paused state after exhausting LLM"
            " retries before failing with LLMExhaustedError. <= 0 waits"
            " forever (legacy interactive behavior)."
        ),
    )

    # Paths & Storage
    TRACES_PATH: Path = Field(default_factory=get_default_traces_path)
    DATA_ENGINE_DB_PATH: Path = Field(default_factory=get_data_engine_db_path)
    TEMP_PATH: Path = Field(default_factory=get_temp_dir)

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def fallback_api_keys(self) -> "Settings":
        """Normalize Google / Gemini / GCP and OCR API keys and filter placeholders."""
        # Sanitize any placeholder values loaded from environment or .env
        for attr in (
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "GCP_API_KEY",
            "ANTHROPIC_API_KEY",
            "XAI_API_KEY",
            "OPEN_ROUTER_API_KEY",
            "OCR_API_KEY",
            "VISION_API_KEY",
            "API_KEY",
        ):
            val = getattr(self, attr, None)
            if val and is_placeholder_key(val):
                setattr(self, attr, None)

        if not self.GOOGLE_API_KEY:
            if self.GEMINI_API_KEY:
                self.GOOGLE_API_KEY = self.GEMINI_API_KEY
            elif self.GCP_API_KEY:
                self.GOOGLE_API_KEY = self.GCP_API_KEY

        # Fallback for OCR & Vision API keys
        if not self.OCR_API_KEY and self.VISION_API_KEY:
            self.OCR_API_KEY = self.VISION_API_KEY
        return self

    def get_api_key(self, provider: str) -> SecretStr | None:
        """Get API key for a specified provider.

        Args:
            provider: Provider name (e.g., 'google', 'gemini', 'openai', 'ocr', 'vision').

        Returns:
            SecretStr containing the API key or None if not configured.
        """
        from artemis.llm.google.provider import is_google_family_provider

        provider_lower = provider.lower()
        key: SecretStr | None = None
        if is_google_family_provider(provider_lower):
            key = self.GOOGLE_API_KEY or self.GEMINI_API_KEY or self.GCP_API_KEY
        elif provider_lower in ("ocr", "vision", "google_vision"):
            key = self.OCR_API_KEY or self.VISION_API_KEY
        elif provider_lower == "openai":
            key = self.OPENAI_API_KEY
        elif provider_lower == "deepseek":
            key = self.DEEPSEEK_API_KEY
        elif provider_lower in ("anthropic", "claude"):
            key = self.ANTHROPIC_API_KEY
        elif provider_lower == "openrouter":
            key = self.OPEN_ROUTER_API_KEY
        elif provider_lower in ("xai", "grok"):
            key = self.XAI_API_KEY

        if key and not is_placeholder_key(key):
            return key
        return None


# Singleton instance
settings = Settings()

# Synchronize DATA_ENGINE_DB_PATH in environment for external sub-processes/tools
if settings.DATA_ENGINE_DB_PATH:
    os.environ[ENV_DATA_ENGINE_DB_PATH] = str(settings.DATA_ENGINE_DB_PATH)
