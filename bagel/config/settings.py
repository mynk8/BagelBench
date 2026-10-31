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
from pydantic import Field
from pydantic_settings import BaseSettings

from bagel.config.constants import (
    DEFAULT_ADB_HOST,
    DEFAULT_ADB_PORT,
    ENV_DATA_ENGINE_DB_PATH,
)
from bagel.config.paths import (
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


class Settings(BaseSettings):
    """Centralized BAGEL runtime settings loaded from environment and .env files."""

    # Android ADB Connectivity
    ADB_HOST: str | None = Field(default=DEFAULT_ADB_HOST)
    ADB_PORT: int | None = Field(default=DEFAULT_ADB_PORT)
    ADB_DEVICE_SERIAL: str | None = None
    # UI hierarchy backend: "auto" = Accessibility Helper with UIAutomator2
    # fallback, "helper" = helper only, "uiautomator" = UIAutomator2 only.
    BAGEL_HIERARCHY_BACKEND: str = Field(default="auto")
    # Whether a task may install / upgrade the Accessibility Helper APK on a device
    # it holds. False = only attach to a helper installed by `bagel helper install`.
    BAGEL_HELPER_AUTO_INSTALL: bool = Field(default=True)

    # Paths & Storage
    TRACES_PATH: Path = Field(default_factory=get_default_traces_path)
    DATA_ENGINE_DB_PATH: Path = Field(default_factory=get_data_engine_db_path)
    TEMP_PATH: Path = Field(default_factory=get_temp_dir)

    model_config = {"env_file": ".env", "extra": "ignore"}


# Singleton instance
settings = Settings()

# Synchronize DATA_ENGINE_DB_PATH in environment for external sub-processes/tools
if settings.DATA_ENGINE_DB_PATH:
    os.environ[ENV_DATA_ENGINE_DB_PATH] = str(settings.DATA_ENGINE_DB_PATH)
