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

"""Host-side task slots: case/build assignments, setup and action budgets."""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field


@dataclass
class Slot:
    """One native benchmark task: a case on one build. Kept host-side only."""

    slot_id: str
    case_id: str
    build: str
    app_package: str | None = None
    setup: list[list[str]] = field(default_factory=list)
    """Host-side argv commands run before the agent's first call (reset, install, seed)."""
    step_budget: int | None = None
    setup_cwd: str | None = None
    signature: dict[str, Any] | None = None
