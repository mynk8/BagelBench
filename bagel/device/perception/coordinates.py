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

"""Parse device swipe arguments for screen presentation."""

import json
import re
from typing import Any


def parse_swipe_parameters(
    args: Any,
    default_duration: int | None = 800,
) -> tuple[str | None, str | list[int] | None, int | None]:
    """Parses swipe/drag/scroll parameters from various possible input formats into a standardized tuple:

    (kind, target, duration) where kind is 'direction' or 'coords' or None.
    If 'coords', target is [start_x, start_y, end_x, end_y] in 0-1000 scale.
    If 'direction', target is 'up' | 'down' | 'left' | 'right'.
    """
    if args is None:
        return "direction", "up", default_duration

    # Extract raw dictionary if args is a dict
    if isinstance(args, dict):
        direction = args.get("direction")
        start = args.get("start")
        end = args.get("end")
        coordinates = args.get("coordinates") or args.get("normalized_coordinates")
        action = args.get("action")
        gesture = args.get("gesture")
        duration = (
            args.get("duration")
            or args.get("duration_ms")
            or args.get("time_in_ms")
            or default_duration
        )
    else:
        direction = None
        start = None
        end = None
        coordinates = None
        action = args
        gesture = None
        duration = default_duration

    try:
        duration_int = int(duration) if duration is not None else default_duration
    except (ValueError, TypeError):
        duration_int = default_duration

    def _parse_pt(p: Any) -> list[int] | None:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                return [int(float(p[0])), int(float(p[1]))]
            except (ValueError, TypeError):
                pass
        if isinstance(p, str):
            nums = re.findall(r"-?\d+(?:\.\d+)?", p)
            if len(nums) >= 2:
                return [int(float(nums[0])), int(float(nums[1]))]
        return None

    # 1. Check start and end
    if start is not None and end is not None:
        pt_s = _parse_pt(start)
        pt_e = _parse_pt(end)
        if pt_s and pt_e:
            return "coords", [pt_s[0], pt_s[1], pt_e[0], pt_e[1]], duration_int

    # 2. Check candidate values in priority order
    candidates = [coordinates, action, gesture, direction]
    for c in candidates:
        if c is None:
            continue
        # If list of 4 numbers
        if isinstance(c, (list, tuple)):
            if len(c) == 4:
                try:
                    return "coords", [int(float(x)) for x in c], duration_int
                except (ValueError, TypeError):
                    pass
            elif (
                len(c) == 2 and isinstance(c[0], (list, tuple)) and isinstance(c[1], (list, tuple))
            ):
                pt1 = _parse_pt(c[0])
                pt2 = _parse_pt(c[1])
                if pt1 and pt2:
                    return "coords", [pt1[0], pt1[1], pt2[0], pt2[1]], duration_int

        # If string
        if isinstance(c, str):
            s = c.strip()
            # Try JSON parse first
            try:
                parsed = json.loads(s)
                if isinstance(parsed, (list, tuple)):
                    if len(parsed) == 4:
                        return "coords", [int(float(x)) for x in parsed], duration_int
                    elif len(parsed) == 2:
                        pt1 = _parse_pt(parsed[0])
                        pt2 = _parse_pt(parsed[1])
                        if pt1 and pt2:
                            return "coords", [pt1[0], pt1[1], pt2[0], pt2[1]], duration_int
            except (ValueError, TypeError):
                pass

            # Regex extract numbers
            nums = re.findall(r"-?\d+(?:\.\d+)?", s)
            if len(nums) == 4:
                return "coords", [int(float(x)) for x in nums], duration_int

            # Check direction string (only if no digits)
            s_lower = s.lower()
            if not any(char.isdigit() for char in s):
                for d in ("up", "down", "left", "right"):
                    if d in s_lower:
                        return "direction", d, duration_int

    return None, None, duration_int
