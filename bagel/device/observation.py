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

"""Capture the screen, index visible UI elements, and save the capture."""

import asyncio
import base64
from uuid import uuid4

from bagel.config import get_temp_dir
from bagel.device.context import BagelContext
from bagel.device.controllers.unified_controller import UnifiedMobileController
from bagel.device.results import ActionCode, ObserveResult
from bagel.device.perception.ocr_xml_fusion import fuse_ocr_with_xml
from bagel.device.perception.visualization import format_minimal_list_with_elements
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["observe"]


async def observe(
    ctx: BagelContext,
    controller: UnifiedMobileController,
    settle_ms: int = 400,
    ocr_results: list | None = None,
) -> tuple[ObserveResult, bytes | None]:
    """Return the indexed observation and raw screenshot bytes.

    A failed hierarchy still returns the screenshot with hierarchy_ok=False.
    """
    try:
        if settle_ms > 0:
            logger.info(f"Delaying {settle_ms / 1000:.1f}s before capturing screen state...")
            await asyncio.sleep(settle_ms / 1000.0)
        else:
            logger.info("Retrieving screen data directly (skip settling)...")
        device_data = await controller.get_screen_data()
        screenshot_bytes = base64.b64decode(device_data.base64)
    except Exception as e:
        logger.error(f"Failed to capture screen state: {e}")
        return (
            ObserveResult(
                ok=False,
                code=ActionCode.DEVICE_ERROR,
                message=f"Failed to capture screen state: {e}",
                hierarchy_ok=False,
            ),
            None,
        )

    xml_hierarchy = None
    ocr_results = ocr_results or []
    elements: list[dict] = []
    hierarchy_ok = True
    width = height = None
    try:
        xml_hierarchy = device_data.elements
        width = device_data.width or 1080
        height = device_data.height or 2400
        if ctx.device:
            ctx.device.device_width = width
            ctx.device.device_height = height

        fused_xml = fuse_ocr_with_xml(xml_hierarchy, ocr_results)
        minimal_list_str, elements, _ = format_minimal_list_with_elements(fused_xml, width, height)
    except Exception as e:
        logger.error(f"Failed to fetch or fuse UI hierarchy: {e}")
        minimal_list_str = "Not available due to hierarchy error."
        hierarchy_ok = False

    screenshot_path = None
    try:
        temp_file = get_temp_dir("screenshots") / f"{uuid4().hex}.jpg"
        temp_file.write_bytes(screenshot_bytes)
        screenshot_path = str(temp_file)
    except OSError as exc:
        logger.error(f"Failed to save screenshot: {exc}")

    from pathlib import Path

    return (
        ObserveResult(
            ok=True,
            message="Screen observed.",
            screenshot_path=screenshot_path,
            image_name=Path(screenshot_path).stem if screenshot_path else None,
            width=width,
            height=height,
            elements_text=minimal_list_str,
            elements=elements,
            hierarchy_ok=hierarchy_ok,
        ),
        screenshot_bytes,
    )
