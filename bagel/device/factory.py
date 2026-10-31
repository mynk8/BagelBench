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

"""Construct a device actuator and its fixed-argument ADB command runner."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import Any, cast

from bagel.device.conditions import Shell

logger = logging.getLogger(__name__)


def adb_shell(adb_client: Any, serial: str) -> Shell:
    """A :data:`Shell` over a ``adbutils``-style client for ``serial``."""

    async def run(argv: list[str]) -> str:
        device = adb_client.device(serial)
        return await asyncio.to_thread(device.shell, shlex.join(argv))

    return run


def device_actuator(serial: str, adb_host: str = "127.0.0.1", adb_port: int = 5037) -> Any:
    """An ``AdbActuator`` with its own context for ``serial`` (no agent run needed)."""
    from adbutils import AdbClient

    from bagel.device.clients.screen_client_factory import create_screen_client
    from bagel.device.context import BagelContext, DevicePlatform
    from bagel.device.actuators.adb import AdbActuator
    from bagel.platform import platform as host_platform
    from third_party.mobile_use.context import DeviceContext

    adb_client = AdbClient(host=adb_host, port=adb_port)
    try:
        width, height = adb_client.device(serial).window_size()
    except Exception:  # pylint: disable=broad-exception-caught
        width, height = 1080, 2400
    ctx = BagelContext(
        device=DeviceContext(
            host_platform=host_platform.os_type.name,
            mobile_platform=DevicePlatform.ANDROID,
            device_id=serial,
            device_width=width,
            device_height=height,
        ),
        adb_client=adb_client,
        ui_adb_client=create_screen_client(serial),
    )
    return AdbActuator(ctx)


_GLOBAL_CONTROLLER = None
_CONTROLLERS: dict[str, Any] = {}


def get_controller(device_serial: str | None = None):
    """Lazy-load device controller on-demand, caching per device serial."""
    from adbutils import AdbClient

    from bagel.device.clients.screen_client_factory import create_screen_client
    from bagel.device.controllers.unified_controller import UnifiedMobileController
    from bagel.device.context import BagelContext, DeviceContext, DevicePlatform
    from bagel.platform import platform

    global _GLOBAL_CONTROLLER, _CONTROLLERS
    target_serial = (
        device_serial or os.environ.get("BAGEL_DEVICE_ID") or os.environ.get("ADB_DEVICE_SERIAL")
    )
    if target_serial and target_serial in _CONTROLLERS:
        return _CONTROLLERS[target_serial]
    if not target_serial and _GLOBAL_CONTROLLER is not None:
        return _GLOBAL_CONTROLLER

    logger.info("Initializing lazy device controller...")
    if os.environ.get("BAGEL_CLOUD_MODE") == "1":
        logger.info(
            "GCP CLOUD MODE active: initializing CloudMobileDeviceController via UnifiedMobileController..."
        )
        resolved_serial = target_serial or "cloud_device"
        ctx = BagelContext(
            device=DeviceContext.model_validate(
                {
                    "platform": DevicePlatform.ANDROID,
                    "device_id": resolved_serial,
                    "width": 1080,
                    "height": 2400,
                }
            )
        )
        controller = UnifiedMobileController(ctx=ctx)
        if resolved_serial:
            _CONTROLLERS[resolved_serial] = controller
        if _GLOBAL_CONTROLLER is None:
            _GLOBAL_CONTROLLER = controller
        return controller

    host = os.environ.get("ADB_HOST", "localhost")
    port_str = os.environ.get("ADB_PORT", "5037")
    port = int(port_str) if port_str.isdigit() else 5037
    if "ADB_SERVER_SOCKET" not in os.environ and (host != "localhost" or port != 5037):
        os.environ["ADB_SERVER_SOCKET"] = f"tcp:{host}:{port}"
    adb = AdbClient(host=host, port=port)

    devices = adb.device_list()
    if not devices:
        raise Exception(f"No Android devices found at {host}:{port}")

    if target_serial:
        matched = [d for d in devices if d.serial == target_serial]
        if not matched:
            raise Exception(
                f"Target Android device '{target_serial}' not found at"
                f" {host}:{port} among available devices."
            )
        device = matched[0]
    else:
        device = devices[0]
    device_id = cast(str, device.serial)

    # Observer path: the helper is used only when it is already installed and
    # running; nothing is installed from here (that happens inside a task's
    # device-lock boundary or via `bagel helper install`).
    ui_client = create_screen_client(device_id)
    try:
        ui_data = ui_client.get_screen_data()
        width, height = ui_data.width, ui_data.height
    except Exception as e:
        logger.warning(f"Failed initial screen data check, using defaults: {e}")
        width, height = 1080, 2400

    ctx = BagelContext.model_validate(
        {
            "trace_id": "mcp-session",
            "device": DeviceContext(
                host_platform=platform.os_type.name,
                mobile_platform=DevicePlatform.ANDROID,
                device_id=device_id,
                device_width=width,
                device_height=height,
            ),
            "adb_client": adb,
            "ui_adb_client": ui_client,
        }
    )

    controller = UnifiedMobileController(ctx)
    if device_id:
        _CONTROLLERS[device_id] = controller
    if _GLOBAL_CONTROLLER is None:
        _GLOBAL_CONTROLLER = controller
    logger.info(f"Lazy device controller fully initialized for device: {device_id}")
    return controller
