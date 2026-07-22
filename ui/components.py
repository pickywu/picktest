"""Shared interaction states and their visual tokens."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .tokens import COLORS


class ControlState(Enum):
    DEFAULT = auto()
    HOVER = auto()
    PRESSED = auto()
    SELECTED = auto()
    FOCUSED = auto()
    DISABLED = auto()
    LOADING = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ControlVisual:
    text: tuple[int, int, int]
    surface: tuple[int, int, int]
    surface_alpha: int
    marker: tuple[int, int, int]
    marker_alpha: int
    y_offset: int = 0


def resolve_control_state(*, enabled: bool = True, hovered: bool = False,
                          pressed: bool = False, selected: bool = False,
                          focused: bool = False, loading: bool = False,
                          error: bool = False) -> ControlState:
    """Resolve flags with one stable priority order for every screen."""
    if error:
        return ControlState.ERROR
    if loading:
        return ControlState.LOADING
    if not enabled:
        return ControlState.DISABLED
    if pressed:
        return ControlState.PRESSED
    if selected:
        return ControlState.SELECTED
    if focused:
        return ControlState.FOCUSED
    if hovered:
        return ControlState.HOVER
    return ControlState.DEFAULT


def _rgb(color: tuple[int, ...]) -> tuple[int, int, int]:
    return color[0], color[1], color[2]


_VISUALS = {
    ControlState.DEFAULT: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_quiet), 0, COLORS.brass, 0,
    ),
    ControlState.HOVER: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_hover), COLORS.surface_hover[3],
        COLORS.brass, 210,
    ),
    ControlState.PRESSED: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_pressed), COLORS.surface_pressed[3],
        COLORS.focus, 235, -1,
    ),
    ControlState.SELECTED: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_selected), COLORS.surface_selected[3],
        COLORS.ember, 235,
    ),
    ControlState.FOCUSED: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_focused), COLORS.surface_focused[3],
        COLORS.focus, 245,
    ),
    ControlState.DISABLED: ControlVisual(
        COLORS.text_disabled, _rgb(COLORS.surface_quiet), 80,
        COLORS.text_disabled, 90,
    ),
    ControlState.LOADING: ControlVisual(
        COLORS.text_secondary, _rgb(COLORS.surface_loading),
        COLORS.surface_loading[3], COLORS.brass, 170,
    ),
    ControlState.ERROR: ControlVisual(
        COLORS.text, _rgb(COLORS.surface_error), COLORS.surface_error[3],
        COLORS.danger, 245,
    ),
}


def control_visual(state: ControlState) -> ControlVisual:
    return _VISUALS[state]


__all__ = [
    "ControlState", "ControlVisual", "control_visual", "resolve_control_state",
]
