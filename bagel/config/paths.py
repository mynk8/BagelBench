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

"""Centralized workspace, configuration, temporary files, and directory management."""

import os
from pathlib import Path
import sys

from bagel.config.constants import (
    DATA_ENGINE_DB_FILENAME,
    ENV_ANTIGRAVITY_APP_DIR,
    ENV_BAGEL_APP_DIR,
    ENV_BAGEL_TRACES_DIR,
    ENV_BAGEL_USE_USER_DIR,
)
from bagel.platform import platform

# Project root directory (3 levels up from bagel/config/paths.py)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT_DIR / "config"


def is_frozen_bundle() -> bool:
    """Check if running inside a PyInstaller / Nuitka standalone compiled binary."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def is_source_checkout() -> bool:
    """Return whether ``ROOT_DIR`` is an Bagel source checkout.

    Installed wheels also contain an ``bagel`` directory, so the repository
    metadata file is the important discriminator.  Runtime code must not treat
    a wheel's ``site-packages`` directory as writable application state.
    """
    return (ROOT_DIR / "pyproject.toml").is_file() and (ROOT_DIR / "bagel").is_dir()


def _use_user_app_dir() -> bool:
    """Return whether mutable runtime state belongs in the PAL user directory."""
    return (
        is_frozen_bundle()
        or not is_source_checkout()
        or os.getenv(ENV_BAGEL_USE_USER_DIR) == "true"
        or bool(os.getenv(ENV_BAGEL_APP_DIR))
        or bool(os.getenv(ENV_ANTIGRAVITY_APP_DIR))
    )


def get_app_dir() -> Path:
    """Returns the central application directory for BAGEL configurations, DBs, and traces.

    Order of precedence:
    1. BAGEL_APP_DIR or ANTIGRAVITY_APP_DIR environment variable.
    2. Legacy ~/.gemini/jetski or ~/.bagel directory if it exists.
    3. OS-standard data directory via Platform Abstraction Layer (PAL).
    """
    return platform.paths.resolve_app_dir()


def get_env_file() -> Path:
    """Return the canonical writable dotenv file for this installation mode."""
    return get_app_dir() / ".env" if _use_user_app_dir() else ROOT_DIR / ".env"


def get_default_traces_path() -> Path:
    """Returns default traces directory.

    Uses user app dir when running as a frozen binary or when app dir env is set.
    """
    env_traces = os.getenv(ENV_BAGEL_TRACES_DIR)
    if env_traces:
        traces_dir = Path(env_traces)
    elif _use_user_app_dir():
        traces_dir = get_app_dir() / "traces"
    else:
        traces_dir = ROOT_DIR / "traces"

    traces_dir.mkdir(parents=True, exist_ok=True)
    return traces_dir


def get_traces_dir() -> Path:
    """Alias for get_default_traces_path."""
    return get_default_traces_path()


def get_temp_dir(subfolder: str | None = None) -> Path:
    """Returns a unified temporary directory for BAGEL runtime operations (e.g., screenshots, recordings).

    Args:
        subfolder: Optional subfolder name under the temp directory.

    Returns:
        Path object pointing to the initialized temporary directory.
    """
    return platform.paths.temp_dir(subfolder)


def get_data_engine_db_path() -> Path:
    """Returns the unified SQLite database path for BAGEL DataEngine."""
    return get_default_traces_path() / DATA_ENGINE_DB_FILENAME


GLOBAL_APP_DIR = get_app_dir()
WORKSPACE_ROOT = ROOT_DIR
TRACES_PATH = get_default_traces_path()
DB_PATH = get_data_engine_db_path()
