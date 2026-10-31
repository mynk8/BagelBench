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

"""Device-control facade using the configured Android driver."""

from bagel.device.context import BagelContext
from bagel.device.drivers.factory import get_driver
from third_party.mobile_use.controllers.unified_controller import UnifiedMobileControllerBase


class UnifiedMobileController(UnifiedMobileControllerBase):
    def __init__(self, ctx: BagelContext):
        super().__init__(ctx, get_driver(ctx))

    async def cleanup(self) -> None:
        await self._driver.disconnect()
