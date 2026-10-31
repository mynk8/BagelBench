"""Device operations remain deterministic after removing the internal agents."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bagel.device.actuators.adb import AdbActuator
from bagel.device.context import BagelContext, DeviceContext
from bagel.device.observation import observe
from third_party.mobile_use.utils import app_launch_utils


@pytest.mark.parametrize(
    "package,expected", [("org.tasks", True), ("Tasks", False), ("org.task", False)]
)
def test_app_management_requires_an_exact_installed_package(monkeypatch, package, expected):
    monkeypatch.setattr(
        "third_party.mobile_use.controllers.platform_specific_commands_controller.list_packages",
        lambda ctx: "org.tasks\norg.other\n",
    )
    controller = SimpleNamespace(terminate_app=AsyncMock(return_value=True))
    actuator = AdbActuator(BagelContext(device=DeviceContext()), controller=controller)

    result = asyncio.run(actuator.manage_app("stop", package))

    assert result.ok is expected
    assert controller.terminate_app.await_count == int(expected)


@pytest.mark.parametrize("launch_success", [True, False])
def test_app_launch_uses_the_device_without_trace_or_model_services(monkeypatch, launch_success):
    controller = SimpleNamespace(launch_app=AsyncMock(return_value=launch_success))
    monkeypatch.setattr(app_launch_utils, "UnifiedMobileController", lambda ctx: controller)
    monkeypatch.setattr(app_launch_utils.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        app_launch_utils, "_poll_for_app_ready", AsyncMock(return_value=(True, None))
    )

    success, error = asyncio.run(
        app_launch_utils.launch_app_with_retries(
            BagelContext(device=DeviceContext()), "org.tasks", max_retries=1
        )
    )

    assert success is launch_success
    assert bool(error) is not launch_success
    controller.launch_app.assert_awaited_once_with("org.tasks")


def test_observations_keep_distinct_capture_files(monkeypatch, tmp_path):
    monkeypatch.setattr("bagel.device.observation.get_temp_dir", lambda subfolder: tmp_path)
    controller = SimpleNamespace(
        get_screen_data=AsyncMock(
            return_value=SimpleNamespace(base64="c2NyZWVu", elements=[], width=100, height=200)
        )
    )
    ctx = BagelContext(device=DeviceContext())

    async def capture_twice():
        first, _ = await observe(ctx, controller, settle_ms=0)
        second, _ = await observe(ctx, controller, settle_ms=0)
        return first, second

    first, second = asyncio.run(capture_twice())
    assert first.ok and second.ok
    assert first.screenshot_path != second.screenshot_path
    assert Path(first.screenshot_path).read_bytes() == b"screen"
    assert Path(second.screenshot_path).read_bytes() == b"screen"
