# Copyright 2025-2026 Minitap, Inc.
# Modifications Copyright 2026 Google LLC
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
#
# Originally from mobile-use (https://github.com/minitap-ai/mobile-use).
# See third_party/mobile_use/METADATA for the upstream source and local modifications.

"""Utilities for handling app locking and initial app launch logic."""

import asyncio
from bagel.device.context import BagelContext
from bagel.device.controllers.unified_controller import UnifiedMobileController
from bagel.device.app_launch import current_foreground, observe_foreground
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


async def _poll_for_app_ready(
    ctx: BagelContext, app_package: str, max_poll_seconds: int = 15, poll_interval: float = 1.0
) -> tuple[bool, str | None]:
    """Poll for app to be ready after launch.

    Treats mCurrentFocus=null as a loading state and keeps polling.
    Only fails if we get a different (non-null) package or timeout.

    Args:
        ctx: Mobile use context
        app_package: Expected package name
        max_poll_seconds: Maximum time to poll (default: 15s)
        poll_interval: Time between polls (default: 1s)

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    polls = int(max_poll_seconds / poll_interval)
    for i in range(polls):
        ready, current_package, task = await observe_foreground(ctx, app_package)
        if ready:
            if current_package == app_package:
                logger.success(f"App {app_package} is ready (took ~{i * poll_interval:.1f}s)")
            else:
                logger.success(
                    f"App {app_package} is ready (focused window belongs to '{current_package}', but the foreground {task.describe()} is owned by {app_package}, took ~{i * poll_interval:.1f}s)"
                )
            return (True, None)
        if current_package is None:
            logger.debug(f"Poll {i + 1}/{polls}: App loading (mCurrentFocus=null)...")
        else:
            logger.debug(
                f"Poll {i + 1}/{polls}: Wrong app in foreground (expected '{app_package}', got '{current_package}', foreground {(task.describe() if task else 'task unknown')}). Still waiting..."
            )
        if i < polls - 1:
            await asyncio.sleep(poll_interval)
    current_package, task = await current_foreground(ctx)
    error_msg = f"Timeout waiting for {app_package} to load after {max_poll_seconds}s. Current foreground: {current_package}; foreground {(task.describe() if task else 'task unknown')}"
    logger.error(error_msg)
    return (False, error_msg)


async def launch_app_with_retries(
    ctx: BagelContext, app_package: str, max_retries: int = 3, max_poll_seconds: int = 15
) -> tuple[bool, str | None]:
    """Launch an app with retry logic and smart polling.

    Args:
        ctx: Mobile use context
        app_package: Package name (Android) to launch
        max_retries: Maximum number of launch attempts (default: 3)
        max_poll_seconds: Maximum time to wait for app to load per attempt
          (default: 15s)

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    for attempt in range(1, max_retries + 1):
        logger.info(f"Launch attempt {attempt}/{max_retries} for app {app_package}")
        controller = UnifiedMobileController(ctx)
        if attempt > 1:
            logger.warning(
                f"Attempt {attempt - 1} failed. Force stopping '{app_package}' to clear frozen state before retrying..."
            )
            await controller.terminate_app(app_package)
            await asyncio.sleep(1.0)
        launch_success = await controller.launch_app(app_package)
        if not launch_success:
            error_msg = f"Failed to execute launch command for {app_package}"
            logger.error(error_msg)
            if attempt == max_retries:
                return (False, error_msg)
            await asyncio.sleep(2)
            continue
        await asyncio.sleep(1)
        success, error_msg = await _poll_for_app_ready(ctx, app_package, max_poll_seconds)
        if success:
            return (True, None)
        if attempt < max_retries:
            logger.warning(f"Attempt {attempt} failed: {error_msg}. Retrying...")
            await asyncio.sleep(1)
    error_msg = f"Failed to launch {app_package} after {max_retries} attempts"
    logger.error(error_msg)
    return (False, error_msg)
