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

"""MCP schemas and handlers for the Android device actions."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import inspect
from typing import Annotated, Any
from mcp.types import CallToolResult
from bagel.device.results import ActionResult


@dataclass(frozen=True)
class ParamSpec:
    """One typed MCP tool parameter."""

    name: str
    annotation: Any
    description: str | None = None
    required: bool = True
    default: Any = None


@dataclass(frozen=True)
class WireDialect:
    """The action-server tool mirroring one actuator method.

    ``bind`` receives the actuator and the validated, default-filled argument dict
    and performs the (tiny) call-site conversion the historical hand-written wrapper
    performed -- typically ``int()`` coercion of coordinate pairs.
    """

    description: str
    params: tuple[ParamSpec, ...]
    bind: Callable[[Any, dict[str, Any]], Awaitable[ActionResult]]


@dataclass(frozen=True)
class ActionSpec:
    """One device action exposed over MCP."""

    name: str
    wire: WireDialect


async def _wire_click(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.click(
        int(a["target"][0]), int(a["target"][1]), times=a["times"], delay_ms=a["delay_ms"]
    )


async def _wire_click_sequence(actuator: Any, a: dict[str, Any]) -> ActionResult:
    points = [(int(p[0]), int(p[1])) for p in a["sequence"]]
    return await actuator.click_sequence(points, delay_ms=a["delay_ms"])


async def _wire_long_press(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.long_press(
        int(a["target"][0]), int(a["target"][1]), duration_ms=a["duration_ms"]
    )


async def _wire_input_text(actuator: Any, a: dict[str, Any]) -> ActionResult:
    target = a["target"]
    norm = (int(target[0]), int(target[1])) if target else None
    return await actuator.input_text(a["text"], norm, clear_exist=a["clear_exist"])


async def _wire_swipe(actuator: Any, a: dict[str, Any]) -> ActionResult:
    start, end = (a["start"], a["end"])
    return await actuator.swipe(
        (int(start[0]), int(start[1])), (int(end[0]), int(end[1])), a["duration_ms"]
    )


async def _wire_press_key(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.press_key(a["key"])


async def _wire_manage_app(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.manage_app(a["action"], a["app_name"])


async def _wire_wait_for_delay(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.wait_for_delay(a["time_in_ms"])


async def _wire_wait_for_text(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.wait_for_text(a["text"], a["wait_state"], a["timeout_ms"])


async def _wire_open_link(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.open_link(a["url"])


async def _wire_erase_one_char(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.erase_one_char()


async def _wire_focus_and_clear_text(actuator: Any, a: dict[str, Any]) -> ActionResult:
    return await actuator.focus_and_clear_text(int(a["target"][0]), int(a["target"][1]))


_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="click",
        wire=WireDialect(
            description="Tap at a 0-1000 normalized [x, y] coordinate.",
            params=(
                ParamSpec("target", list[int]),
                ParamSpec("times", int, required=False, default=1),
                ParamSpec("delay_ms", int, required=False, default=100),
            ),
            bind=_wire_click,
        ),
    ),
    ActionSpec(
        name="click_sequence",
        wire=WireDialect(
            description="Tap a series of 0-1000 normalized [x, y] points in one atomic burst.",
            params=(
                ParamSpec("sequence", list[list[int]]),
                ParamSpec("delay_ms", int, required=False, default=50),
            ),
            bind=_wire_click_sequence,
        ),
    ),
    ActionSpec(
        name="long_press",
        wire=WireDialect(
            description="Long-press at a 0-1000 normalized [x, y] coordinate.",
            params=(
                ParamSpec("target", list[int]),
                ParamSpec("duration_ms", int, required=False, default=1000),
            ),
            bind=_wire_long_press,
        ),
    ),
    ActionSpec(
        name="input_text",
        wire=WireDialect(
            description="Type text, optionally focusing a 0-1000 normalized [x, y] target first.",
            params=(
                ParamSpec("text", str),
                ParamSpec("target", list[int] | None, required=False, default=None),
                ParamSpec("clear_exist", bool, required=False, default=True),
            ),
            bind=_wire_input_text,
        ),
    ),
    ActionSpec(
        name="swipe",
        wire=WireDialect(
            description="Swipe between two 0-1000 normalized [x, y] points.",
            params=(
                ParamSpec("start", list[int]),
                ParamSpec("end", list[int]),
                ParamSpec("duration_ms", int, required=False, default=800),
            ),
            bind=_wire_swipe,
        ),
    ),
    ActionSpec(
        name="press_key",
        wire=WireDialect(
            description="Press a device key (home, back, enter, delete, tab, search, menu, app_switch).",
            params=(ParamSpec("key", str),),
            bind=_wire_press_key,
        ),
    ),
    ActionSpec(
        name="manage_app",
        wire=WireDialect(
            description="Launch or stop an app by its exact installed package.",
            params=(ParamSpec("action", str), ParamSpec("app_name", str)),
            bind=_wire_manage_app,
        ),
    ),
    ActionSpec(
        name="wait_for_delay",
        wire=WireDialect(
            description="Wait for a fixed number of milliseconds.",
            params=(ParamSpec("time_in_ms", int),),
            bind=_wire_wait_for_delay,
        ),
    ),
    ActionSpec(
        name="wait_for_text",
        wire=WireDialect(
            description="Wait for text to appear on or disappear from the screen.",
            params=(
                ParamSpec("text", str),
                ParamSpec("wait_state", str, required=False, default="appear"),
                ParamSpec("timeout_ms", int, required=False, default=5000),
            ),
            bind=_wire_wait_for_text,
        ),
    ),
    ActionSpec(
        name="open_link",
        wire=WireDialect(
            description="Open a URL on the device.",
            params=(ParamSpec("url", str),),
            bind=_wire_open_link,
        ),
    ),
    ActionSpec(
        name="erase_one_char",
        wire=WireDialect(
            description="Erase a single character in the focused field.",
            params=(),
            bind=_wire_erase_one_char,
        ),
    ),
    ActionSpec(
        name="focus_and_clear_text",
        wire=WireDialect(
            description="Focus the field at a 0-1000 normalized [x, y] and clear its text.",
            params=(ParamSpec("target", list[int]),),
            bind=_wire_focus_and_clear_text,
        ),
    ),
)
ACTION_SPECS: dict[str, ActionSpec] = {spec.name: spec for spec in _SPECS}
EXCEPTION_PREFIXES: dict[str, str] = {
    "click": "Error during click",
    "click_sequence": "Error executing click sequence",
    "long_press": "Error during long press",
    "input_text": "Error during input text",
    "swipe": "Error during swipe",
    "press_key": "Error during press_key",
    "manage_app": "Error during manage_app",
    "wait_for_delay": "Error during wait_for_delay",
    "wait_for_text": "Error during wait_for_text",
}


def exception_prefix(action: str) -> str:
    """Returns the historical human-readable exception prefix for an action."""
    return EXCEPTION_PREFIXES.get(action, f"Error during {action}")


def wire_dialects() -> tuple[ActionSpec, ...]:
    """Returns every spec that has a wire dialect, in manifest order."""
    return _SPECS


def make_wire_handler(
    spec: ActionSpec,
    actuator: Any,
    wrap: Callable[[ActionResult], CallToolResult],
    wrap_exception: Callable[[str, Exception], CallToolResult],
) -> Callable[..., Awaitable[CallToolResult]]:
    """Builds the FastMCP tool function for one wire dialect.

    The returned coroutine carries an explicit ``__signature__`` so FastMCP derives
    the same argument model a literal ``async def`` produced historically, and the
    same ``Annotated[CallToolResult, ActionResult]`` return annotation so the
    structured-output schema is unchanged.
    """
    wire = spec.wire
    if wire is None:
        raise ValueError(f"Action '{spec.name}' has no wire dialect.")

    async def handler(**kwargs: Any) -> Any:
        try:
            return wrap(await wire.bind(actuator, kwargs))
        except Exception as e:
            return wrap_exception(spec.name, e)

    return_annotation = Annotated[CallToolResult, ActionResult]
    parameters = [
        inspect.Parameter(
            p.name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=p.annotation,
            default=inspect.Parameter.empty if p.required else p.default,
        )
        for p in wire.params
    ]
    handler.__name__ = spec.name
    handler.__qualname__ = spec.name
    handler.__doc__ = wire.description
    setattr(
        handler, "__signature__", inspect.Signature(parameters, return_annotation=return_annotation)
    )
    handler.__annotations__ = {p.name: p.annotation for p in wire.params}
    handler.__annotations__["return"] = return_annotation
    return handler
