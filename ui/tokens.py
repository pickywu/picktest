"""集中管理遊戲 UI 的顏色、尺寸與字級。

畫面程式不應再自行發明相近但不同的灰、金、藍。替換整體視覺時，
先調整本檔，再由畫面層處理少數具有世界觀意義的例外。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorTokens:
    text: tuple[int, int, int] = (244, 239, 226)
    text_secondary: tuple[int, int, int] = (190, 198, 207)
    text_disabled: tuple[int, int, int] = (112, 119, 128)
    gold: tuple[int, int, int] = (232, 183, 81)
    focus: tuple[int, int, int] = (246, 203, 104)
    surface: tuple[int, int, int, int] = (24, 32, 43, 222)
    surface_quiet: tuple[int, int, int, int] = (16, 23, 33, 184)
    surface_hover: tuple[int, int, int, int] = (55, 69, 84, 176)
    surface_pressed: tuple[int, int, int, int] = (72, 83, 94, 210)
    surface_selected: tuple[int, int, int, int] = (67, 76, 79, 214)
    surface_focused: tuple[int, int, int, int] = (63, 72, 78, 208)
    surface_loading: tuple[int, int, int, int] = (52, 65, 76, 190)
    surface_error: tuple[int, int, int, int] = (94, 42, 45, 214)
    line: tuple[int, int, int, int] = (126, 139, 151, 105)
    line_highlight: tuple[int, int, int, int] = (222, 190, 118, 150)
    inner_shadow: tuple[int, int, int, int] = (2, 5, 9, 150)
    material_tint: tuple[int, int, int] = (104, 112, 121)
    danger: tuple[int, int, int] = (207, 87, 91)
    healing: tuple[int, int, int] = (91, 177, 119)
    hp: tuple[int, int, int] = (220, 61, 67)
    shield: tuple[int, int, int] = (74, 151, 224)
    ember: tuple[int, int, int] = (201, 79, 66)
    brass: tuple[int, int, int] = (213, 166, 83)
    moss: tuple[int, int, int] = (117, 128, 92)


@dataclass(frozen=True)
class LayoutTokens:
    grid: int = 8
    safe_margin: int = 32
    minimum_hit_target: int = 44
    control_height: int = 48
    primary_control_height: int = 52
    control_padding_x: int = 18
    compact_control_padding_x: int = 10
    compact_gap: int = 8
    normal_gap: int = 16
    section_gap: int = 24
    page_gap: int = 32


@dataclass(frozen=True)
class TypeTokens:
    micro: int = 11
    secondary: int = 13
    body: int = 15
    control: int = 17
    section_title: int = 22
    page_title: int = 32
    display: int = 48


@dataclass(frozen=True)
class MotionTokens:
    hover_ms: int = 110
    pressed_ms: int = 75
    selected_ms: int = 160
    feedback_short_ms: int = 420


@dataclass(frozen=True)
class RadiusTokens:
    control: int = 4
    panel: int = 8
    modal: int = 10


@dataclass(frozen=True)
class FrameTokens:
    panel_inset: int = 10
    card_inset: int = 6
    panel_margin_ratio: float = .16
    card_margin_ratio: float = .10
    title_inset_x: int = 34
    title_inset_y: int = 32
    divider_height: int = 5


COLORS = ColorTokens()
LAYOUT = LayoutTokens()
TYPE = TypeTokens()
MOTION = MotionTokens()
RADIUS = RadiusTokens()
FRAMES = FrameTokens()
