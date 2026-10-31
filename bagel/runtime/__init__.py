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

"""Device connectivity, locking and screen state services."""

from bagel.runtime.device_lock import ConcurrencyMode, DeviceBusyError, DeviceExecutionLock
from bagel.runtime.adb_endpoint import (
    ADB_ENDPOINT_ID_ENV,
    AdbEndpoint,
    AdbSession,
    AdbTarget,
    InvalidAdbEndpoint,
    current_adb_endpoint,
)
from bagel.runtime.device_pool import DevicePool, DeviceStatus, device_pool
from bagel.runtime.process_probe import pid_is_alive
from bagel.runtime.awake_service import (
    ensure_device_awake,
    sanitize_device_state,
    screen_awake_service,
    shutdown_awake_service,
    start_awake_service,
)
