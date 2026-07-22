r"""Asset-backed drawing and layout helpers for the RPG."""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any

import arcade
from arcade.types import Color

from character_scale import (
    canvas_center_offset,
    monster_pose_scale,
    monster_pose_anchor_x,
    player_pose_anchor_x,
    player_uniform_scale,
)
from localization import get_locale, translate
from ui.assets import (
    canonical_ui_asset,
    resolve_ui_asset,
    ui_asset_has_integrated_surface,
    ui_asset_has_surface,
)
from ui.components import ControlState, control_visual, resolve_control_state
from ui.combat_icons import (
    INTENT_ICONS,
    StatusBadge,
    collect_enemy_status_badges,
    collect_player_status_badges,
    intent_icon,
)
from ui.map_layout import (
    cover_map_viewport,
    route_boss_geometry,
    route_node_geometry,
)
from ui.tokens import COLORS, FRAMES, LAYOUT, TYPE


SCREEN_WIDTH = 1180
SCREEN_HEIGHT = 720
SCREEN_TITLE = "EMBER KINGDOM"

INK = COLORS.text
MUTED = COLORS.text_secondary
GOLD = COLORS.gold
PANEL = COLORS.surface
PANEL_EDGE = COLORS.line[:3]
RED = COLORS.hp
GREEN = COLORS.healing
BLUE = COLORS.shield
PURPLE = (176, 122, 232)
ORANGE = (235, 137, 67)

ASSET_ROOT = Path(__file__).resolve().parent / "assets"
PLAYER_ART_ROOT = ASSET_ROOT / "characters" / "players" / "tier_1"
BACKGROUND_ART_ROOT = ASSET_ROOT / "backgrounds"
TITLE_LOGO_PATH = BACKGROUND_ART_ROOT / "title" / "logo.png"
DEATH_EMBLEM_PATH = BACKGROUND_ART_ROOT / "endings" / "death_emblem.png"
END_VICTORY_BACKGROUND_PATH = BACKGROUND_ART_ROOT / "endings" / "victory_background.png"
END_DEFEAT_BACKGROUND_PATH = BACKGROUND_ART_ROOT / "endings" / "defeat_background.png"
VICTORY_EMBLEM_PATH = BACKGROUND_ART_ROOT / "endings" / "victory_emblem.png"
MONSTER_ART_ROOT = ASSET_ROOT / "characters" / "monsters"
EFFECT_ART_ROOT = ASSET_ROOT / "effects" / "combat"
UI_ICON_ROOT = ASSET_ROOT / "ui" / "icons"
ROUTE_KIND_ICON_ASSETS = {
    "battle": "icons/map/kind_battle.png",
    "elite": "icons/map/kind_elite.png",
    "campfire": "icons/map/kind_campfire.png",
    "shop": "icons/map/kind_shop.png",
    "boss": "icons/map/kind_boss.png",
}

# ---------- Replaceable game font ----------
# Keep every font decision here.  To swap the UI typeface later, change these
# paths/family names only; drawing code must use UI_FONT_STACK.
FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"
# Bundled Noto Sans CJK (SIL Open Font License 1.1).  One harmonised type family
# covering Traditional/Simplified Chinese, Japanese and Korean plus Latin, so
# every locale renders identically on ANY machine without relying on OS fonts.
# The regional builds share one design (visually consistent); each carries its
# language's preferred glyph shapes.
_NOTO_DIR = FONT_ROOT / "noto_sans_cjk"
_BUNDLED_FONTS = {
    "Noto Sans CJK TC": _NOTO_DIR / "NotoSansCJKtc-Regular.otf",
    "Noto Sans CJK SC": _NOTO_DIR / "NotoSansCJKsc-Regular.otf",
    "Noto Sans CJK JP": _NOTO_DIR / "NotoSansCJKjp-Regular.otf",
    "Noto Sans CJK KR": _NOTO_DIR / "NotoSansCJKkr-Regular.otf",
}
UI_FONT_FAMILY = "Noto Sans CJK TC"
UI_FONT_STACK = (UI_FONT_FAMILY, "Microsoft JhengHei", "Arial")

# Per-locale stacks: the bundled Noto family is tried first (guaranteed present
# and glyph-complete); OS fonts remain only as a safety fallback.
_LOCALE_FONT_STACKS = {
    "zh-TW": ("Noto Sans CJK TC", "Microsoft JhengHei", "Arial"),
    "zh-CN": ("Noto Serif CJK SC", "Noto Sans CJK SC", "Microsoft YaHei", "Microsoft JhengHei", "Arial"),
    "EN": ("Noto Sans CJK TC", "Arial"),
    "JA": ("Noto Sans CJK JP", "Yu Gothic", "Meiryo", "Arial"),
    "KO": ("Noto Sans CJK KR", "Malgun Gothic", "Arial"),
}


def current_font_stack() -> tuple[str, ...]:
    """Return the font stack for the active locale (bundled font first)."""
    return _LOCALE_FONT_STACKS.get(get_locale(), UI_FONT_STACK)


for _family, _font_path in _BUNDLED_FONTS.items():
    if _font_path.is_file():
        try:
            arcade.load_font(_font_path)
        except Exception:  # A single bad/missing face must not break startup.
            pass
MONSTER_ART_KIND_NAMES = {
    "血量型": "hp",
    "攻擊型": "attack",
    "防禦型": "defense",
}
INTENT_ICON_FILES = {
    key: Path(spec.asset_path).name for key, spec in INTENT_ICONS.items()
}
PLAYER_ART_SEX_DIRS = {"男性": "male", "女性": "female"}
PLAYER_ART_RACE_DIRS = {
    "獸人": "orc", "人類": "human", "矮人": "dwarf", "精靈": "elf",
}
PLAYER_ART_JOB_FILES = {
    "法師": "mage.png", "聖騎士": "paladin.png",
    "盜賊": "rogue.png", "術士": "warlock.png",
    "戰士": "warrior.png",
}
CJK_NO_LINE_START = frozenset("，。！？；：、）》」』】〕〉…—")

_AI_UI_TEXTURE_CACHE: dict[str, arcade.Texture] = {}
_AI_UI_TIGHT_CACHE: dict[tuple[str, int], arcade.Texture] = {}
_AI_UI_PATCH_CACHE: dict[tuple[str, float], tuple[arcade.Texture, ...]] = {}
_AI_EFFECT_CACHE: dict[str, arcade.Texture] = {}
_BACKGROUND_CACHE: dict[str, arcade.Texture] = {}
_PLAYER_TEXTURE_CACHE: dict[tuple[str, str, str, str], arcade.Texture] = {}
_PLAYER_HEAD_TEXTURE_CACHE: dict[tuple[str, str, str], arcade.Texture] = {}
_MONSTER_TEXTURE_CACHE: dict[tuple[int, str, str], arcade.Texture] = {}
_CONTEXT_ICON_TEXTURE_CACHE: dict[str, arcade.Texture] = {}
_QUIET_SURFACE_CACHE: dict[float, arcade.Texture] = {}
_TITLE_LOGO_TEXTURE: arcade.Texture | None = None
_DEATH_EMBLEM_TEXTURE: arcade.Texture | None = None
_VICTORY_EMBLEM_TEXTURE: arcade.Texture | None = None
_END_BACKGROUND_TEXTURES: dict[bool, arcade.Texture] = {}

SKILL_EFFECT_FILES_BY_JOB: dict[str, tuple[str, ...]] = {
    "戰士": (
        "steel_guard.png", "slash_streak.png", "magic_ring.png",
        "blood_drop.png", "magic_mote.png",
    ),
    "法師": (
        "fireball_projectile.png", "fire_impact.png", "ice_crystal.png",
        "barrier_hex.png", "magic_mote.png",
    ),
    "聖騎士": (
        "holy_beam.png", "impact_burst.png", "holy_sigil.png",
        "angel_wing.png", "magic_ring.png", "magic_mote.png",
    ),
    "盜賊": (
        "shadow_slash.png", "smoke_puff.png", "stun_star.png",
        "magic_mote.png",
    ),
    "術士": (
        "corruption_bolt.png", "curse_wisp.png", "magic_ring.png",
        "magic_mote.png",
    ),
}


def _required_texture(path: Path, description: str) -> arcade.Texture:
    """Load a required AI asset and fail clearly instead of drawing a fallback."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")
    return arcade.load_texture(path)


def load_title_logo() -> arcade.Texture:
    """Load the generated title insignia once and reuse it on the home screen."""
    global _TITLE_LOGO_TEXTURE
    if _TITLE_LOGO_TEXTURE is None:
        _TITLE_LOGO_TEXTURE = _required_texture(TITLE_LOGO_PATH, "AI title logo")
    return _TITLE_LOGO_TEXTURE


def load_death_emblem() -> arcade.Texture:
    """Load the DEATH emblem once for the defeat screen."""
    global _DEATH_EMBLEM_TEXTURE
    if _DEATH_EMBLEM_TEXTURE is None:
        _DEATH_EMBLEM_TEXTURE = _required_texture(
            DEATH_EMBLEM_PATH, "DEATH emblem"
        )
    return _DEATH_EMBLEM_TEXTURE


def load_victory_emblem() -> arcade.Texture:
    """Load the transparent AI-painted victory title for the end screen."""
    global _VICTORY_EMBLEM_TEXTURE
    if _VICTORY_EMBLEM_TEXTURE is None:
        _VICTORY_EMBLEM_TEXTURE = _required_texture(
            VICTORY_EMBLEM_PATH, "AI victory emblem"
        )
    return _VICTORY_EMBLEM_TEXTURE


def load_end_background(victory: bool) -> arcade.Texture:
    """Load the victory or defeat back-view ending artwork once."""
    texture = _END_BACKGROUND_TEXTURES.get(victory)
    if texture is None:
        path = (END_VICTORY_BACKGROUND_PATH if victory
                else END_DEFEAT_BACKGROUND_PATH)
        description = ("AI victory ending background" if victory
                       else "AI defeat ending background")
        texture = _required_texture(path, description)
        _END_BACKGROUND_TEXTURES[victory] = texture
    return texture


def load_ai_effect(filename: str) -> arcade.Texture:
    """Load one required transparent AI-painted VFX sprite."""
    texture = _AI_EFFECT_CACHE.get(filename)
    if texture is None:
        texture = _required_texture(EFFECT_ART_ROOT / filename, f"effect {filename}")
        _AI_EFFECT_CACHE[filename] = texture
    return texture


def skill_effect_files(job: str) -> tuple[str, ...]:
    """Return the bounded VFX set needed by one selected class."""
    return SKILL_EFFECT_FILES_BY_JOB.get(job, ("magic_mote.png",))


def prewarm_skill_effects(job: str) -> tuple[arcade.Texture, ...]:
    """Warm one class's existing full-resolution VFX without changing output."""
    return tuple(load_ai_effect(filename) for filename in skill_effect_files(job))


def load_ai_ui_texture(relative_path: str) -> arcade.Texture:
    """Load one required AI-painted UI asset from the explicit asset catalog."""
    relative_path = canonical_ui_asset(relative_path)
    texture = _AI_UI_TEXTURE_CACHE.get(relative_path)
    if texture is None:
        path = resolve_ui_asset(relative_path)
        texture = _required_texture(path, f"AI UI {relative_path}")
        _AI_UI_TEXTURE_CACHE[relative_path] = texture
    return texture


def load_ai_ui_patches(relative_path: str,
                       margin_ratio: float) -> tuple[arcade.Texture, ...]:
    """Crop a mother asset into nine reusable Arcade textures."""
    key = (relative_path, round(margin_ratio, 3))
    cached = _AI_UI_PATCH_CACHE.get(key)
    if cached is not None:
        return cached
    source = load_ai_ui_texture(relative_path)
    margin_x = max(1, min(source.width // 3, round(source.width * margin_ratio)))
    margin_y = max(1, min(source.height // 3, round(source.height * margin_ratio)))
    xs = (0, margin_x, source.width - margin_x, source.width)
    ys = (0, margin_y, source.height - margin_y, source.height)
    patches = tuple(
        source.crop(xs[column], ys[row],
                    xs[column + 1] - xs[column],
                    ys[row + 1] - ys[row])
        for row in range(3)
        for column in range(3)
    )
    _AI_UI_PATCH_CACHE[key] = patches
    return patches


def draw_ai_ui_frame_asset(relative_path: str, left: float, bottom: float,
                           width: float, height: float, *,
                           tint: tuple[int, int, int] | None = None,
                           active: bool = False, enabled: bool = True,
                           margin_ratio: float = .18,
                           filled: bool = True) -> None:
    """Draw an AI mother asset as nine reusable Arcade texture patches."""
    relative_path = canonical_ui_asset(relative_path)
    surface_backed = ui_asset_has_surface(relative_path)
    integrated_surface = ui_asset_has_integrated_surface(relative_path)
    if filled and surface_backed:
        if not integrated_surface:
            veil = load_ai_ui_texture("surfaces/control.png")
            surface_color = (210, 218, 222)
            if tint is not None:
                surface_color = tuple(min(255, 150 + round(channel * .35))
                                      for channel in tint)
            arcade.draw_texture_rect(
                veil, arcade.XYWH(left + width / 2, bottom + height / 2,
                                  width, height), color=Color(*surface_color), alpha=238,
            )
    patches = load_ai_ui_patches(relative_path, margin_ratio)
    margin = max(3.0, min(24.0, width / 3, height / 3))
    xs = (left, left + margin, left + width - margin, left + width)
    ys = (bottom, bottom + margin, bottom + height - margin, bottom + height)
    if tint is None:
        draw_color = (255, 255, 255)
    else:
        draw_color = tuple(min(255, 145 + round(channel * .43)) for channel in tint)
    if active:
        draw_color = tuple(min(255, channel + 24) for channel in draw_color)
    draw_alpha = 255 if enabled else 135
    for row in range(3):
        for column in range(3):
            if (row == 1 and column == 1
                    and (not filled or (surface_backed
                                        and not integrated_surface))):
                continue
            patch = patches[row * 3 + column]
            patch_width = max(1.0, xs[column + 1] - xs[column])
            patch_height = max(1.0, ys[row + 1] - ys[row])
            arcade.draw_texture_rect(
                patch,
                arcade.XYWH(xs[column] + patch_width / 2,
                            ys[row] + patch_height / 2,
                            patch_width, patch_height),
                color=Color(*draw_color), alpha=draw_alpha,
            )


def load_ai_ui_icon(relative_path: str, size: int = 72,
                    brightness: float = 1.0) -> arcade.Texture:
    """Load a required icon; scale and highlight are applied at draw time."""
    del size, brightness
    return load_ai_ui_texture(relative_path)


def load_tight_ai_ui_texture(relative_path: str, padding: int = 2) -> arcade.Texture:
    """Crop transparent margins from a generated UI mother asset once."""
    key = (relative_path, padding)
    cached = _AI_UI_TIGHT_CACHE.get(key)
    if cached is not None:
        return cached
    source = load_ai_ui_texture(relative_path)
    points = source.hit_box_points
    if not points:
        _AI_UI_TIGHT_CACHE[key] = source
        return source
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    left = max(0, math.floor(source.width / 2 + min_x) - padding)
    right = min(source.width, math.ceil(source.width / 2 + max_x) + padding)
    top = max(0, math.floor(source.height / 2 - max_y) - padding)
    bottom = min(source.height, math.ceil(source.height / 2 - min_y) + padding)
    cropped = source.crop(left, top, max(1, right - left), max(1, bottom - top))
    _AI_UI_TIGHT_CACHE[key] = cropped
    return cropped


def load_context_icon(name: str) -> arcade.Texture:
    """Load and tightly crop a context-specific UI icon."""
    key = f"icon:{name}"
    texture = _CONTEXT_ICON_TEXTURE_CACHE.get(key)
    if texture is None:
        icon_paths = {
            "guard": UI_ICON_ROOT / "actions" / "guard.png",
            "slash": UI_ICON_ROOT / "actions" / "slash.png",
            "potion_bag": UI_ICON_ROOT / "potions" / "bag.png",
            "reward_ember": UI_ICON_ROOT / "rewards" / "ember.png",
        }
        path = icon_paths.get(name)
        if path is None:
            raise ValueError(f"Unsupported context icon: {name}")
        source = _required_texture(path, f"context icon {name}")
        points = source.hit_box_points
        if points:
            padding = 2
            min_x = min(point[0] for point in points)
            max_x = max(point[0] for point in points)
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            left = max(0, math.floor(source.width / 2 + min_x) - padding)
            right = min(source.width, math.ceil(source.width / 2 + max_x) + padding)
            top = max(0, math.floor(source.height / 2 - max_y) - padding)
            bottom = min(source.height, math.ceil(source.height / 2 - min_y) + padding)
            texture = source.crop(left, top, max(1, right - left),
                                  max(1, bottom - top))
        else:
            texture = source
        _CONTEXT_ICON_TEXTURE_CACHE[key] = texture
    return texture


def _load_generated_background(relative_path: str) -> arcade.Texture:
    texture = _BACKGROUND_CACHE.get(relative_path)
    if texture is None:
        texture = _required_texture(
            BACKGROUND_ART_ROOT / relative_path,
            f"AI background {relative_path}",
        )
        _BACKGROUND_CACHE[relative_path] = texture
    return texture


def make_background() -> arcade.Texture:
    return _load_generated_background("title/background.png")


def make_activity_background(kind: str, variant: int = 0) -> arcade.Texture:
    if kind == "battle" and 1 <= variant <= 5:
        relative_path = f"battles/stage_{variant:02d}.png"
    elif kind == "shop":
        relative_path = "activities/shop.png"
    elif kind == "campfire":
        relative_path = "activities/campfire.png"
    elif kind == "event" and 1 <= variant <= 20:
        relative_path = f"events/event_{variant:02d}.png"
    else:
        raise ValueError(f"Unsupported activity background: {kind!r}, variant={variant}")
    return _load_generated_background(relative_path)


def make_adventure_map(chapter: int = 1) -> arcade.Texture:
    """Load one of the five route-map paintings.

    Chapters one through four mirror the journey stages; chapter five is the
    final approach to the throne.  Keeping these paintings free of authored
    route lines lets the generated graph remain readable above every backdrop.
    """
    chapter = max(1, min(5, int(chapter)))
    return _load_generated_background(
        f"adventure/progress_map_chapter_{chapter:02d}.png"
    )


def make_talent_background() -> arcade.Texture:
    """Load the dedicated talent-tree backdrop.

    Keeping this separate from the title backdrop prevents the progression
    screen from reading like UI pasted over the home screen.  The generated
    artwork is cached by ``_load_generated_background`` just like the other
    full-screen scene paintings.
    """
    return _load_generated_background("talents/background.png")


def player_gear_tier(level: int) -> int:
    return min(5, 1 + max(0, level - 1) // 5)


def make_player_portrait(sex: str, race: str, job: str, level: int = 1,
                         pose: str = "idle") -> arcade.Texture:
    """Load the required AI character sprite directly; no generated fallback."""
    del level
    if pose not in {"idle", "attack", "hurt", "block"}:
        raise ValueError(f"Unsupported player pose: {pose}")
    key = (sex, race, job, pose)
    cached = _PLAYER_TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    sex_dir = PLAYER_ART_SEX_DIRS.get(sex)
    race_dir = PLAYER_ART_RACE_DIRS.get(race)
    filename = PLAYER_ART_JOB_FILES.get(job)
    asset_path = (
        PLAYER_ART_ROOT / pose / sex_dir / race_dir / filename
        if sex_dir and race_dir and filename else None
    )
    if asset_path is None:
        raise ValueError(f"Unsupported character art combination: {sex}/{race}/{job}")
    texture = _required_texture(asset_path, f"AI character {sex}/{race}/{job}")
    _PLAYER_TEXTURE_CACHE[key] = texture
    return texture


def make_player_head_portrait(sex: str, race: str, job: str) -> arcade.Texture:
    """Crop a readable head-and-shoulders avatar from an idle character asset."""
    key = (sex, race, job)
    cached = _PLAYER_HEAD_TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    source = make_player_portrait(sex, race, job, pose="idle")
    image = source.image
    alpha = image.getchannel("A")
    width, height = image.size
    alpha_mask = alpha.point(lambda value: 255 if value > 24 else 0)
    visible_bounds = alpha_mask.getbbox() or (0, 0, width, height)
    central_left = round(width * .27)
    central_right = round(width * .73)
    threshold = max(6, round((central_right - central_left) * .045))
    visible_top = visible_bounds[1]
    for y in range(visible_bounds[1], visible_bounds[3]):
        row = alpha_mask.crop((central_left, y, central_right, y + 1))
        if sum(pixel > 0 for pixel in row.getdata()) >= threshold:
            visible_top = y
            break

    # Character sheets use several different canvas sizes and body occupancies.
    # Derive the avatar window from the actual body height instead of the PNG
    # height so a 1024x1536 warrior and a 1254x1254 mage show comparable heads.
    body_height = max(1, visible_bounds[3] - visible_top)
    crop_size = min(width, height, max(180, round(body_height * .36)))
    top = max(0, visible_top - round(crop_size * .07))
    top = min(top, height - crop_size)

    # Some characters stand well left or right of their transparent canvas.
    # Follow the widest opaque run on each head-band row: broad hair, face and
    # shoulders outweigh a thin staff or axe without assuming canvas centring.
    focus_bottom = min(height, visible_top + max(1, round(crop_size * .42)))
    head_band = alpha_mask.crop((0, visible_top, width, focus_bottom))
    head_center_x = width / 2
    row_centers: list[tuple[float, int]] = []
    pixels = head_band.load()
    minimum_run = max(8, round(width * .015))
    for y in range(head_band.height):
        best_start = 0
        best_end = 0
        run_start: int | None = None
        for x in range(width + 1):
            opaque = x < width and bool(pixels[x, y])
            if opaque and run_start is None:
                run_start = x
            elif not opaque and run_start is not None:
                if x - run_start > best_end - best_start:
                    best_start, best_end = run_start, x
                run_start = None
        run_width = best_end - best_start
        if run_width >= minimum_run:
            row_centers.append(((best_start + best_end - 1) / 2, run_width))
    total_weight = sum(weight for _center, weight in row_centers)
    if total_weight:
        head_center_x = sum(
            center * weight for center, weight in row_centers
        ) / total_weight
    left = round(head_center_x - crop_size / 2)
    left = max(0, min(width - crop_size, left))
    avatar = source.crop(left, top, crop_size, crop_size)
    _PLAYER_HEAD_TEXTURE_CACHE[key] = avatar
    return avatar


def make_monster_portrait(rank: int, kind: str, pose: str = "idle") -> arcade.Texture:
    """Load the required AI monster sprite directly; no generated fallback."""
    if pose not in {"idle", "attack", "hurt", "block"}:
        raise ValueError(f"Unsupported monster pose: {pose}")
    key = (rank, kind, pose)
    cached = _MONSTER_TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    kind_name = MONSTER_ART_KIND_NAMES.get(kind)
    if kind_name is None or not 1 <= rank <= 6:
        raise ValueError(f"Unsupported monster art combination: rank={rank}, kind={kind}")
    path = MONSTER_ART_ROOT / f"rank_{rank:02d}" / pose / f"{kind_name}.png"
    texture = _required_texture(path, f"AI monster rank={rank}, kind={kind}")
    _MONSTER_TEXTURE_CACHE[key] = texture
    return texture


def make_critical_effect() -> arcade.Texture:
    return load_ai_effect("impact_burst.png")


def fit_texture_size(texture: arcade.Texture, max_width: float,
                     max_height: float) -> tuple[float, float]:
    """Fit a texture inside a box without changing its original aspect ratio."""
    source_width = max(1.0, float(texture.width))
    source_height = max(1.0, float(texture.height))
    scale = min(max_width / source_width, max_height / source_height)
    return source_width * scale, source_height * scale


def fit_visible_texture_size(texture: arcade.Texture, max_visible_width: float,
                             max_visible_height: float) -> tuple[float, float]:
    """Scale by opaque hit-box bounds instead of transparent canvas bounds."""
    points = texture.hit_box_points
    if not points:
        return fit_texture_size(texture, max_visible_width, max_visible_height)
    visible_width = max(1.0, max(point[0] for point in points)
                        - min(point[0] for point in points))
    visible_height = max(1.0, max(point[1] for point in points)
                         - min(point[1] for point in points))
    scale = min(max_visible_width / visible_width,
                max_visible_height / visible_height)
    return float(texture.width) * scale, float(texture.height) * scale


def texture_visible_size(texture: arcade.Texture) -> tuple[float, float]:
    """Return the alpha-aware visible size in source pixels."""
    points = texture.hit_box_points
    if not points:
        return max(1.0, float(texture.width)), max(1.0, float(texture.height))
    return (
        max(1.0, max(point[0] for point in points) - min(point[0] for point in points)),
        max(1.0, max(point[1] for point in points) - min(point[1] for point in points)),
    )


def fit_player_texture_size(texture: arcade.Texture, sex: str, race: str,
                            job: str, pose: str, max_visible_width: float,
                            max_visible_height: float) -> tuple[float, float]:
    """Keep every pose at the identity's reviewed displayed body scale."""
    sex_dir = PLAYER_ART_SEX_DIRS.get(sex)
    race_dir = PLAYER_ART_RACE_DIRS.get(race)
    filename = PLAYER_ART_JOB_FILES.get(job)
    if not sex_dir or not race_dir or not filename:
        return fit_visible_texture_size(texture, max_visible_width, max_visible_height)
    scale = player_uniform_scale(
        sex_dir, race_dir, Path(filename).stem,
        max_visible_height, max_visible_width, pose,
    )
    return float(texture.width) * scale, float(texture.height) * scale


def combat_reaction_pose(animation: Any, target: str,
                         enemy_index: int = 0) -> str:
    """Return the target pose after impact: HP loss hurts, zero loss blocks."""
    if animation is None or not getattr(animation, "impacted", False):
        return "idle"
    attacker = getattr(animation, "attacker", "")
    is_target = (
        target == "player" and attacker == "enemy"
        or target == "enemy" and attacker == "player"
        and enemy_index == int(getattr(animation, "enemy_index", 0))
    )
    if not is_target:
        return "idle"
    return "hurt" if int(getattr(animation, "damage", 0)) > 0 else "block"


def make_log_card_skin(width: int, height: int, accent: tuple[int, int, int],
                       newest: bool) -> arcade.Texture:
    del width, height, accent, newest
    return load_ai_ui_texture("frame.card")


def make_log_scroll_skin(width: int, height: int, part: str,
                         active: bool = False) -> arcade.Texture:
    del width, height, active
    asset = "scrollbars/track.png" if part == "track" else "scrollbars/thumb.png"
    return load_ai_ui_texture(asset)


class RPGDrawingMixin:
    """提供給 RPGWindow 的所有繪圖與畫面排版功能。"""

    @staticmethod
    def display_text(value: Any) -> str:
        """Return the active-locale copy used by every drawing path.

        Game state deliberately keeps its stable Traditional Chinese values;
        localization happens only at the presentation boundary.  This also
        lets buttons and messages created by ``rpg.py`` switch language
        without duplicating locale-aware branches throughout the game logic.
        """
        return translate(str(value))

    @staticmethod
    def _route_value(item: Any, name: str, default: Any = None) -> Any:
        """Read route dataclasses and migrated dict payloads uniformly."""
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    def _journey_route_nodes(self) -> list[Any]:
        route = getattr(self, "journey_route", None)
        raw_nodes = self._route_value(route, "nodes", ())
        if isinstance(raw_nodes, dict):
            return list(raw_nodes.values())
        if isinstance(raw_nodes, (list, tuple)):
            return list(raw_nodes)
        return []

    @classmethod
    def _route_node_id(cls, node: Any) -> str:
        return str(cls._route_value(node, "id", ""))

    @classmethod
    def _route_kind_key(cls, node: Any) -> str:
        kind = cls._route_value(node, "kind", "battle")
        kind = getattr(kind, "value", kind)
        return str(kind).strip().lower().replace("-", "_")

    @staticmethod
    def route_kind_copy(kind: str) -> tuple[str, str, tuple[int, int, int]]:
        """Return compact map copy without exposing rolled combat numbers."""
        aliases = {
            "normal": "battle", "monster": "battle", "combat": "battle",
            "potion_shop": "shop", "merchant": "shop",
        }
        kind = aliases.get(kind, kind)
        return {
            "battle": ("小怪", "一般遭遇；勝利後繼續深入本章。", (184, 193, 207)),
            "elite": ("菁英", "危險的強敵；勝利後可免費選一瓶藥水。", (225, 116, 72)),
            "campfire": ("營火", "休整並從數種永久增益中選擇一項。", (228, 151, 66)),
            "shop": ("藥水商", "使用金幣補充本次旅程需要的藥水。", (78, 181, 146)),
            "boss": ("魔王", "本章最危險的決戰。", (206, 72, 75)),
        }.get(kind, ("未知", "前方仍籠罩在黑霧之中。", (159, 169, 183)))

    @staticmethod
    def rect(left: float, bottom: float, width: float, height: float,
             color: tuple[int, ...], border: tuple[int, ...] | None = None,
             border_width: int = 1) -> None:
        # ``surfaces/control.png`` contains its own perimeter.  Stretching it
        # for full-screen veils or tiny scrollbar parts silently introduced a
        # decorative frame even when ``border`` was not requested.
        fill = tuple(color[:3]) + ((color[3] if len(color) > 3 else 255),)
        arcade.draw_rect_filled(
            arcade.LBWH(left, bottom, width, height), fill,
        )
        if border:
            draw_ai_ui_frame_asset(
                "frames/container.png", left, bottom, width, height,
                tint=tuple(border[:3]), margin_ratio=.16, filled=False,
            )

    def draw_ui_frame(self, relative_path: str, left: float, bottom: float,
                      width: float, height: float, *,
                      tint: tuple[int, int, int] | None = None,
                      active: bool = False, enabled: bool = True,
                      margin_ratio: float = .18,
                      filled: bool = True) -> bool:
        draw_ai_ui_frame_asset(
            relative_path, left, bottom, width, height, tint=tint,
            active=active, enabled=enabled, margin_ratio=margin_ratio,
            filled=filled,
        )
        return True

    def framed_surface(self, left: float, bottom: float, width: float,
                       height: float, *, kind: str = "panel",
                       accent: tuple[int, int, int] | None = None,
                       enabled: bool = True, selected: bool = False,
                       alpha: int = 238) -> None:
        """Draw the shared dark-fantasy container language.

        Large panels use the structural container frame; repeated content cards
        use the quieter cloth card. Both share the same tokenised backing,
        inset shadow, material tint, and selection rule.
        """
        is_card = kind == "card"
        frame_name = "frame.card" if is_card else "frame.panel"
        inset = FRAMES.card_inset if is_card else FRAMES.panel_inset
        margin_ratio = (FRAMES.card_margin_ratio if is_card
                        else FRAMES.panel_margin_ratio)
        surface_rgb = (COLORS.surface_quiet[:3] if is_card else COLORS.surface[:3])
        surface_alpha = alpha if enabled else min(alpha, 118)
        arcade.draw_rect_filled(
            arcade.LBWH(left, bottom, width, height),
            (*surface_rgb, surface_alpha),
        )
        self.draw_ui_frame(
            frame_name, left, bottom, width, height,
            tint=accent, active=selected, enabled=enabled,
            margin_ratio=margin_ratio, filled=True,
        )
        if width > inset * 2 + 4 and height > inset * 2 + 4:
            shadow = COLORS.inner_shadow
            inner_left = left + inset
            inner_bottom = bottom + inset
            inner_width = width - inset * 2
            inner_height = height - inset * 2
            arcade.draw_rect_filled(
                arcade.LBWH(inner_left, inner_bottom + inner_height - 2,
                            inner_width, 2), shadow,
            )
            arcade.draw_rect_filled(
                arcade.LBWH(inner_left, inner_bottom, 2, inner_height), shadow,
            )
        if selected:
            divider = load_ai_ui_texture("divider.section")
            arcade.draw_texture_rect(
                divider,
                arcade.XYWH(left + width / 2, bottom + 5,
                            max(36, min(width - 24, 180)),
                            FRAMES.divider_height),
                color=Color(*(accent or COLORS.ember)), alpha=235,
            )

    def rounded_rect(self, left: float, bottom: float, width: float, height: float,
                     radius: float, color: tuple[int, ...],
                     border: tuple[int, ...] | None = None,
                     border_width: int = 1) -> None:
        """Draw a card entirely from reusable AI-painted frame textures."""
        del radius, border_width
        if width >= 120 and height >= 44:
            self.framed_surface(
                left, bottom, width, height, kind="card",
                accent=tuple(border[:3]) if border else None,
            )
        else:
            self.rect(left, bottom, width, height, color)

    def quiet_surface(self, left: float, bottom: float, width: float,
                      height: float, *, enabled: bool = True,
                      selected: bool = False, alpha: int = 205) -> None:
        """Draw only the calm AI-painted cloth centre for repeated list rows.

        Dense lists must not repeat four metal rails per entry.  The material is
        still sourced from the generated content-card anchor; only the centre
        patch is used, with a short ember marker for selection.
        """
        centre = load_ai_ui_patches("frame.card", FRAMES.card_margin_ratio)[4]
        target_ratio = max(.1, width / max(1.0, height))
        ratio_key = round(target_ratio, 2)
        fitted = _QUIET_SURFACE_CACHE.get(ratio_key)
        if fitted is None:
            source_ratio = centre.width / max(1, centre.height)
            if source_ratio > target_ratio:
                crop_height = centre.height
                crop_width = max(1, round(crop_height * target_ratio))
                crop_x = max(0, (centre.width - crop_width) // 2)
                crop_y = 0
            else:
                crop_width = centre.width
                crop_height = max(1, round(crop_width / target_ratio))
                crop_x = 0
                crop_y = max(0, (centre.height - crop_height) // 2)
            fitted = centre.crop(crop_x, crop_y, crop_width, crop_height)
            _QUIET_SURFACE_CACHE[ratio_key] = fitted
        # These are direct framebuffer colours now, not tints multiplied into
        # a nearly black texture.  Keep them genuinely dark so the replacement
        # reads as a restrained veil rather than a pale grey board.
        base_color = ((48, 35, 26) if selected else
                      (15, 21, 30) if enabled else (10, 12, 16))
        base_alpha = alpha if enabled else min(alpha, 110)
        arcade.draw_rect_filled(
            arcade.LBWH(left, bottom, width, height),
            (*base_color, base_alpha),
        )
        # A restrained pass of the new cloth anchor keeps material continuity
        # without exposing its high-frequency weave as a checkerboard.
        arcade.draw_texture_rect(
            fitted,
            arcade.XYWH(left + width / 2, bottom + height / 2, width, height),
            color=Color(*COLORS.material_tint),
            alpha=26 if enabled else 10,
        )
        # Quiet rows still belong to the same system as large panels: a hairline
        # perimeter and opposing inner highlight/shadow replace anonymous flat
        # rectangles without adding a full ornamental rail to every list item.
        outline_alpha = 112 if enabled else 55
        arcade.draw_rect_outline(
            arcade.XYWH(left + width / 2, bottom + height / 2, width, height),
            (*COLORS.line[:3], outline_alpha), 1,
        )
        if width >= 36 and height >= 20:
            arcade.draw_line(
                left + 5, bottom + height - 3, left + width - 5,
                bottom + height - 3,
                (*COLORS.line_highlight[:3], 58 if enabled else 24), 1,
            )
            arcade.draw_line(
                left + 3, bottom + 3, left + width - 3, bottom + 3,
                COLORS.inner_shadow, 2,
            )
        if selected:
            divider = load_ai_ui_texture("divider.section")
            arcade.draw_texture_rect(
                divider,
                arcade.XYWH(left + width / 2, bottom + 4,
                            min(width - 24, 150), 4),
                color=Color(*COLORS.ember), alpha=235,
            )

    def text(self, value: str, x: float, y: float, size: int = 18,
             color: tuple[int, ...] = INK, anchor_x: str = "left",
             anchor_y: str = "baseline", bold: bool = False,
             width: int | None = None, multiline: bool = False,
             max_width: float | None = None, max_height: float | None = None,
             min_size: int = 8) -> None:
        """Draw text and shrink it until it stays inside the supplied bounds."""
        value = self.display_text(value)
        scale = float(getattr(self, "ui_scale", 1.0))
        # Most body text stays at 13px or above. Dense secondary labels may use
        # 10–12px when their caller explicitly allows it; never hide meaning
        # behind an automatic ellipsis.
        min_size = max(10, min_size)
        # Latin glyphs become visibly brittle below 12 px on the packaged
        # Windows font stack. Keep meaningful English labels at the audited
        # floor; one-character badges and numeric counters may remain compact.
        if get_locale() == "EN" and re.search(r"[A-Za-z]{3}", value):
            min_size = max(12, min_size)
        fitted_size = max(round(size * scale), min_size)
        if getattr(self, "high_contrast", False) and tuple(color[:3]) == MUTED:
            color = (222, 227, 235, color[3]) if len(color) > 3 else (222, 227, 235)

        def get_label(display_value: str, draw_x: float = x, draw_y: float = y,
                      draw_color: tuple[int, ...] = color,
                      cache_variant: str = "main") -> arcade.Text:
            # Position is deliberately not part of the cache key.  Animated
            # labels used to allocate/rasterise a new Text object every frame,
            # producing cache spikes and visible edge shimmer while moving.
            key = (cache_variant, display_value, fitted_size, draw_color, anchor_x, anchor_y,
                   bold, width, multiline)
            cached = self._text_cache.get(key)
            if cached is None:
                if len(self._text_cache) >= self.TEXT_CACHE_LIMIT:
                    # Evict a small oldest generation instead of clearing the
                    # whole cache and forcing a visible rasterisation cliff.
                    evictions = max(1, self.TEXT_CACHE_LIMIT // 16)
                    for _ in range(min(evictions, len(self._text_cache))):
                        self._text_cache.pop(next(iter(self._text_cache)))
                cached = arcade.Text(
                    display_value, draw_x, draw_y, draw_color, fitted_size,
                    width=width, align="left",
                    anchor_x=anchor_x, anchor_y=anchor_y, bold=bold,
                    multiline=multiline,
                    font_name=current_font_stack(),
                )
                self._text_cache[key] = cached
            else:
                # Python dicts preserve insertion order; reinserting gives us
                # bounded LRU behaviour without another cache dependency.
                self._text_cache.pop(key)
                self._text_cache[key] = cached
                cached.x = draw_x
                cached.y = draw_y
            return cached

        while True:
            label = get_label(value)
            fits_width = max_width is None or label.content_width <= max_width
            # Arcade's content_height includes large font-leading margins
            # (13px CJK text reports about 23px). Layout limits describe the
            # intended visible glyph size, so compare against the font size.
            fits_height = max_height is None or fitted_size <= max_height
            if fits_width and fits_height:
                # One restrained dark offset is cheaper and cleaner than boxing
                # every label. It keeps copy readable over snow, parchment,
                # fire and detailed character art without adding more panels.
                get_label(value, x + 1.25, y - 1.25, (0, 0, 0, 205),
                          "shadow").draw()
                label.draw()
                return
            if fitted_size <= min_size:
                if max_width is not None and not fits_width:
                    self.ui_truncations.append((value, "文字框寬度不足"))
                overflow_width = max_width is not None and label.content_width > max_width + 1
                overflow_height = max_height is not None and label.font_size > max_height + 1
                if overflow_width or overflow_height:
                    self.ui_layout_warnings.append(
                        (value, float(label.content_width), float(label.content_height))
                    )
                get_label(value, x + 1.25, y - 1.25, (0, 0, 0, 205),
                          "shadow").draw()
                label.draw()
                return
            fitted_size -= 1

    @staticmethod
    def floating_damage_style(floating) -> str:
        if floating.shielding:
            return "shielding"
        if floating.healing:
            return "healing"
        if floating.critical:
            return "critical"
        return "damage"

    def floating_damage_value(self, floating) -> str:
        if floating.shielding:
            value = f"◆ +{floating.amount}"
        elif floating.healing:
            value = f"+{floating.amount}"
        elif floating.amount == 0:
            value = "0"
        else:
            value = f"{'暴擊 ' if floating.critical else ''}-{floating.amount}"
        return self.display_text(value)

    @staticmethod
    def floating_damage_base_size(style: str) -> int:
        return 31 if style == "critical" else 27

    def prewarm_floating_label_slot(self, style: str) -> None:
        """Create one pixel-equivalent label group outside the impact frame."""
        size = self.floating_damage_base_size(style)
        # Include both locales and every numeric/symbol glyph in the warm-up
        # string so changing the actual value only updates an existing layout.
        template = "暴擊 CRITICAL ◆ +-0123456789"
        label = arcade.Text(
            template, 0, 0, GOLD, size,
            anchor_x="center", anchor_y="center", bold=True,
            font_name=current_font_stack(),
        )
        outlines = [
            arcade.Text(
                template, dx, dy, (4, 7, 11, 230), size,
                anchor_x="center", anchor_y="center", bold=True,
                font_name=current_font_stack(),
            )
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2))
        ]
        self._floating_label_pool.append({
            "style": style,
            "label": label,
            "outlines": outlines,
            "in_use": False,
        })

    def prepare_floating_damage_label(self, floating) -> None:
        if floating.pool_slot >= 0:
            return
        style = self.floating_damage_style(floating)
        slot_index = next(
            (
                index for index, group in enumerate(self._floating_label_pool)
                if group["style"] == style and not group["in_use"]
            ),
            -1,
        )
        if slot_index < 0:
            # Overflow remains lossless. Normal play uses the pre-warmed pool;
            # simultaneous reflect/DOT/shield chains may grow it temporarily.
            self.prewarm_floating_label_slot(style)
            slot_index = len(self._floating_label_pool) - 1
        group = self._floating_label_pool[slot_index]
        group["in_use"] = True
        floating.pool_slot = slot_index
        floating.label = group["label"]
        floating.outline_labels = group["outlines"]

        value = self.floating_damage_value(floating)
        size = self.floating_damage_base_size(style)
        labels = [floating.label, *floating.outline_labels]
        for label in labels:
            label.text = value
            label.font_size = size
        while floating.label.content_width > 230 and size > 13:
            size -= 2
            for label in labels:
                label.font_size = size

    def release_floating_damage_label(self, floating) -> None:
        slot = getattr(floating, "pool_slot", -1)
        if 0 <= slot < len(self._floating_label_pool):
            self._floating_label_pool[slot]["in_use"] = False
        floating.pool_slot = -1
        floating.label = None
        floating.outline_labels = []

    def prime_attack_floating_label(self) -> None:
        """Lay out one invisible outline layer per wind-up frame.

        Pyglet defers glyph layout until ``draw``. Spreading the five
        pixel-equivalent layers across the 170 ms attack wind-up removes the
        single impact-frame cliff without changing visible timing or styling.
        """
        animation = getattr(self, "attack_animation", None)
        floating = getattr(animation, "floating", None)
        if floating is None or animation.impacted:
            return
        labels = [*floating.outline_labels, floating.label]
        index = int(getattr(animation, "floating_prime_index", 0))
        if index >= len(labels):
            return
        label = labels[index]
        if label is None:
            return
        original_x, original_y, original_color = label.x, label.y, label.color
        label.x = -512
        label.y = -512
        label.color = (0, 0, 0, 0)
        label.draw()
        label.x, label.y, label.color = original_x, original_y, original_color
        animation.floating_prime_index = index + 1

    def panel(self, left: float, bottom: float, width: float, height: float,
              title: str = "") -> None:
        self.framed_surface(left, bottom, width, height, kind="panel",
                            accent=COLORS.brass, alpha=238)
        divider = load_ai_ui_texture("divider.section")
        arcade.draw_texture_rect(
            divider,
            arcade.XYWH(left + width / 2, bottom + height - 3,
                        max(80, width - 48), FRAMES.divider_height),
            color=Color(*COLORS.brass), alpha=155,
        )
        if title:
            self.text(title, left + FRAMES.title_inset_x,
                      bottom + height - FRAMES.title_inset_y, 17, GOLD,
                      "left", "center", True,
                      max_width=max(20, width - 68), max_height=22)

    def bar(self, x: float, y: float, width: float, value: float, maximum: int,
            color: tuple[int, ...], label: str,
            actual_value: float | None = None) -> None:
        displayed_ratio = max(0, min(1, value / max(1, maximum)))
        actual = value if actual_value is None else actual_value
        actual_ratio = max(0, min(1, actual / max(1, maximum)))
        bar_height = 25.0
        interior_width = max(0.0, width - 12)
        shield_meter = tuple(color[:3]) == BLUE
        fill_path = "meter.shield" if shield_meter else "meter.hp"
        fill = load_tight_ai_ui_texture(fill_path, 1)

        # A recessed track and a distinct delayed-loss layer make damage
        # readable even when the framed PNG has a highly textured centre.
        self.rect(x + 5, y + 5, width - 10, bar_height - 10,
                  (5, 10, 16, 232), (112, 126, 142, 110), 1)
        if displayed_ratio > actual_ratio + .002:
            trail_width = interior_width * displayed_ratio
            arcade.draw_texture_rect(
                fill, arcade.XYWH(x + 6 + trail_width / 2,
                                  y + bar_height / 2,
                                  trail_width, bar_height - 10),
                color=Color(*(135, 203, 255) if shield_meter else (238, 169, 76)),
                alpha=218,
            )
            main_ratio = actual_ratio
        else:
            # Healing grows smoothly instead of jumping to the target value.
            main_ratio = displayed_ratio
        fill_width = interior_width * main_ratio
        if fill_width > 0:
            arcade.draw_texture_rect(
                fill, arcade.XYWH(x + 6 + fill_width / 2,
                                  y + bar_height / 2,
                                  fill_width, bar_height - 10),
                color=Color(*(74, 151, 224) if shield_meter else (220, 61, 67)),
            )
            self.rect(x + 8, y + bar_height - 7,
                      max(0, fill_width - 4), 1,
                      (220, 241, 255, 92) if shield_meter
                      else (255, 213, 191, 82))
        frame = load_ai_ui_texture("meter.frame")
        arcade.draw_texture_rect(frame, arcade.XYWH(x + width / 2,
                                                    y + bar_height / 2,
                                                    width, bar_height))
        label_color = (188, 224, 255) if shield_meter else (255, 239, 226)
        self.text(label, x + width / 2, y + bar_height / 2, 12,
                  label_color, "center", "center", True,
                  max_width=width - 44, max_height=16, min_size=11)

    def shield_bar(self, x: float, y: float, width: float, value: float,
                   maximum: int, actual_value: int | None = None) -> None:
        shield = max(0, value)
        actual = round(shield) if actual_value is None else actual_value
        self.bar(x, y, width, shield, max(1, maximum, shield, actual), BLUE,
                 f"◆ {max(0, actual)}", actual_value=actual)

    def draw_combat_hit_flash(self, texture: arcade.Texture,
                              rect: arcade.XYWH, alpha: int) -> None:
        """用短暫加亮的原輪廓做受擊閃白，不需要額外的角色遮罩資產。"""
        if alpha <= 0:
            return
        previous_blend = self.ctx.blend_func
        try:
            self.ctx.blend_func = self.ctx.BLEND_ADDITIVE
            arcade.draw_texture_rect(texture, rect, alpha=alpha)
        finally:
            self.ctx.blend_func = previous_blend

    def draw_button(self, button: Any) -> None:
        """Draw one readable control surface with consistent interaction states.

        Text controls always keep a quiet backing surface. This protects labels
        from detailed scene art and lets hover/focus use the whole hit target
        instead of a decorative line that reads like an accidental underline.
        """
        # Route nodes use the map's status-aware renderer.  Their Button still
        # owns mouse hit testing and hover state, but drawing it again here
        # would cover the node marker with a generic rectangular control.
        if getattr(button, "group", "") == "route-node":
            return
        talent_rank = self.class_talent_rank(button.talent_id) if button.talent_id else 0
        learned_talent = talent_rank > 0
        needs_attention = bool(getattr(button, "attention", False)) and button.enabled
        visually_enabled = button.enabled or learned_talent
        focused = (bool(self.buttons) and self.focused_button_index >= 0
                   and button is self.buttons[
                       min(self.focused_button_index, len(self.buttons) - 1)
                   ])
        hovered = button is self.hovered and visually_enabled
        pressed = button is getattr(self, "pressed_button", None) and visually_enabled
        selected = bool(getattr(button, "selected", False)) or learned_talent
        loading = bool(getattr(button, "loading", False))
        error = bool(getattr(button, "error", False))
        state = resolve_control_state(
            enabled=visually_enabled,
            hovered=hovered,
            pressed=pressed,
            selected=selected or needs_attention,
            focused=focused,
            loading=loading,
            error=error,
        )
        visual = control_visual(state)
        active = state not in {ControlState.DEFAULT, ControlState.DISABLED}
        role = getattr(button, "role", "normal")
        if role == "normal":
            if button.label in {"開始遊戲", "建立角色", "繼續旅程", "確認名字",
                                "繼續旅程", "重玩"}:
                role = "primary"
            elif button.label in {"關閉遊戲", "確認返回", "重置天賦"}:
                role = "danger"
            elif button.label in {"回到主頁", "返回", "上一步", "離開藥水商"}:
                role = "secondary"
        icon_path = str(getattr(button, "icon", ""))
        icon_only = bool(getattr(button, "icon_only", False))
        battle_icon_button = self.scene == self.Scene.BATTLE and icon_only
        decorated = bool(getattr(button, "decorated", True))
        presentation = getattr(button, "presentation", "auto")
        persistent_surface = bool(
            (icon_only and not battle_icon_button) or presentation == "surface"
        )
        text_surface = bool(str(button.label).strip()) and not icon_only
        if ((text_surface or (decorated and persistent_surface))
                and not battle_icon_button):
            surface = load_ai_ui_texture("surface.material")
            if role == "danger" and state not in {ControlState.PRESSED, ControlState.ERROR}:
                surface_color = COLORS.danger
                surface_alpha = 118 if not active else 164
            elif active:
                surface_color, surface_alpha = visual.surface, visual.surface_alpha
            else:
                surface_color = COLORS.surface_quiet[:3]
                surface_alpha = 164 if visually_enabled else 92
            # Text is always an actionable control, including secondary and
            # previously undecorated labels.  Lay down an opaque minimum base
            # before the material pass so detailed art can never erase its
            # affordance.
            # Talent nodes already have a content-card underneath. Their label
            # plate stays readable but deliberately lighter so the node frame
            # and material remain visible around and through it.
            minimum_alpha = (
                150 if button.talent_id else 184
            ) if visually_enabled else 104
            surface_alpha = max(surface_alpha, minimum_alpha)
            arcade.draw_rect_filled(
                arcade.XYWH(button.x, button.y, button.width, button.height),
                (*surface_color, surface_alpha),
            )
            arcade.draw_texture_rect(
                surface,
                arcade.XYWH(button.x, button.y, button.width, button.height),
                color=Color(*COLORS.material_tint),
                alpha=(62 if button.talent_id else 96) if visually_enabled else 45,
            )
            outline_color = visual.marker if active else COLORS.line[:3]
            arcade.draw_rect_outline(
                arcade.XYWH(button.x, button.y, button.width, button.height),
                (*outline_color, 220 if active else 125),
                2 if active else 1,
            )
        elif (not decorated and active and button.width >= 100
              and button.height >= 100):
            # Image cards already draw their own backing before their artwork.
            # Keep interaction feedback without darkening the character image.
            arcade.draw_rect_outline(
                arcade.XYWH(button.x, button.y, button.width, button.height),
                Color(*visual.marker), 2,
            )
        icon_texture = None
        if icon_path:
            if battle_icon_button:
                slot = load_ai_ui_texture("frame.skill_slot")
                slot_color = ((91, 101, 114) if not visually_enabled
                              else visual.marker if active else (140, 153, 167))
                arcade.draw_texture_rect(
                    slot, arcade.XYWH(button.x, button.y, 68, 68),
                    color=Color(*slot_color),
                    alpha=116 if not visually_enabled else (255 if active else 205),
                )
            icon_size = int(max(24, min(button.height - 10,
                                        44 if battle_icon_button
                                        else (46 if icon_only else 34))))
            slice_icon_map = {
                "icons/talents/warrior/weapon_mastery.png": "slash",
                "icons/talents/warrior/shield_mastery.png": "guard",
                "icons/potions/universal.png": "potion_bag",
            }
            slice_icon_name = slice_icon_map.get(icon_path) if battle_icon_button else None
            shop_potion_icon = (self.scene == self.Scene.SHOP
                                and icon_path.startswith("icons/potions/"))
            icon_texture = (
                load_context_icon(slice_icon_name)
                if slice_icon_name else
                load_tight_ai_ui_texture(icon_path, 2)
                if battle_icon_button else
                load_tight_ai_ui_texture(icon_path, 3)
                if shop_potion_icon else
                load_ai_ui_icon(icon_path, icon_size, 1.0)
            )
            if icon_texture is not None:
                icon_x = button.x if icon_only else button.x - button.width / 2 + 33
                icon_y = button.y + (1 if pressed else (0 if battle_icon_button else 2))
                draw_width, draw_height = (
                    fit_texture_size(icon_texture, icon_size, icon_size)
                    if battle_icon_button or shop_potion_icon
                    else (icon_size, icon_size)
                )
                arcade.draw_texture_rect(
                    icon_texture, arcade.XYWH(icon_x, icon_y,
                                              draw_width, draw_height),
                    alpha=255 if visually_enabled else 82,
                )
                # A restrained second pass lifts dark AI icons without adding glow.
                if battle_icon_button and visually_enabled:
                    arcade.draw_texture_rect(
                        icon_texture, arcade.XYWH(icon_x, icon_y,
                                                  draw_width, draw_height),
                        alpha=48 if active else 28,
                    )
        horizontal_padding = (LAYOUT.compact_control_padding_x
                              if button.width < 180 else LAYOUT.control_padding_x)
        label_max_width = max(12, button.width - horizontal_padding * 2)
        has_sub_label = bool(getattr(button, "sub_label", ""))
        external_sub_label = self.scene == self.Scene.SETTINGS and has_sub_label
        if icon_only:
            if getattr(button, "badge", ""):
                badge_x = button.x + button.width / 2 - 11
                badge_y = button.y - button.height / 2 + 11
                badge = load_ai_ui_texture("icons/markers/badge_round.png")
                arcade.draw_texture_rect(badge, arcade.XYWH(badge_x, badge_y, 22, 22))
                self.text(str(button.badge), badge_x, badge_y, 10, INK,
                          "center", "center", True, max_width=16,
                          max_height=13, min_size=8)
        else:
            text_x = button.x + (18 if icon_texture is not None else 0)
            if icon_texture is not None:
                label_max_width = max(44, label_max_width - 52)
            label_y = button.y + (1 if external_sub_label else (10 if has_sub_label else 1))
            single_label_height = max(13, button.height - (12 if button.height < 34 else 22))
            symbol_label = button.label in {"♂", "♀"}
            if symbol_label:
                label_y += 4
            label_color = (
                GOLD if learned_talent or needs_attention or role == "primary"
                else COLORS.danger if role == "danger" and button.enabled
                else visual.text
            )
            label_size = (
                30 if symbol_label else
                TYPE.control if external_sub_label else
                TYPE.body if has_sub_label else TYPE.control
            )
            label_min_size = (
                22 if symbol_label else
                13 if external_sub_label else
                12 if has_sub_label else 13
            )
            translated_label = self.display_text(button.label)
            can_use_two_lines = (
                not symbol_label and not has_sub_label and button.height >= 40
                and self.measure_text_width(
                    translated_label, label_min_size, True
                ) > label_max_width
            )
            if can_use_two_lines:
                # Long English control labels retain a proper button face and
                # wrap at spaces.  They are never squeezed below the 12/13 px
                # control floor or allowed to spill through the frame.
                lines, fitted_size = self.fitted_wrapped_lines(
                    translated_label, label_max_width, label_size,
                    min_size=label_min_size, max_lines=2,
                )
                spacing = max(15, fitted_size + 3)
                first_y = label_y + visual.y_offset + (len(lines) - 1) * spacing / 2
                for line_index, line in enumerate(lines):
                    self.text(
                        line, text_x, first_y - line_index * spacing,
                        fitted_size, label_color, "center", "center", True,
                        max_width=label_max_width, max_height=spacing,
                        min_size=fitted_size,
                    )
            else:
                self.text(button.label, text_x, label_y + visual.y_offset,
                          label_size, label_color,
                          "center", "center", True,
                          max_width=label_max_width,
                          max_height=40 if symbol_label else
                          (single_label_height if external_sub_label else
                           (16 if has_sub_label else single_label_height)),
                          min_size=label_min_size)
            if has_sub_label:
                sub_y = (button.y - button.height / 2 - 17
                         if external_sub_label else button.y - 11)
                self.text(button.sub_label, text_x, sub_y, TYPE.secondary,
                          MUTED if button.enabled else (105, 110, 120),
                          "center", "center", False,
                          max_width=(button.width if external_sub_label else label_max_width),
                          max_height=17, min_size=12)
    def draw_potion_menu_backdrop(self) -> None:
        bounds = getattr(self, "potion_menu_bounds", None)
        if not bounds:
            return
        left, bottom, width, height = bounds
        self.quiet_surface(left, bottom, width, height, alpha=236)

    def button_tooltip_text(self, button: Any) -> str:
        if not button.enabled and getattr(button, "disabled_reason", ""):
            reason = f"目前無法使用：{button.disabled_reason}"
            return f"{button.tooltip}\n{reason}" if button.tooltip else reason
        if button.tooltip:
            return button.tooltip
        label = str(button.label)
        clean = label.split("｜", 1)[0].split(" CD", 1)[0].replace(" 已用", "")
        if "天賦" in clean:
            return "有可用天賦點時，進入天賦頁強化職業能力。"
        if clean.startswith("藥水 x"):
            return "展開藥水清單；同一種藥水每回合只能喝一瓶。"
        if clean.startswith("金幣 +"):
            dwarf_bonus = ("；尋金本能已將金幣加倍。"
                           if self.player.race == "矮人" else "。")
            return f"在營火整理戰利品，獲得顯示的金幣{dwarf_bonus}"
        exact = {
            "開始遊戲": "建立新角色並開始旅程。",
            "建立角色": "開始建立新角色。",
            "讀取存檔": "進入讀取存檔畫面。",
            "關閉遊戲": "關閉遊戲視窗。",
            "回到主頁": "返回主頁。",
            "留在旅途中": "取消返回，繼續目前旅程。",
            "確認返回": "結束本次旅程並返回主頁。",
            "確認名字": "使用目前輸入的名稱繼續建立角色。",
            "繼續旅程": "前往下一段旅程。",
            "存檔 / 讀檔": "管理目前旅程的存檔與讀檔。",
            "藥水商": "進入藥水商購買藥水。",
            "重置天賦": "返還已投入的天賦點。",
            "返回": "返回上一個畫面。",
            "關閉": "關閉目前面板。",
            "離開藥水商": "離開藥水商，回到旅程。",
            "重玩": "重新開始一輪遊戲。",
            "男性": "選擇男性，防禦增加 5。",
            "女性": "選擇女性，暴擊增加 1%。",
            "獸人": "選擇獸人，血量上限增加 10。",
            "人類": "選擇人類，攻擊增加 5。",
            "矮人": "選擇矮人，防禦增加 5。",
            "精靈": "選擇精靈，暴擊增加 1%。",
            "上一組職業": "切換到上一組職業。",
            "下一組職業": "切換到下一組職業。",
            "恢復 50% 血量": "在營火回血 50%，下一場戰鬥獲得護盾。",
            "恢復 33% 血量": "在營火回血 33%。",
            "攻擊 +5%": "永久增加 5% 攻擊。",
            "攻擊 +3%": "永久增加 3% 攻擊。",
            "防禦 +5%": "永久增加 5% 防禦。",
            "防禦 +3%": "永久增加 3% 防禦。",
            "存檔": "把目前旅程寫入這個存檔槽。",
            "讀檔": "讀取這個存檔槽的旅程。",
            "讀取": "讀取這個存檔槽的旅程。",
        }
        if clean in {job for job, _bonus in self.JOBS}:
            return self.job_summary(clean)
        if clean.startswith("暴擊 +"):
            return "永久增加角色的暴擊率。"
        # Repeating a control's label in a tooltip adds noise without helping
        # the decision. Unknown controls therefore opt out of generic copy.
        return exact.get(clean, "")

    def draw_hover_tooltip(self) -> None:
        if (self.scene == self.Scene.BATTLE
                and getattr(self, "hovered_enemy_intent_index", None) is not None):
            # Enemy move details own the hover layer while the pointer is over
            # an enemy, so skill focus help cannot overlap the intent card.
            return
        target = self.hovered
        if target is None and self.buttons and self.focused_button_index >= 0:
            focused = self.buttons[min(self.focused_button_index, len(self.buttons) - 1)]
            # Keyboard/gamepad users still need descriptions for controls whose
            # labels are hidden and for dense talent nodes. Plain text buttons
            # are already self-describing and should not open an unsolicited
            # tooltip on every page.
            if (getattr(focused, "icon_only", False) or focused.talent_id
                    or self.scene == self.Scene.SHOP):
                target = focused
        if not target:
            return
        tooltip = self.button_tooltip_text(target)
        if not tooltip:
            return
        is_talent_tip = self.scene == self.Scene.TALENT and bool(target.talent_id)
        raw_lines = tooltip.splitlines()
        if not raw_lines:
            return
        if is_talent_tip:
            title = raw_lines[0]
            # English talent descriptions carry longer rank clauses and an
            # availability sentence. Give them a useful reading measure so
            # words do not form a tall, fragmented tooltip column.
            width = 520
            talent_rank = self.class_talent_rank(target.talent_id)
            styled_lines = []
            for point, detail in enumerate(raw_lines[1:], start=1):
                detail_color = GOLD if point <= talent_rank else MUTED
                wrapped = self.wrap_text_hanging(
                    detail, width - 88, 12
                )
                styled_lines.extend(
                    (line, detail_color, indent) for line, indent in wrapped
                )
            title_color = GOLD if talent_rank > 0 else MUTED
        else:
            title = ""
            measured = max(self.measure_text_width(line, 12) for line in raw_lines)
            width = max(220, min(420, measured + 74))
            lines = []
            for raw_line in raw_lines:
                lines.extend(self.wrap_text_pixels(
                    raw_line, width - 72, 12, single_line_tolerance=.02
                ))
            styled_lines = [(line, INK, 0.0) for line in lines]
            title_color = GOLD
        # AI frames have a thick ornamental rim. Keep text inside the safe
        # centre instead of positioning it against the outer texture bounds.
        line_spacing = 23 if is_talent_tip else 24
        top_padding = 26
        bottom_padding = 20
        title_block = 31 if title else 0
        height = top_padding + title_block + len(styled_lines) * line_spacing + bottom_padding
        battle_icon_tip = (self.scene == self.Scene.BATTLE
                           and bool(getattr(target, "icon_only", False)))
        if battle_icon_tip:
            left = max(24, min(SCREEN_WIDTH - width - 24,
                               target.x - width / 2))
            bottom = max(132, target.y + target.height / 2 + 12)
        else:
            left = max(24, min(SCREEN_WIDTH - width - 24, target.x - width / 2))
            bottom = target.y + target.height / 2 + 12
            if bottom + height > SCREEN_HEIGHT - 18:
                bottom = target.y - target.height / 2 - height - 12
            bottom = max(18, min(SCREEN_HEIGHT - height - 18, bottom))
        self.quiet_surface(left, bottom, width, height, alpha=242)
        content_left = left + 36
        content_width = width - 72
        if title:
            self.text(title, content_left, bottom + height - top_padding, 13, title_color,
                      anchor_y="center", bold=True,
                      max_width=content_width, max_height=22)
        if title:
            first_line_y = bottom + height - top_padding - title_block
        else:
            # Centre short one/two-line hints as a block; using a fixed
            # top-origin was what made them appear glued to the upper rim.
            first_line_y = (
                bottom + height / 2
                + (len(styled_lines) - 1) * line_spacing / 2
            )
        for index, (line, line_color, indent) in enumerate(styled_lines):
            line_width = content_width - indent
            measured_width = self.measure_text_width(line, 12)
            if (line and line[-1] in CJK_NO_LINE_START
                    and measured_width <= line_width + 16):
                line_width = measured_width
            self.text(line, content_left + indent,
                      first_line_y - index * line_spacing, 12, line_color,
                      anchor_y="center", max_width=line_width,
                      max_height=22, min_size=12)

    @staticmethod
    def should_record_log(message: str) -> bool:
        keep_phrases = (
            "開始旅程", "存檔", "讀取", "損毀", "寫入失敗",
            "購買成功", "喝下",
            "倒下", "搜出", "DEATH", "過關", "通關",
            "抵達第", "天賦點", "重置了", "副職業", "點亮", "分身",
            "沒有明顯變化", "沒有找到", "作弊調整",
            "血量上限", "攻擊 ", "防禦 ", "暴擊 ", "金幣 ",
            "護盾 +", "恢復 ",
        )
        return any(phrase in message for phrase in keep_phrases)

    def log(self, message: str, *, record: bool | None = None) -> None:
        if self.scene == self.Scene.EVENT:
            self.event_messages.append(message)
        if self.scene == self.Scene.BATTLE:
            self.combat_messages.append(message)
            self.combat_messages = self.combat_messages[-24:]
        if record is None:
            record = self.should_record_log(message)
        if not record:
            return
        if self.log_scroll > 0:
            self.log_scroll += 1
        self.messages.append(message)
        limit = getattr(self, "LOG_RECORD_LIMIT", 12)
        self.messages = self.messages[-limit:]
        self.log_scroll = min(self.log_scroll, max(0, len(self.messages) - 1))

    def measure_text_width(self, value: str, size: int = 11,
                           bold: bool = False) -> float:
        value = self.display_text(value)
        key = (value, size, bold)
        measured = self._measure_cache.get(key)
        if measured is None:
            if len(self._measure_cache) >= self.MEASURE_CACHE_LIMIT:
                evictions = max(1, self.MEASURE_CACHE_LIMIT // 16)
                for _ in range(min(evictions, len(self._measure_cache))):
                    self._measure_cache.pop(next(iter(self._measure_cache)))
            label = arcade.Text(
                value, 0, 0, INK, size, bold=bold,
                font_name=current_font_stack(),
            )
            measured = label.content_width
            self._measure_cache[key] = measured
        else:
            self._measure_cache.pop(key)
            self._measure_cache[key] = measured
        return measured

    @staticmethod
    def _latin_break_units(paragraph: str) -> list[str]:
        """Return whitespace-delimited Latin words for safe line wrapping.

        Hyphenated names, slash-separated class names, contractions, numbers,
        and em-dash compounds are indivisible.  This intentionally trades a
        little unused line width for the much more important guarantee that an
        English word is never cut between two lines.
        """
        return [
            (" " if index else "") + match.group(0)
            for index, match in enumerate(re.finditer(r"\S+", paragraph))
        ]

    def _wrap_latin_paragraph(self, paragraph: str, max_width: float,
                              size: int) -> list[str]:
        """Wrap translated English copy without splitting a word."""
        lines: list[str] = []
        current = ""
        for unit in self._latin_break_units(paragraph):
            candidate = current + unit
            if current and self.measure_text_width(candidate, size) > max_width:
                lines.append(current.rstrip())
                current = unit.lstrip()
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
        return lines or [" "]

    def wrap_text_pixels(self, value: str, max_width: float,
                         size: int = 11,
                         single_line_tolerance: float = 0.0) -> list[str]:
        """Wrap CJK and Latin text by rendered width while preserving each record."""
        value = self.display_text(value)
        lines: list[str] = []
        for paragraph in value.splitlines() or [""]:
            if (paragraph and single_line_tolerance > 0
                    and self.measure_text_width(paragraph, size)
                    <= max_width * (1 + single_line_tolerance)):
                lines.append(paragraph)
                continue
            if get_locale() == "EN":
                lines.extend(self._wrap_latin_paragraph(paragraph, max_width, size))
                continue
            paragraph_lines: list[str] = []
            current = ""
            for character in paragraph:
                candidate = current + character
                if current and self.measure_text_width(candidate, size) > max_width:
                    if character in CJK_NO_LINE_START:
                        # Keep punctuation with the preceding glyph without
                        # letting that line exceed the requested width.
                        head = current[:-1].rstrip()
                        if head:
                            paragraph_lines.append(head)
                        current = current[-1:] + character
                    else:
                        paragraph_lines.append(current.rstrip())
                        current = character.lstrip()
                else:
                    current = candidate
            if current:
                paragraph_lines.append(current)
            if not paragraph_lines:
                paragraph_lines.append(" ")
            lines.extend(paragraph_lines)
        return lines

    def fitted_wrapped_lines(self, value: str, max_width: float,
                             size: int = 12, *, min_size: int = 12,
                             max_lines: int | None = None
                             ) -> tuple[list[str], int]:
        """Fit a translated paragraph without clipping or splitting words.

        Informational copy should wrap before it shrinks.  When a caller has a
        fixed-height region, this helper may reduce the font only as far as the
        explicit minimum to fit ``max_lines``; it never discards overflow
        lines.  The returned size lets drawing and height calculations share
        the exact same decision.
        """
        minimum = max(10, min_size)
        current_size = max(size, minimum)
        while True:
            lines = self.wrap_text_pixels(value, max_width, current_size)
            words_fit = all(
                self.measure_text_width(line, current_size) <= max_width + 1
                for line in lines
            )
            line_count_fits = max_lines is None or len(lines) <= max_lines
            if (words_fit and line_count_fits) or current_size <= minimum:
                return lines, current_size
            current_size -= 1

    def draw_text_block(self, value: str, x: float, center_y: float,
                        max_width: float, size: int = 12,
                        color: tuple[int, ...] = INK, *,
                        line_spacing: float | None = None,
                        max_lines: int | None = None,
                        min_size: int = 12,
                        anchor_x: str = "center", bold: bool = False
                        ) -> int:
        """Draw a vertically centred wrapped block and return its line count."""
        lines, fitted_size = self.fitted_wrapped_lines(
            value, max_width, size, min_size=min_size, max_lines=max_lines
        )
        spacing = line_spacing or max(18.0, fitted_size + 7.0)
        first_y = center_y + (len(lines) - 1) * spacing / 2
        for index, line in enumerate(lines):
            self.text(
                line, x, first_y - index * spacing, fitted_size, color,
                anchor_x, "center", bold, max_width=max_width,
                max_height=spacing, min_size=fitted_size,
            )
        return len(lines)

    def pack_status_lines(self, values: list[str], max_width: float,
                          size: int, separator: str = "｜") -> list[str]:
        """Pack localized status labels by rendered width instead of count."""
        lines: list[str] = []
        current = ""
        for value in values:
            candidate = value if not current else f"{current}{separator}{value}"
            if current and self.measure_text_width(candidate, size, True) > max_width:
                lines.append(current)
                current = value
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def wrap_text_hanging(self, value: str, max_width: float,
                          size: int = 11,
                          single_line_tolerance: float = 0.0
                          ) -> list[tuple[str, float]]:
        """Wrap a labelled line and align continuations below its body text."""
        value = self.display_text(value)
        if (value and single_line_tolerance > 0
                and self.measure_text_width(value, size)
                <= max_width * (1 + single_line_tolerance)):
            return [(value, 0.0)]

        separator = value.find("：")
        if separator < 0:
            separator = value.find(":")
        if separator < 0:
            return [(line, 0.0) for line in self.wrap_text_pixels(value, max_width, size)]

        prefix = value[:separator + 1]
        body = value[separator + 1:]
        indent = self.measure_text_width(prefix, size)
        if get_locale() == "EN":
            body = body.strip()
            # English labels are wider than their CJK counterparts. Cap the
            # hanging indent so the body retains a useful measure while every
            # line still starts on a clear, consistent column.
            indent = min(self.measure_text_width(prefix + " ", size), max_width * .38)
            continuation_width = max(1.0, max_width - indent)
            wrapped_latin: list[tuple[str, float]] = []
            current = prefix
            for unit_index, unit in enumerate(self._latin_break_units(body)):
                if unit_index == 0:
                    unit = " " + unit
                line_indent = 0.0 if not wrapped_latin else indent
                line_width = max_width if not wrapped_latin else continuation_width
                candidate = current + unit
                if current and self.measure_text_width(candidate, size) > line_width:
                    wrapped_latin.append((current.rstrip(), line_indent))
                    current = unit.lstrip()
                else:
                    current = candidate
            if current:
                wrapped_latin.append(
                    (current.rstrip(), 0.0 if not wrapped_latin else indent)
                )
            return wrapped_latin or [(prefix, 0.0)]
        continuation_width = max(1.0, max_width - indent)
        wrapped: list[tuple[str, float]] = []
        current = prefix

        for character in body:
            line_indent = 0.0 if not wrapped else indent
            line_width = max_width if not wrapped else continuation_width
            candidate = current + character
            if current and self.measure_text_width(candidate, size) > line_width:
                if character in CJK_NO_LINE_START:
                    head = current[:-1].rstrip()
                    if head:
                        wrapped.append((head, line_indent))
                    current = current[-1:] + character
                else:
                    wrapped.append((current.rstrip(), line_indent))
                    current = character.lstrip()
            else:
                current = candidate

        if current:
            wrapped.append((current, 0.0 if not wrapped else indent))
        if not wrapped:
            wrapped.append((prefix, 0.0))
        return wrapped

    @staticmethod
    def log_card_style(message: str) -> tuple[str, tuple[int, int, int]]:
        if any(word in message for word in ("倒下", "GAME")):
            return "戰", (216, 76, 65)
        if any(word in message for word in ("詛咒", "劇毒", "毒火", "失去", "失敗", "不足", "GAME")):
            return "危", (180, 68, 126)
        if any(word in message for word in ("恢復", "靈藥", "聖輝", "血量")):
            return "癒", (70, 174, 119)
        if any(word in message for word in ("獲得", "增加", "升級", "金幣", "購買", "+", "搜出")):
            return "獲", (231, 177, 72)
        if any(word in message for word in ("藥水商", "商人", "龍牙", "玄鐵", "星眼")):
            return "市", (169, 91, 196)
        return "旅", (70, 137, 196)

    def log_badge_text(self, value: str) -> str:
        """Keep localized log categories inside their intentionally tiny badge."""
        displayed = self.display_text(value).strip()
        if get_locale() == "EN" and len(displayed) > 1:
            return displayed[0]
        return displayed

    def prepared_log_cards(self, text_width: float = 220,
                           messages: list[str] | None = None
                           ) -> list[tuple[str, list[str], tuple[int, int, int], int]]:
        text_size = max(10, round(11 * float(getattr(self, "ui_scale", 1.0))))
        source = self.messages if messages is None else messages
        cache = getattr(self, "_log_layout_cache", None)
        if cache is None:
            cache = self._log_layout_cache = {}
        cache_key = (
            "plain", tuple(source), get_locale(), round(text_width, 2),
            text_size,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            cache.pop(cache_key)
            cache[cache_key] = cached
            return cached

        cards: list[tuple[str, list[str], tuple[int, int, int], int]] = []
        for message in reversed(source):
            lines = self.wrap_text_pixels(message, text_width, text_size)
            icon, accent = self.log_card_style(message)
            cards.append((icon, lines, accent, max(44, 22 + len(lines) * 20)))
        if len(cache) >= 32:
            cache.pop(next(iter(cache)))
        cache[cache_key] = cards
        return cards

    def prepared_hanging_log_cards(
            self, messages: list[str], text_width: float, text_size: int
            ) -> list[tuple[str, list[tuple[str, float]], tuple[int, int, int], int]]:
        """Prepare the expanded combat log once per content/layout revision."""
        cache = getattr(self, "_log_layout_cache", None)
        if cache is None:
            cache = self._log_layout_cache = {}
        cache_key = (
            "hanging", tuple(messages), get_locale(), round(text_width, 2),
            text_size,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            cache.pop(cache_key)
            cache[cache_key] = cached
            return cached

        cards: list[
            tuple[str, list[tuple[str, float]], tuple[int, int, int], int]
        ] = []
        for message in reversed(messages):
            lines = self.wrap_text_hanging(message, text_width, text_size)
            icon, accent = self.log_card_style(message)
            cards.append((icon, lines, accent, max(46, 24 + len(lines) * 21)))
        if len(cache) >= 32:
            cache.pop(next(iter(cache)))
        cache[cache_key] = cards
        return cards

    @staticmethod
    def max_log_scroll(cards: list[tuple[str, list[str], tuple[int, int, int], int]],
                       available_height: float = 382) -> int:
        used_height = 0.0
        oldest_page_count = 0
        for _icon, _lines, _accent, card_height in reversed(cards):
            next_height = card_height + (5 if oldest_page_count else 0)
            if used_height + next_height > available_height:
                break
            used_height += next_height
            oldest_page_count += 1
        return max(0, len(cards) - oldest_page_count)

    def visible_log_cards(self, text_width: float = 220,
                          available_height: float = 382,
                          messages: list[str] | None = None,
                          prepared: list[
                              tuple[str, list[str], tuple[int, int, int], int]
                          ] | None = None,
                          ) -> list[tuple[str, list[str], tuple[int, int, int], int]]:
        if prepared is None:
            prepared = self.prepared_log_cards(text_width, messages)
        maximum = self.max_log_scroll(prepared, available_height)
        self.log_scroll = max(0, min(self.log_scroll, maximum))
        cards: list[tuple[str, list[str], tuple[int, int, int], int]] = []
        used_height = 0.0
        for icon, lines, accent, card_height in prepared[self.log_scroll:]:
            next_height = card_height + (5 if cards else 0)
            if used_height + next_height > available_height:
                break
            cards.append((icon, lines, accent, card_height))
            used_height += next_height
        return cards

    def activity_canvas(self, texture: arcade.Texture, title: str) -> None:
        # The texture itself is submitted by ``draw_background_batch`` with
        # the persistent main backdrop before scene content is rendered.
        del texture
        # Full-screen scenes preserve the artwork. Size the quiet title tag
        # from translated copy so wider English names such as POTION MERCHANT
        # remain inside the material instead of floating past its edge.
        display_title = self.display_text(title)
        title_width = max(
            200.0,
            min(340.0, self.measure_text_width(display_title, 15, True) + 52.0),
        )
        title_left = 42.0
        self.quiet_surface(title_left, 651, title_width, 34, alpha=178)
        self.text(display_title, title_left + title_width / 2, 668, 15, INK,
                  "center", "center", True,
                  max_width=title_width - 34, max_height=20, min_size=11)

    @staticmethod
    def battle_background_stage(level: int) -> int:
        if level >= 21:
            return 5
        return min(4, 1 + max(0, level - 1) // 5)

    def battle_canvas(self) -> None:
        """One continuous arena with a subdued, integrated action dock."""
        stage = self.battle_background_stage(self.player.lv)
        stage_names = {
            1: "邊境堡壘", 2: "陷落城塞", 3: "古戰大教堂",
            4: "深淵王庭", 5: "終焉王座",
        }
        self.battle_background = self._ensure_battle_background(stage)
        self.rect(35, 20, 1110, 106, (20, 31, 44, 246))
        self.rect(49, 34, 1082, 78, (32, 45, 60, 220))
        self.draw_ui_frame("frame.battle_dock", 35, 20, 1110, 106,
                           tint=(67, 84, 103), margin_ratio=.12, filled=False)
        self.rect(50, 112, 1080, 1, (135, 154, 174, 116))
        # The stage name is useful orientation, but does not need an ornate
        # plaque competing with the arena.  A compact quiet strip preserves
        # contrast while leaving the scene art visible.
        self.quiet_surface(43, 651, 260, 34, alpha=178)
        self.text(stage_names[stage], 173, 668, 14, INK,
                  "center", "center", True, max_width=224, max_height=19,
                  min_size=12)
        modifier = getattr(getattr(self, "battle_modifier", None), "value", "")
        modifier_labels = {
            "rampart": "堅壁｜敵人開場獲得護盾",
            "greed": "貪婪｜敵攻 +15%・金幣 ×2",
        }
        if modifier in modifier_labels:
            self.quiet_surface(400, 651, 380, 34, alpha=188)
            self.text(modifier_labels[modifier], 590, 668, 13, GOLD,
                      "center", "center", True, max_width=350,
                      max_height=18, min_size=12)

        action_left, action_bottom = 54.0, 41.0
        action_width, action_height = 110.0, 64.0
        self.rect(action_left, action_bottom, action_width, action_height,
                  (38, 53, 70, 232), (110, 132, 153, 155), 1)
        action_point = load_ai_ui_texture("icons/markers/action_point.png")
        total_actions = max(1, self.battle_action_points)
        action_value = f"{max(0, self.player_actions_left)}/{total_actions}"
        value_width = self.measure_text_width(action_value, 12, True)
        icon_size, gap = 26.0, 7.0
        group_width = icon_size + gap + value_width
        group_center_x = action_left + action_width / 2
        icon_x = group_center_x - group_width / 2 + icon_size / 2
        value_x = icon_x + icon_size / 2 + gap
        group_left = group_center_x - group_width / 2
        self._battle_action_slot_geometry = (
            action_left, action_bottom, action_width, action_height,
        )
        self._battle_action_group_geometry = (
            group_left, 73 - icon_size / 2, group_width, icon_size,
        )
        action_available = self.player_actions_left > 0
        arcade.draw_texture_rect(
            action_point, arcade.XYWH(icon_x, 73, icon_size, icon_size),
            color=Color(*(239, 191, 91) if action_available else (125, 136, 151)),
            alpha=245 if action_available else 155,
        )
        self.text(action_value, value_x, 73, 12,
                  GOLD if action_available else (157, 169, 183),
                  "left", "center", True, max_width=40, max_height=16,
                  min_size=10)

    def event_background(self, number: int) -> arcade.Texture:
        texture = self.event_backgrounds.get(number)
        if texture is None:
            texture = make_activity_background("event", number)
            self.event_backgrounds[number] = texture
        return texture

    def monster_portrait(self, rank: int, kind: str,
                         pose: str = "idle") -> arcade.Texture:
        key = (rank, kind, pose)
        texture = self._monster_portrait_cache.get(key)
        if texture is None:
            texture = make_monster_portrait(rank, kind, pose)
            self._monster_portrait_cache[key] = texture
        return texture

    def battle_enemy_ground_position(self, index: int) -> tuple[float, float]:
        """Return the fixed world-space foot anchor for one enemy."""
        enemies = getattr(self, "enemies", ())
        if len(enemies) <= 1:
            return 850.0, 228.0
        formations = ((770.0, 228.0), (990.0, 233.0))
        x, ground_y = formations[min(index, len(formations) - 1)]
        if index == min(getattr(self, "target_index", 0), len(formations) - 1):
            x -= 24.0
        return x, ground_y

    def battle_enemy_texture_size(self, texture: arcade.Texture,
                                  index: int = 0,
                                  pose: str = "idle") -> tuple[float, float]:
        enemies = getattr(self, "enemies", ())
        max_width = 185.0 if len(enemies) > 1 else 250.0
        max_height = 220.0 if len(enemies) > 1 else 285.0
        boss = bool(enemies and getattr(enemies[min(index, len(enemies) - 1)],
                                        "rank", 1) >= 6)
        if boss:
            max_width, max_height = 320.0, 350.0
        if not enemies:
            return fit_visible_texture_size(texture, max_width, max_height)
        enemy = enemies[min(index, len(enemies) - 1)]
        kind_name = MONSTER_ART_KIND_NAMES.get(getattr(enemy, "kind", ""))
        if kind_name is None:
            return fit_visible_texture_size(texture, max_width, max_height)
        scale = monster_pose_scale(
            int(getattr(enemy, "rank", 1)), kind_name, pose,
            max_height, max_width,
        )
        return float(texture.width) * scale, float(texture.height) * scale

    def battle_enemy_visual_position(self, index: int,
                                     texture: arcade.Texture | None = None,
                                     display_height: float | None = None,
                                     pose: str = "idle",
                                     ) -> tuple[float, float]:
        """Return a pose-aware centre while keeping the feet on one baseline."""
        portraits = getattr(self, "enemy_portraits", ())
        if texture is None:
            texture = portraits[index] if index < len(portraits) else getattr(
                self, "enemy_portrait", None
            )
        x, ground_y = self.battle_enemy_ground_position(index)
        if texture is None:
            return x, ground_y
        if display_height is None:
            _width, display_height = self.battle_enemy_texture_size(
                texture, index, pose
            )
        enemies = getattr(self, "enemies", ())
        if enemies:
            enemy = enemies[min(index, len(enemies) - 1)]
            kind_name = MONSTER_ART_KIND_NAMES.get(getattr(enemy, "kind", ""))
            if kind_name is not None:
                scale = display_height / max(1.0, float(texture.height))
                anchor_x = monster_pose_anchor_x(
                    int(getattr(enemy, "rank", 1)), kind_name, pose,
                )
                x -= canvas_center_offset(anchor_x, float(texture.width), scale)
        visible_bottom, _ = self.texture_visible_vertical_bounds(texture, display_height)
        return x, ground_y - visible_bottom

    @staticmethod
    def texture_visible_vertical_bounds(texture: arcade.Texture | None,
                                        display_height: float) -> tuple[float, float]:
        """Return alpha-aware Y bounds without runtime Pillow processing."""
        if texture is None or not texture.hit_box_points:
            return -display_height / 2, display_height / 2
        scale = display_height / max(1.0, float(texture.height))
        ys = tuple(float(point[1]) * scale for point in texture.hit_box_points)
        return min(ys), max(ys)

    @staticmethod
    def texture_visible_horizontal_bounds(texture: arcade.Texture | None,
                                          display_width: float) -> tuple[float, float]:
        if texture is None or not texture.hit_box_points:
            return -display_width / 2, display_width / 2
        scale = display_width / max(1.0, float(texture.width))
        xs = tuple(float(point[0]) * scale for point in texture.hit_box_points)
        return min(xs), max(xs)

    def portrait_visual_top(self, texture: arcade.Texture, center_y: float,
                            display_size: float) -> float:
        """Return the actual alpha-aware top used by intent/status placement."""
        _bottom, top = self.texture_visible_vertical_bounds(texture, display_size)
        return center_y + top

    def draw_player_preview(self, sex: str, race: str, job: str,
                            x: float, ground_y: float,
                            max_width: float, max_height: float,
                            *, alpha: int = 255, shadow: bool = True) -> None:
        """Draw an idle player sprite aligned by its visible foot baseline."""
        texture = make_player_portrait(sex, race, job, pose="idle")
        width, height = fit_player_texture_size(
            texture, sex, race, job, "idle", max_width, max_height,
        )
        sex_dir = PLAYER_ART_SEX_DIRS.get(sex)
        race_dir = PLAYER_ART_RACE_DIRS.get(race)
        filename = PLAYER_ART_JOB_FILES.get(job)
        draw_x = x
        if sex_dir and race_dir and filename:
            scale = height / max(1.0, float(texture.height))
            anchor_x = player_pose_anchor_x(
                sex_dir, race_dir, Path(filename).stem, "idle",
            )
            draw_x -= canvas_center_offset(anchor_x, float(texture.width), scale)
        visible_bottom, _ = self.texture_visible_vertical_bounds(texture, height)
        center_y = ground_y - visible_bottom
        if shadow:
            ground_shadow = load_ai_ui_texture("icons/markers/ground_shadow.png")
            arcade.draw_texture_rect(
                ground_shadow,
                arcade.XYWH(x, ground_y + 2, max(30.0, width * .72),
                            max(7.0, min(14.0, height * .08))),
                alpha=min(alpha, 90),
            )
        arcade.draw_texture_rect(
            texture, arcade.XYWH(draw_x, center_y, width, height), alpha=alpha,
        )

    @staticmethod
    def draw_player_head_preview(sex: str, race: str, job: str,
                                 x: float, y: float, size: float,
                                 *, alpha: int = 255) -> None:
        texture = make_player_head_portrait(sex, race, job)
        arcade.draw_texture_rect(
            texture, arcade.XYWH(x, y, size, size), alpha=alpha,
        )

    @staticmethod
    def skill_effect_alpha(progress: float) -> int:
        fade_in = min(1.0, progress / .12)
        fade_out = min(1.0, (1.0 - progress) / .22)
        return max(0, min(255, int(255 * fade_in * fade_out)))

    def draw_skill_effects(self) -> None:
        if getattr(self, "reduce_motion", False):
            return
        names = {
            "blood_ritual": "血祭強襲", "fate_rewrite": "命運改寫",
            "divine_protection": "神聖庇護", "sap": "悶棍",
            "slash": "斬擊", "guard": "格擋", "cleave": "順劈斬",
            "fortify": "鋼鐵壁壘", "counter": "盾擊反制",
            "bladestorm": "劍刃風暴", "last_stand": "最後防線",
            "fireball": "火球術", "ice_armor": "冰甲術",
            "pyroblast": "炎爆術", "ice_wall": "冰牆術",
            "ice_barrier": "寒冰屏障", "mana_shield": "法力護盾",
            "meteor": "隕石風暴", "smite": "聖光懲擊",
            "blessing": "虔誠祝福", "judgment": "聖光審判",
            "sanctuary": "聖域", "purify": "淨化祈禱",
            "divine_wrath": "神聖怒火", "guardian_angel": "守護天使",
            "stab": "刺擊", "smokescreen": "煙幕",
            "backstab": "背刺", "smoke_bomb": "煙霧彈",
            "vanish": "消失", "shadowstep": "暗影步",
            "assassinate": "刺殺", "soul_drain": "靈魂汲取",
            "corruption_bolt": "腐蝕箭", "dark_charm": "暗影護符",
            "agony": "痛苦詛咒", "life_tap": "生命轉化",
            "soul_link": "靈魂連結", "hex": "衰弱咒印",
            "doom": "末日降臨",
        }
        job_colors = {
            "戰士": (232, 83, 61), "法師": (82, 173, 255),
            "聖騎士": (255, 211, 93), "盜賊": (174, 104, 235),
            "術士": (116, 218, 83),
        }
        for effect in self.skill_effects:
            progress = max(0.0, min(1.0, effect.elapsed / effect.duration))
            alpha = self.skill_effect_alpha(progress)
            if alpha <= 0:
                continue
            color = job_colors.get(effect.job, GOLD)
            self.draw_skill_effect(effect.skill_id, effect.job, progress, alpha, color)
            if progress < .72:
                label_x = 590
                if len(getattr(self, "enemies", ())) > 1:
                    target_index = min(getattr(self, "target_index", 0), 1)
                    target_x, _target_y = self.battle_enemy_visual_position(target_index)
                    label_x = (330 + target_x) / 2
                self.text(names.get(effect.skill_id, effect.skill_id), label_x, 606, 17,
                          color, "center", "center", True,
                          max_width=300, max_height=25, min_size=13)

    def intent_icon_texture(self, intent: str) -> arcade.Texture:
        if intent in self._intent_icon_cache:
            return self._intent_icon_cache[intent]
        try:
            spec = intent_icon(intent)
        except KeyError as exc:
            raise ValueError(f"Unsupported enemy intent: {intent}") from exc
        texture = load_ai_ui_texture(
            spec.best_asset_path(ASSET_ROOT / "ui")
        )
        self._intent_icon_cache[intent] = texture
        return texture

    def draw_status_badges(
        self,
        badges: tuple[StatusBadge, ...],
        center_x: float,
        base_y: float,
        max_width: float,
    ) -> None:
        """Draw icon-first overhead chips without dropping localized status text."""
        if not badges:
            return
        tone_colors = {
            "danger": RED,
            "warning": ORANGE,
            "drain": PURPLE,
            "ailment": PURPLE,
            "guard": BLUE,
            "counter": GOLD,
            "recovery": GREEN,
            "power": GOLD,
            "evasion": (164, 180, 224),
        }
        locale = get_locale()
        # The shared text boundary enforces a 12px English floor, so measure
        # chips at that same size instead of underestimating their plate width.
        font_size = 12 if locale == "EN" else 10
        chip_height = 28.0
        gap = 5.0
        prepared: list[tuple[StatusBadge, str, float]] = []
        for badge in badges:
            label = badge.label(locale)
            text_value = f"{label} {badge.value}" if badge.value else label
            text_width = self.measure_text_width(text_value, font_size, True)
            chip_width = min(max_width, max(54.0, 38.0 + text_width))
            prepared.append((badge, text_value, chip_width))

        rows: list[list[tuple[StatusBadge, str, float]]] = []
        row: list[tuple[StatusBadge, str, float]] = []
        row_width = 0.0
        for item in prepared:
            item_width = item[2]
            candidate_width = item_width if not row else row_width + gap + item_width
            if row and candidate_width > max_width:
                rows.append(row)
                row = [item]
                row_width = item_width
            else:
                row.append(item)
                row_width = candidate_width
        if row:
            rows.append(row)

        for row_index, items in enumerate(rows):
            total_width = sum(item[2] for item in items) + gap * (len(items) - 1)
            cursor_x = center_x - total_width / 2
            y = base_y + row_index * (chip_height + 4)
            for badge, text_value, chip_width in items:
                accent = tone_colors.get(badge.icon.tone, GOLD)
                self.rect(
                    cursor_x, y - chip_height / 2, chip_width, chip_height,
                    (5, 10, 17, 232), (*accent, 205), 1,
                )
                icon = load_tight_ai_ui_texture(
                    badge.icon.best_asset_path(ASSET_ROOT / "ui"), 2
                )
                icon_width, icon_height = fit_texture_size(icon, 21, 21)
                arcade.draw_texture_rect(
                    icon,
                    arcade.XYWH(cursor_x + 15, y, icon_width, icon_height),
                )
                self.text(
                    text_value, cursor_x + 30, y, font_size, INK,
                    "left", "center", True,
                    max_width=max(18.0, chip_width - 35),
                    max_height=18, min_size=font_size,
                )
                cursor_x += chip_width + gap

    @staticmethod
    def displayed_enemy_intent(enemy) -> str:
        return "stun" if enemy.skip_turns > 0 else enemy.intent

    def draw_intent_icon(self, enemy, x: float, y: float, *, selected: bool = False) -> None:
        """Show the next enemy action as a framed badge clear of damage text."""
        displayed_intent = self.displayed_enemy_intent(enemy)
        _legacy_icon, color, _category = self.enemy_intent_style(displayed_intent)
        pulse = .5 + .5 * math.sin(self.battle_clock * 4.2)
        if selected:
            marker = load_ai_ui_texture("icons/markers/target_selected.png")
            arcade.draw_texture_rect(
                marker, arcade.XYWH(x, y, 82, 82),
                alpha=210 + round(pulse * 35),
            )
        badge = load_ai_ui_texture("icons/markers/badge_round.png")
        arcade.draw_texture_rect(
            badge, arcade.XYWH(x, y, 70, 70),
            color=Color(*color), alpha=244,
        )
        texture = self.intent_icon_texture(displayed_intent)
        arcade.draw_texture_rect(texture, arcade.XYWH(x, y + 1, 49, 49))
        value = self.enemy_intent_value(enemy)
        if value:
            value_width = max(30.0, self.measure_text_width(value, 13, True) + 15)
            value_x, value_y = x + 25, y - 23
            self.rect(value_x - value_width / 2, value_y - 11,
                      value_width, 22, (6, 11, 18, 242), (*color, 218), 1)
            self.text(value, value_x + 1, value_y - 1, 13, (0, 0, 0, 230),
                      "center", "center", True, max_width=value_width - 6,
                      max_height=17, min_size=10)
            self.text(value, value_x, value_y, 13, color,
                      "center", "center", True, max_width=value_width - 6,
                      max_height=17, min_size=10)

    def draw_intent_telegraph(self, enemy, x: float, y: float,
                              width: float, compact: bool = False) -> None:
        """Draw a restrained single-line telegraph for the enemy's next action."""
        _legacy_icon, color, _category = self.enemy_intent_style(enemy.intent)
        hostile = enemy.intent in self.HOSTILE_ENEMY_INTENTS
        pulse = .5 + .5 * math.sin(self.battle_clock * (6.0 if hostile else 3.2))
        height = 42
        left = x - width / 2
        self.rect(left, y - height / 2, width, height,
                  (7, 13, 23, 205), (*color, 155 + int(pulse * 55)), 1)
        self.rect(left, y - height / 2, 3, height, (*color, 225))
        texture = self.intent_icon_texture(enemy.intent)
        arcade.draw_texture_rect(
            texture, arcade.XYWH(left + 21, y, 30, 30),
        )
        label = self.enemy_intent_label(enemy)
        if "｜" in label:
            skill_name, effect = label.split("｜", 1)
            if compact:
                compact_effects = {
                    "攻擊與防禦 -33%，持續 3 回合": "攻防 -33%・3 回合",
                    "使你跳過下一次行動": "跳過下次行動",
                    "免疫下一次受到的傷害": "免疫下次傷害",
                    "1 回合內反彈 50% 傷害": "反彈 50% 傷害・1 回合",
                    "淨化負面狀態，否則轉為護盾": "淨化減益；無減益則獲盾",
                }
                effect = compact_effects.get(effect, effect)
                effect = effect.replace("傷害，持續 3 回合", "傷害・3 回合")
            self.text(skill_name, left + 42, y + 9, 10 if compact else 11, color,
                      "left", "center", True, max_width=width - 50,
                      max_height=15, min_size=8)
            self.text(effect, left + 42, y - 9, 10 if compact else 11, INK,
                      "left", "center", hostile, max_width=width - 50,
                      max_height=15, min_size=8)
        else:
            self.text(label, left + 42, y, 11, INK,
                      "left", "center", hostile, max_width=width - 50,
                      max_height=16, min_size=8)

    def draw_enemy_intent_hover_card(self) -> None:
        """Reveal the next enemy move only while its enemy or icon is hovered."""
        if (self.scene != self.Scene.BATTLE or self.battle_log_expanded
                or getattr(self, "tutorial_tip", "")
                or self.home_confirmation or self.cheat_open):
            return
        index = getattr(self, "hovered_enemy_intent_index", None)
        if index is None or index < 0 or index >= len(self.enemies):
            return
        enemy = self.enemies[index]
        if enemy.hp <= 0:
            return

        label = self.enemy_intent_label(enemy)
        if "｜" in label:
            skill_name, effect = label.split("｜", 1)
        else:
            skill_name, effect = label, "本回合不會採取行動。"
        displayed_intent = self.displayed_enemy_intent(enemy)
        _legacy_icon, color, category = self.enemy_intent_style(displayed_intent)
        if enemy.skip_turns > 0:
            category = "無法行動"

        # English intent explanations are substantially wider than their CJK
        # sources.  Give the hover card a readable measure and a genuine
        # two-line effect region instead of shrinking the sentence into a
        # single overflowing strip.
        width, height = 520.0, 112.0
        if index < len(self.enemy_intent_hitboxes):
            anchor_left, anchor_bottom, anchor_width, anchor_height = (
                self.enemy_intent_hitboxes[index]
            )
        elif index < len(self.enemy_hitboxes):
            anchor_left, anchor_bottom, anchor_width, anchor_height = (
                self.enemy_hitboxes[index]
            )
        else:
            return
        anchor_x = anchor_left + anchor_width / 2
        left = max(24.0, min(SCREEN_WIDTH - width - 24.0,
                             anchor_x - width / 2))
        bottom = anchor_bottom + anchor_height + 14.0
        if bottom + height > SCREEN_HEIGHT - 18.0:
            bottom = anchor_bottom - height - 14.0
        bottom = max(132.0, bottom)

        self.quiet_surface(left, bottom, width, height, alpha=244)
        self.rect(left, bottom, 4, height, (*color, 235))
        content_left = left + 18
        content_width = width - 34
        self.text(f"{enemy.name}｜下一招・{category}", content_left,
                  bottom + 90, 11, MUTED, "left", "center", True,
                  max_width=content_width, max_height=16, min_size=10)
        self.text(skill_name, content_left, bottom + 65, 13, color,
                  "left", "center", True, max_width=content_width,
                  max_height=19, min_size=11)
        self.draw_text_block(
            effect, content_left, bottom + 31, content_width, 11, INK,
            line_spacing=18, max_lines=2, min_size=11, anchor_x="left",
        )

    @staticmethod
    def draw_ai_effect_sprite(filename: str, x: float, y: float,
                              width: float, height: float, alpha: int,
                              angle: float = 0.0) -> bool:
        texture = load_ai_effect(filename)
        if texture is None:
            return False
        arcade.draw_texture_rect(
            texture, arcade.XYWH(x, y, width, height), angle=angle,
            alpha=max(0, min(255, alpha)),
        )
        return True

    def draw_ai_skill_effect(self, skill_id: str, job: str, progress: float,
                             alpha: int) -> bool:
        """Render every current skill with transparent AI-painted sprites."""
        player_x, player_y = 330.0, 300.0
        enemy_x, enemy_y = self.battle_enemy_visual_position(0)
        if len(getattr(self, "enemies", ())) > 1:
            target_index = min(getattr(self, "target_index", 0), len(self.enemies) - 1)
            enemy_x, enemy_y = self.battle_enemy_visual_position(target_index)
        pulse = 1.0 + math.sin(progress * math.tau * 2) * .045

        def sprite(name: str, x: float, y: float, width: float, height: float | None = None,
                   angle: float = 0.0, opacity: float = 1.0) -> bool:
            return self.draw_ai_effect_sprite(
                name, x, y, width * pulse, (height or width) * pulse,
                round(alpha * opacity), angle,
            )

        warrior_guards = {"guard", "fortify", "last_stand"}
        warrior_strikes = {"slash", "cleave", "counter", "bladestorm"}
        frost_spells = {"ice_armor", "ice_wall", "ice_barrier", "mana_shield"}
        fire_projectiles = {"fireball", "pyroblast"}
        holy_strikes = {"smite", "judgment", "divine_wrath"}
        holy_aura = {"blessing", "sanctuary", "purify", "divine_protection"}
        shadow_strikes = {"stab", "backstab", "shadowstep", "assassinate"}
        smoke_spells = {"smokescreen", "smoke_bomb", "vanish"}
        warlock_projectiles = {"corruption_bolt", "soul_drain"}
        warlock_curses = {"agony", "hex", "doom"}
        warlock_self = {"dark_charm", "life_tap", "soul_link"}

        if skill_id in warrior_guards:
            return sprite("steel_guard.png", player_x, player_y, 235)
        if skill_id in warrior_strikes:
            count = 3 if skill_id == "bladestorm" else (2 if skill_id in {"cleave", "counter"} else 1)
            drawn = False
            for index in range(count):
                angle = -28 + index * (56 / max(1, count - 1)) + progress * (110 if count > 2 else 18)
                drawn |= sprite("slash_streak.png", enemy_x, enemy_y, 260, 210, angle)
            return drawn
        if skill_id == "blood_ritual":
            drawn = sprite("magic_ring.png", player_x, player_y - 45, 245, 150,
                           progress * 55)
            return sprite("blood_drop.png", player_x, player_y + 25, 145) or drawn
        if skill_id == "fate_rewrite":
            return sprite("magic_ring.png", 590, 420, 275, 190, progress * 80)
        if skill_id in fire_projectiles:
            travel = min(1.0, progress / .58)
            x = player_x + (enemy_x - player_x) * travel
            y = player_y + math.sin(travel * math.pi) * (78 if skill_id == "pyroblast" else 48)
            size = 150 if skill_id == "pyroblast" else 112
            drawn = sprite("fireball_projectile.png", x, y, size, size * .68)
            if travel >= 1:
                drawn |= sprite("fire_impact.png", enemy_x, enemy_y,
                                245 if skill_id == "pyroblast" else 195,
                                opacity=.92)
            return drawn
        if skill_id in warlock_projectiles:
            travel = min(1.0, progress / .60)
            x = player_x + (enemy_x - player_x) * travel
            y = player_y + math.sin(travel * math.pi) * 42
            drawn = sprite("corruption_bolt.png", x, y, 125, 78)
            if travel >= 1:
                drawn |= sprite("curse_wisp.png", enemy_x, enemy_y, 165, opacity=.82)
            return drawn
        if skill_id == "meteor":
            travel = min(1.0, progress / .58)
            x, y = 1010 - 155 * travel, 650 - 310 * travel
            # Use the same round fire projectile language as the mage's other
            # fire skills.  The previous crescent trail read like a sword slash.
            drawn = sprite("fireball_projectile.png", x, y, 195, 125, -48)
            if progress > .46:
                drawn |= sprite("fire_impact.png", enemy_x, enemy_y, 250)
            return drawn
        if skill_id in frost_spells:
            x, y = (590.0, 335.0) if skill_id == "ice_wall" else (player_x, player_y)
            width = 330 if skill_id == "ice_wall" else 235
            drawn = sprite("ice_crystal.png", x, y, width, 230)
            if skill_id in {"ice_barrier", "mana_shield"}:
                drawn |= sprite("barrier_hex.png", player_x, player_y, 245)
            return drawn
        if skill_id in holy_strikes:
            drawn = sprite("holy_beam.png", enemy_x, enemy_y + 115, 190, 390)
            return sprite("impact_burst.png", enemy_x, enemy_y, 175, opacity=.7) or drawn
        if skill_id in holy_aura:
            return sprite("holy_sigil.png", player_x, player_y - 32, 255, 210,
                          opacity=.9)
        if skill_id == "guardian_angel":
            drawn = sprite("angel_wing.png", player_x, player_y + 25, 285, 245)
            return sprite("magic_ring.png", player_x, player_y - 55, 210, 130) or drawn
        if skill_id in smoke_spells:
            return sprite("smoke_puff.png", player_x, player_y, 260 + progress * 60)
        if skill_id == "sap":
            return sprite("stun_star.png", enemy_x, enemy_y + 105, 145,
                          angle=progress * 90)
        if skill_id in shadow_strikes:
            count = 3 if skill_id == "assassinate" else (2 if skill_id in {"backstab", "shadowstep"} else 1)
            drawn = False
            for index in range(count):
                angle = -38 + index * (76 / max(1, count - 1))
                drawn |= sprite("shadow_slash.png", enemy_x, enemy_y, 245, 195, angle)
            return drawn
        if skill_id in warlock_curses:
            drawn = sprite("curse_wisp.png", enemy_x, enemy_y + 20, 215)
            return sprite("magic_ring.png", enemy_x, enemy_y - 60, 210, 125,
                          progress * -65, .75) or drawn
        if skill_id in warlock_self:
            drawn = sprite("curse_wisp.png", player_x, player_y + 15, 185, opacity=.75)
            return sprite("magic_ring.png", player_x, player_y - 45, 215, 135,
                          progress * 55) or drawn
        return sprite("magic_mote.png", enemy_x if job in ("戰士", "法師", "盜賊") else player_x,
                      enemy_y if job in ("戰士", "法師", "盜賊") else player_y, 190)

    def draw_skill_effect(self, skill_id: str, job: str, progress: float,
                          alpha: int, color: tuple[int, int, int]) -> None:
        """Render a skill exclusively from required AI VFX sprites."""
        del color
        if not self.draw_ai_skill_effect(skill_id, job, progress, alpha):
            raise RuntimeError(f"No AI VFX mapping for skill: {skill_id}")

    def event_panel_layout(self) -> tuple[float, float, float, float,
                                          float, float, float, tuple[float, ...]]:
        """Return one compact event layout shared by drawing and buttons."""
        panel_left, panel_bottom, panel_width = 90.0, 46.0, 1000.0
        content_left, content_width = 128.0, 690.0
        button_x = 965.0
        if self.event_resolved and len(self.event_messages) >= 3:
            samples = (
                self.event_messages[-3].removeprefix("你選擇").rstrip("。"),
                self.event_messages[-2],
                self.event_messages[-1],
            )
            line_count = sum(max(1, len(self.wrap_text_pixels(text, content_width, size)))
                             for text, size in zip(samples, (11, 13, 11)))
            text_height = line_count * 19 + 16
            button_count = 1
        else:
            intro = self.event_messages[-1] if self.event_messages else ""
            line_count = max(1, len(self.wrap_text_pixels(intro, content_width, 13)))
            text_height = line_count * 21 + 24
            button_count = max(1, len(self.event_options))
        button_height = button_count * 42 + max(0, button_count - 1) * 10 + 22
        # Three translated choices need more vertical room than their compact
        # Chinese labels.  This region has ample scene space above it; growing
        # here is preferable to overlapping controls or clipping narrative.
        panel_height = max(82.0, min(220.0, float(max(text_height, button_height))))
        center_y = panel_bottom + panel_height / 2
        if button_count == 1:
            button_ys = (center_y,)
        else:
            gap = 52.0
            button_ys = tuple(
                center_y + (button_count - 1) * gap / 2 - index * gap
                for index in range(button_count)
            )
        return (panel_left, panel_bottom, panel_width, panel_height,
                content_left, content_width, button_x, button_ys)


    def on_draw(self) -> None:
        # A DPI or monitor transition can reset Arcade's GL viewport between
        # resize events. Re-assert the shared 1180x720 virtual canvas before
        # drawing any scene so menus, battle and the adventure footer all use
        # the same projection.
        self.apply_ui_viewport()
        self.ui_layout_warnings.clear()
        self.ui_truncations.clear()
        self.clear()
        self.draw_background_batch()
        # Scene artwork owns the outer edge.  A second full-screen perimeter
        # made every menu look like a framed panel inside another frame and
        # added no interaction or grouping information.
        if self.scene == self.Scene.TITLE:
            self.draw_title()
        elif self.scene == self.Scene.SETTINGS:
            self.draw_settings()
        elif self.scene == self.Scene.CREATION:
            self.draw_creation()
        elif self.scene == self.Scene.SAVE_MENU:
            self.draw_save_menu()
        else:
            self.draw_game()
        if self.scene == self.Scene.BATTLE and self.battle_log_expanded:
            self.draw_battle_log_overlay()
        if (self.scene == self.Scene.END
                and getattr(self, "end_record_open", False)):
            self.draw_end_record_overlay()
        if self.home_confirmation:
            self.draw_home_confirmation()
        if self.talent_reset_confirmation:
            self.draw_talent_reset_confirmation()
        if self.cheat_open:
            self.draw_cheat_panel()
        self.draw_potion_menu_backdrop()
        if getattr(self, "tutorial_tip", ""):
            self.draw_battle_tutorial()
        for button in self.buttons:
            if not button.invisible:
                self.draw_button(button)
        self.draw_enemy_intent_hover_card()
        self.draw_hover_tooltip()
        self.draw_scene_transition()

    def draw_background_batch(self) -> None:
        """Submit persistent base and active scene art in one SpriteList draw."""
        layer = self.background_layer
        layer.begin_frame()
        # The journey map is itself a full-screen background. Do not submit the
        # title art underneath it; that legacy layer used to show at the sides
        # of the smaller contained map.
        if self.scene != self.Scene.ADVENTURE:
            if self.background is None:
                self.background = make_background()
            layer.set_texture(
                "main", self.background, center_x=SCREEN_WIDTH / 2,
                center_y=SCREEN_HEIGHT / 2, width=SCREEN_WIDTH, height=SCREEN_HEIGHT,
            )
        texture: arcade.Texture | None = None
        center_x, center_y, width, height = 590.0, 357.5, 1140.0, 685.0
        if self.scene == self.Scene.BATTLE:
            stage = self.battle_background_stage(self.player.lv)
            self.battle_background = self._ensure_battle_background(stage)
            texture = self.battle_background
            camera_x, camera_y = self.combat_camera_offset()
            center_x += camera_x
            center_y += camera_y
            width, height = 1154.0, 699.0
        elif self.scene == self.Scene.CAMPFIRE:
            texture = self._ensure_campfire_background()
        elif self.scene == self.Scene.SHOP:
            texture = self._ensure_shop_background()
        elif self.scene == self.Scene.EVENT:
            number = self.event_background_number(self.event_number)
            texture = self.event_background(number)
        elif self.scene == self.Scene.TALENT:
            texture = self._ensure_talent_background()
            center_x, center_y = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2
            width, height = SCREEN_WIDTH, SCREEN_HEIGHT
        elif self.scene == self.Scene.ADVENTURE:
            texture = self._ensure_adventure_map()
            map_viewport = cover_map_viewport(
                texture.width, texture.height, SCREEN_WIDTH, SCREEN_HEIGHT
            )
            center_x, center_y = map_viewport.center_x, map_viewport.center_y
            width, height = map_viewport.width, map_viewport.height
        if texture is not None:
            source_ratio = texture.width / max(1, texture.height)
            if self.scene not in {
                self.Scene.BATTLE, self.Scene.TALENT, self.Scene.ADVENTURE,
            }:
                height = max(height, width / source_ratio)
            layer.set_texture(
                "scene", texture, center_x=center_x, center_y=center_y,
                width=width, height=height,
            )
        layer.draw()

    def draw_battle_tutorial(self) -> None:
        """Draw the first-battle guide as a modal above the combat HUD."""
        if self.scene != self.Scene.BATTLE or not self.tutorial_tip:
            return
        page = self.battle_tutorial_page()
        title, body = self.FIRST_BATTLE_TUTORIAL_PAGES[page]
        accents = (BLUE, GOLD, (206, 112, 82))
        symbols = ("◆", "✦", "★")
        accent = accents[page]
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 5, 10, 205))
        left, bottom, width, height = 240.0, 145.0, 700.0, 430.0
        self.panel(left, bottom, width, height)
        self.rect(left + 20, bottom + 86, 4, height - 116, (*accent, 225))
        self.text("首戰指南", left + 42, bottom + height - 43, 14, MUTED,
                  "left", "center", True, max_width=300, max_height=20)
        self.text(f"{page + 1} / {len(self.FIRST_BATTLE_TUTORIAL_PAGES)}",
                  left + width - 42, bottom + height - 43, 12, MUTED,
                  "right", "center", True, max_width=100, max_height=18)
        self.text(symbols[page], left + 88, bottom + 292, 46, accent,
                  "center", "center", True, max_width=70, max_height=58)
        self.text(title, left + 145, bottom + 316, 24, GOLD,
                  "left", "center", True, max_width=470, max_height=34,
                  min_size=19)
        lines, tutorial_size = self.fitted_wrapped_lines(
            body, 500, 15, min_size=13, max_lines=5
        )
        tutorial_spacing = 27 if len(lines) <= 4 else 24
        for index, line in enumerate(lines):
            self.text(line, left + 145,
                      bottom + 272 - index * tutorial_spacing,
                      tutorial_size, INK,
                      "left", "center", max_width=500,
                      max_height=tutorial_spacing,
                      min_size=tutorial_size)
        for index in range(len(self.FIRST_BATTLE_TUTORIAL_PAGES)):
            dot_color = accent if index == page else (100, 112, 126)
            arcade.draw_circle_filled(
                left + width / 2 + (index - 1) * 24,
                bottom + 115, 5 if index == page else 3, dot_color,
            )
        self.text("按 Enter 繼續、Esc 略過教學",
                  left + width / 2, bottom + 86, 11, MUTED,
                  "center", "center", max_width=420, max_height=18)

    def draw_scene_transition(self) -> None:
        """在現有 Scene enum 架構上提供統一的淡入，避免每個按鈕各自處理轉場。"""
        duration = max(.001, getattr(self, "scene_transition_duration", .28))
        elapsed = getattr(self, "scene_transition_elapsed", duration)
        if elapsed >= duration:
            return
        progress = max(0.0, min(1.0, elapsed / duration))
        alpha = round(238 * (1.0 - progress) ** 2.25)
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (5, 8, 13, alpha))
        if progress < .55:
            rule_alpha = round(150 * (1.0 - progress / .55))
            self.rect(170, SCREEN_HEIGHT / 2, SCREEN_WIDTH - 340, 1,
                      (*COLORS.brass, rule_alpha))

    def draw_battle_log_overlay(self) -> None:
        """Draw combat history as a deliberate modal, not a player-covering rail."""
        log_left, log_bottom, log_width, log_height = 250.0, 190.0, 680.0, 340.0
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 5, 10, 188))
        self.panel(log_left, log_bottom, log_width, log_height, "戰鬥紀錄")
        content_left = log_left + 74
        text_width = log_width - 128
        text_size = max(11, round(12 * float(getattr(self, "ui_scale", 1.0))))
        prepared = self.prepared_hanging_log_cards(
            self.combat_messages, text_width, text_size
        )
        available_height = log_height - 84
        maximum = self.max_log_scroll(prepared, available_height)
        self.log_scroll = max(0, min(self.log_scroll, maximum))
        visible = []
        used_height = 0.0
        for card in prepared[self.log_scroll:]:
            next_height = card[3] + (5 if visible else 0)
            if used_height + next_height > available_height:
                break
            visible.append(card)
            used_height += next_height
        cursor = log_bottom + log_height - 62.0
        for index, (icon, lines, accent, card_height) in enumerate(visible):
            newest = index == 0 and self.log_scroll == 0
            card_bottom = cursor - card_height
            # The modal panel is already a readable surface.  Only the newest
            # entry needs an additional state marker; repeating a card behind
            # every log line creates a dense stack of nested containers.
            if newest:
                self.quiet_surface(log_left + 20, card_bottom,
                                   log_width - 60, card_height,
                                   selected=True, alpha=150)
            self.text(self.log_badge_text(icon), log_left + 44,
                      card_bottom + card_height / 2, 11,
                      accent, "center", "center", True,
                      max_width=18, max_height=17, min_size=8)
            line_color = INK if newest else (194, 201, 210)
            line_start_y = card_bottom + card_height / 2 + (len(lines) - 1) * 10.5
            for line_index, (line, indent) in enumerate(lines):
                self.text(line, content_left + indent,
                          line_start_y - line_index * 21, 12,
                          line_color, anchor_y="center",
                          max_width=max(40, text_width - indent),
                          max_height=20, min_size=11)
            cursor = card_bottom - 5

        if maximum > 0 and prepared:
            track_left, track_bottom = 908.0, log_bottom + 24.0
            track_width, track_height = 8.0, log_height - 92.0
            thumb_height = max(35.0, track_height * len(visible) / len(prepared))
            thumb_travel = track_height - thumb_height
            thumb_bottom = track_bottom + thumb_travel * (1 - self.log_scroll / maximum)
            self.rect(track_left, track_bottom, track_width, track_height,
                      (29, 39, 54, 210), (92, 110, 135, 160), 1)
            self.rect(track_left, thumb_bottom, track_width, thumb_height,
                      (133, 154, 184, 230), (205, 216, 232, 180), 1)
            self._log_scroll_geometry = (
                track_left, track_bottom, track_width, track_height,
                thumb_bottom, thumb_height, float(maximum),
                float(max(1, len(visible))),
            )
        else:
            self._log_scroll_geometry = None

    def draw_end_record_overlay(self) -> None:
        """Show this run's result only when the player requests the record."""
        p = self.player
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 5, 10, 156))
        self.panel(225, 205, 730, 315, "此次紀錄")
        result_label = "勝利結算" if self.victory else "敗北結算"
        self.text(result_label, 590, 467, 24, GOLD, "center", "center", True,
                  max_width=650, max_height=32, min_size=18)
        job_text = p.job if not p.sub_job else f"{p.job}/{p.sub_job}"
        self.text(f"{p.name}｜{p.race}・{job_text}",
                  590, 421, 17, INK, "center", "center", True,
                  max_width=650, max_height=25, min_size=13)
        self.text(
            f"最終關卡 {self.level_label(p.lv)}｜攻擊 {p.attack}｜防禦 {p.defense}｜暴擊 {self.displayed_critical_chance():.0f}%",
            590, 365, 15, MUTED, "center", "center",
            max_width=650, max_height=23, min_size=12,
        )
        self.text(
            f"勝利戰鬥 {self.run_battles_won}｜擊敗敵人 {self.run_enemies_defeated}",
            590, 311, 15, INK, "center", "center",
            max_width=650, max_height=23, min_size=12,
        )
        self.text(
            f"累積傷害 {self.run_damage_dealt}｜最高一擊 {self.run_highest_hit}",
            590, 267, 15, INK, "center", "center",
            max_width=650, max_height=23, min_size=12,
        )

    def draw_settings(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (3, 6, 12, 82))
        self.panel(330, 110, 520, 500)
        self.text("設定", 590, 566, 30, GOLD, "center", "center", True,
                  max_width=450, max_height=40)

    def draw_home_confirmation(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 190))
        self.panel(355, 245, 470, 230, "離開這局？")
        self.text("確定要結束這次冒險嗎？", 590, 400, 22, GOLD,
                  "center", "center", True, max_width=400, max_height=32)
        self.draw_text_block(
            "回到主頁後，這次沒有存檔的進度會消失。",
            590, 350, 400, 14, INK, line_spacing=21,
            max_lines=2, min_size=12,
        )

    def draw_talent_reset_confirmation(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 195))
        self.panel(335, 250, 510, 210, "重置天賦？")
        spent = self.class_talent_spent()
        self.text("要清除目前的天賦配置嗎？", 590, 385, 22, GOLD,
                  "center", "center", True, max_width=450, max_height=32)
        self.draw_text_block(
            f"已投入的 {spent} 點會全部返還，此操作不影響角色等級。",
            590, 338, 450, 14, INK, line_spacing=21,
            max_lines=2, min_size=12,
        )

    def draw_cheat_panel(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 200))
        self.panel(280, 70, 620, 580)
        self.text("作弊工具", 590, 612, 28, GOLD, "center", "center", True,
                  max_width=540, max_height=38)
        if self.cheat_dropdown:
            target = "關卡" if self.cheat_dropdown == "lv" else "難度"
            self.text(f"選擇{target}", 590, 545, 22, GOLD, "center", "center", True,
                      max_width=540, max_height=30)
            self.text("點擊要設定的數值，或按「返回」取消。",
                      590, 512, 13, MUTED, "center", "center",
                      max_width=560, max_height=20, min_size=10)
            return
        self.draw_text_block(
            "點擊數值框輸入數字（最多 4 位）；難度與關卡用下拉選單；下一場戰鬥完全生效。",
            590, 577, 570, 12, MUTED, line_spacing=18,
            max_lines=2, min_size=11,
        )
        for row_index, (field, label) in enumerate(self.CHEAT_FIELDS):
            y = self.CHEAT_ROW_TOP - row_index * self.CHEAT_ROW_GAP
            self.quiet_surface(295, y - 19, 590, 38, alpha=145)
            self.text(label, 320, y, 15, INK, "left", "center", True,
                      max_width=280, max_height=22, min_size=11)
            if field == "hp":
                self.text(f"上限 {self.player.max_hp}", 610, y, 12, MUTED,
                          "right", "center", max_width=120, max_height=18, min_size=9)

    def draw_save_menu(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 190))
        manage_mode = self.save_menu_mode == "manage"
        title = "存檔 / 讀檔" if manage_mode else "讀取存檔"
        self.panel(240, 80, 700, 520)
        self.text(title, 590, 558, 28, GOLD, "center", "center", True,
                  max_width=620, max_height=38)
        hint = ("你可以保存目前進度，或讀取之前的存檔。" if manage_mode
                else "選一個存檔，繼續上次的冒險。")
        self.text(hint, 590, 526, 13, MUTED, "center", "center",
                  max_width=620, max_height=20, min_size=11)
        for slot in range(1, self.SAVE_SLOT_COUNT + 1):
            bottom = 402 - (slot - 1) * 104
            data = self.save_slots.get(slot)
            self.quiet_surface(270, bottom, 640, 86,
                               enabled=bool(data), alpha=220)
            self.text(f"存檔槽 {slot}", 305, bottom + 65, 15, GOLD, "left", "center",
                      True, max_width=180, max_height=22)
            if not data:
                self.text("空白", 305, bottom + 34, 14, MUTED,
                          "left", "center", max_width=420, max_height=22)
                continue
            saved_player = data.get("player", {})
            job_text = str(saved_player.get("job", ""))
            if saved_player.get("sub_job"):
                job_text += f"/{saved_player['sub_job']}"
            difficulty_name = self.DIFFICULTY_NAMES.get(
                int(data.get("difficulty", 1)), self.DIFFICULTY_NAMES[1]
            )
            saved_potions = 0
            potion_bag = saved_player.get("potion_bag", {})
            if isinstance(potion_bag, dict):
                for count in potion_bag.values():
                    try:
                        saved_potions += max(0, int(count))
                    except (TypeError, ValueError):
                        continue
            try:
                saved_potions += max(0, int(saved_player.get("potions", 0)))
            except (TypeError, ValueError):
                pass
            self.text(
                f"{saved_player.get('name', '勇者')}｜{saved_player.get('race', '')}・{job_text}"
                f"｜{self.level_label(int(saved_player.get('lv', 1)))}",
                305, bottom + 43, 14, INK, "left", "center", True,
                max_width=430, max_height=21, min_size=11,
            )
            self.text(
                f"血量 {saved_player.get('hp', 0)} / {saved_player.get('max_hp', 0)}"
                f"｜金幣 {saved_player.get('gold', 0)}G｜藥水 {saved_potions}",
                305, bottom + 24, 12, INK, "left", "center",
                max_width=430, max_height=18, min_size=10,
            )
            self.text(
                f"{difficulty_name}｜存檔時間 {data.get('saved_at', '—')}",
                305, bottom + 9, 10, MUTED, "left", "center",
                max_width=430, max_height=15, min_size=9,
            )

    def draw_title(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (3, 6, 12, 65))
        arcade.draw_texture_rect(
            load_title_logo(), arcade.XYWH(590, 480, 800, 288)
        )

    def draw_creation(self) -> None:
        # Character choices supply their own interactive cards.  The former
        # 890x510 parent panel duplicated those cards and hid most of the
        # background without improving the reading order.
        titles = ("選擇名字", "選擇種族", "選擇性別", "選擇職業")
        title_y = 525 if self.creation_step in (1, 3) else 505
        title_size = 28 if self.creation_step == 3 else 31
        self.text(titles[self.creation_step], 590, title_y, title_size, INK, "center", "center", True,
                  max_width=760, max_height=45)
        steps = ("名字", "種族", "性別", "職業")
        english_steps = get_locale() == "EN"
        step_start = 380 if english_steps else 455
        step_gap = 140 if english_steps else 90
        step_width = 112 if english_steps else 82
        for index, step in enumerate(steps):
            x = step_start + index * step_gap
            active = index == self.creation_step
            complete = index < self.creation_step
            color = GOLD if active else ((103, 174, 139) if complete else MUTED)
            self.text(f"{index + 1} {step}", x, 565,
                      12 if english_steps else 13, color,
                      "center", "center", active,
                      max_width=step_width, max_height=18,
                      min_size=12 if english_steps else 13)
            if index < len(steps) - 1:
                divider = load_ai_ui_texture("dividers/horizontal.png")
                arcade.draw_texture_rect(divider,
                                         arcade.XYWH(x + step_gap / 2, 565,
                                                     12 if english_steps else 8, 3),
                                         alpha=150)
        if self.creation_step == 0:
            self.quiet_surface(410, 365, 360, 62, alpha=218)
            input_y = 399
            if self.name_input or self.name_input_focused:
                if self.name_input:
                    self.text(self.name_input, 590, input_y, 24, GOLD, "center", "center", True,
                              max_width=320, max_height=38)
                if self.name_input_focused and int(self.name_caret_timer * 2) % 2 == 0:
                    name_width = (
                        min(320.0, self.measure_text_width(self.name_input, 24, True))
                        if self.name_input else 0.0
                    )
                    self.text("|", 590 + name_width / 2 + 3, input_y, 24, INK,
                              "left", "center", max_width=20, max_height=38)
            else:
                self.text("輸入角色名稱", 590, input_y, 24, MUTED, "center", "center", True,
                          max_width=320, max_height=38)
        elif self.creation_step == 1:
            for index, (race, _bonus) in enumerate(self.RACES):
                x = 290 + index * 200
                self.quiet_surface(x - 85, 260, 170, 185, alpha=210)
                self.draw_player_head_preview(
                    self.selected_sex, race, self.selected_job,
                    x, 352, 154,
                )
                self.text(race, x, 235, 16, GOLD, "center", "center", True,
                          max_width=150, max_height=21, min_size=14)
            self.quiet_surface(310, 180, 560, 32, alpha=210)
            self.text("移到頭像可查看初始加成與種族天賦。",
                      590, 196, 12, INK, "center", "center",
                      max_width=520, max_height=18, min_size=12)
        elif self.creation_step == 2:
            sex_cards = (("男性", 465), ("女性", 715))
            for sex, x in sex_cards:
                self.quiet_surface(x - 95, 260, 190, 190,
                                   selected=self.selected_sex == sex, alpha=210)
                self.draw_player_head_preview(
                    sex, self.selected_race, self.selected_job,
                    x, 355, 164,
                )
                self.text(sex, x, 235, 17, GOLD, "center", "center", True,
                          max_width=170, max_height=22, min_size=15)
        elif self.creation_step == 3:
            self.quiet_surface(230, 438, 720, 55, alpha=178)
            self.text("遊戲難度", 300, 466, 14, GOLD, "center", "center", True,
                      max_width=140, max_height=20, min_size=12)
            rule_items = (
                ("★", "標準", 365, (50, 76, 96)),
                ("★★", "強化", 555, (104, 76, 43)),
                ("★★★", "雙怪", 745, (100, 46, 55)),
            )
            for label, rule, left, _fill in rule_items:
                self.text(label, left + 38, 466, 13, (255, 216, 104),
                          "center", "center", True,
                          max_width=66, max_height=20, min_size=10)
                self.text(rule, left + 111, 466, 11, INK, "center", "center",
                          max_width=110, max_height=16, min_size=12)
            visible_jobs = self.visible_jobs()
            start_x = 590 - (len(visible_jobs) - 1) * 120
            for i, (job, _bonus) in enumerate(visible_jobs):
                x = start_x + i * 240
                self.quiet_surface(x - 108, 205, 216, 230, alpha=212)
                progress = self.job_difficulty(job)
                self.draw_player_preview(
                    self.selected_sex, self.selected_race, job,
                    x, 245, 155, 160,
                )
                self.text(job, x, 421, 17, INK, "center", "center", True,
                          max_width=190, max_height=22, min_size=15)
                star_y = 219
                for star in range(self.MAX_DIFFICULTY):
                    lit = star < progress
                    self.text("★", x - 24 + star * 24, star_y, 14,
                              GOLD if lit else (116, 93, 46), "center", "center", True,
                              max_width=20, max_height=19)
            self.quiet_surface(310, 143, 560, 56, alpha=210)
            self.text("將滑鼠移到職業框查看能力；點擊後立即開始冒險。",
                      590, 181, 12, INK, "center", "center",
                      max_width=520, max_height=18, min_size=12)
            page_label = f"{self.job_page + 1}/{self.max_job_page() + 1}"
            self.text(page_label, 590, 158, 11, MUTED, "center", "center",
                      max_width=80, max_height=16)

    def draw_journey_route_map(self) -> bool:
        """Draw any previewed chapter while keeping only legal nodes clickable."""
        all_nodes = self._journey_route_nodes()
        if not all_nodes:
            return False
        node_by_id = {
            self._route_node_id(node): node for node in all_nodes
            if self._route_node_id(node)
        }
        completed = {
            str(node_id) for node_id in getattr(self, "route_completed_ids", ())
        }
        selected_id = str(getattr(self, "route_selected_id", "") or "")
        active_id = str(getattr(self, "route_active_id", "") or "")
        try:
            reachable_ids = self.route_reachable_ids()
        except (AttributeError, TypeError, ValueError):
            try:
                reachable_ids = self.route_available_ids()
            except (AttributeError, TypeError, ValueError):
                reachable_ids = ()
        available = {str(node_id) for node_id in reachable_ids}

        chapter = max(1, min(5, int(getattr(
            self, "route_preview_chapter", 1
        ))))
        nodes = [
            node for node in all_nodes
            if self._route_value(node, "chapter", 0) == chapter
        ]
        if not nodes:
            return False

        def geometry(node: Any):
            if self._route_kind_key(node) == "boss":
                return route_boss_geometry()
            global_depth = int(self._route_value(node, "depth", 0))
            return route_node_geometry(
                int(self._route_value(node, "layer", global_depth % 7)),
                int(self._route_value(node, "lane", 0)),
            )

        progress_depth = max(
            (
                int(self._route_value(
                    node_by_id[node_id], "layer",
                    int(self._route_value(node_by_id[node_id], "depth", -1)) % 7,
                ))
                for node_id in completed | {active_id}
                if node_id in node_by_id
                and self._route_value(node_by_id[node_id], "chapter", 0) == chapter
            ),
            default=-1,
        )

        def node_state(node: Any) -> str:
            node_id = self._route_node_id(node)
            if node_id == active_id:
                return "active"
            if node_id == selected_id:
                return "selected"
            if node_id in completed:
                return "completed"
            if node_id in available:
                return "reachable"
            global_depth = int(self._route_value(node, "depth", 0))
            layer = int(self._route_value(node, "layer", global_depth % 7))
            return "bypassed" if layer <= progress_depth else "locked"

        state_colors = {
            "active": (90, 181, 225),
            "selected": (255, 210, 102),
            "completed": GOLD,
            "reachable": (104, 201, 158),
            "bypassed": (105, 110, 120),
            "locked": (118, 124, 136),
        }

        # Connections sit beneath markers. Their colour tells route history,
        # while solid/highlight versus thin/dim keeps the meaning visible even
        # when colour perception is limited.
        chapter_ids = {self._route_node_id(node) for node in nodes}
        for source in nodes:
            source_id = self._route_node_id(source)
            source_geometry = geometry(source)
            next_ids = self._route_value(source, "next_ids", ())
            if not isinstance(next_ids, (list, tuple, set)):
                continue
            for target_id_value in next_ids:
                target_id = str(target_id_value)
                if target_id not in chapter_ids or target_id not in node_by_id:
                    continue
                target = node_by_id[target_id]
                target_geometry = geometry(target)
                chosen_edge = (
                    target_id in {selected_id, active_id}
                    and source_id in completed
                )
                completed_edge = source_id in completed and target_id in completed
                reachable_edge = target_id in available and source_id in (completed | {active_id})
                if chosen_edge:
                    edge_color, edge_width = state_colors["selected"], 5
                elif completed_edge:
                    edge_color, edge_width = state_colors["completed"], 4
                elif reachable_edge:
                    edge_color, edge_width = state_colors["reachable"], 3
                else:
                    edge_color, edge_width = state_colors["locked"], 1
                arcade.draw_line(
                    source_geometry.center_x, source_geometry.center_y,
                    target_geometry.center_x, target_geometry.center_y,
                    (5, 8, 12, 185), edge_width + 3,
                )
                arcade.draw_line(
                    source_geometry.center_x, source_geometry.center_y,
                    target_geometry.center_x, target_geometry.center_y,
                    (*edge_color, 225 if edge_width >= 3 else 120), edge_width,
                )

        hovered_button = getattr(self, "hovered", None)
        hovered_node: Any | None = None
        if getattr(hovered_button, "group", "") == "route-node":
            hovered_node = min(
                nodes,
                key=lambda node: (
                    geometry(node).center_x - float(getattr(hovered_button, "x", -9999))
                ) ** 2 + (
                    geometry(node).center_y - float(getattr(hovered_button, "y", -9999))
                ) ** 2,
                default=None,
            )

        pulse = .5 + .5 * math.sin(self.battle_clock * 4.0)
        for node_spec in nodes:
            node_id = self._route_node_id(node_spec)
            point = geometry(node_spec)
            state = node_state(node_spec)
            state_color = state_colors[state]
            kind_key = self._route_kind_key(node_spec)
            _kind_label, _description, kind_color = self.route_kind_copy(kind_key)
            kind_icon = load_tight_ai_ui_texture(
                ROUTE_KIND_ICON_ASSETS.get(
                    kind_key, ROUTE_KIND_ICON_ASSETS["battle"],
                ),
                2,
            )
            node_size = (
                45 if state in {"active", "selected"}
                else 41 if state == "reachable"
                else 37
            )
            width, height = fit_texture_size(kind_icon, node_size, node_size)
            alpha = 245 if state not in {"locked", "bypassed"} else 170 if state == "bypassed" else 205
            if state in {"active", "selected"}:
                arcade.draw_circle_outline(
                    point.center_x, point.center_y, 25 + pulse * 3,
                    (*state_color, 155 + round(pulse * 80)), 3,
                )
            arcade.draw_circle_filled(
                point.center_x, point.center_y, 23,
                (7, 10, 15, 220 if state not in {"locked", "bypassed"} else 175),
            )
            arcade.draw_texture_rect(
                kind_icon,
                arcade.XYWH(point.center_x, point.center_y, width, height),
                color=(
                    Color(255, 255, 255)
                    if state not in {"locked", "bypassed"}
                    else Color(142, 146, 155)
                ),
                alpha=alpha,
            )
            arcade.draw_circle_outline(
                point.center_x, point.center_y, 21,
                (*kind_color, 235 if state not in {"locked", "bypassed"} else 105),
                3 if node_spec is hovered_node else 2,
            )
            if node_spec is hovered_node:
                arcade.draw_circle_outline(
                    point.center_x, point.center_y, 28,
                    (235, 240, 248, 220), 2,
                )
            if state == "completed":
                self.text("✓", point.center_x + 17, point.center_y + 17, 12,
                          GOLD, "center", "center", True,
                          max_width=18, max_height=16, min_size=10)
            elif state == "bypassed":
                self.text("×", point.center_x + 16, point.center_y + 16, 10,
                          (150, 154, 163), "center", "center", True,
                          max_width=16, max_height=14, min_size=9)

        preview_node = hovered_node or node_by_id.get(selected_id) or node_by_id.get(active_id)
        self.quiet_surface(75, 104, 1030, 72, alpha=230)
        chapter_number = int(chapter) if str(chapter).lstrip("-").isdigit() else chapter
        chapter_label = f"第 {max(1, chapter_number)} 章" if isinstance(chapter_number, int) else f"章節 {chapter_number}"
        current_chapter = int(getattr(self, "current_route_chapter", lambda: 1)())
        preview_suffix = "" if chapter_number == current_chapter else "｜未來路線預覽"
        if preview_node is not None:
            _kind_label, description, kind_color = self.route_kind_copy(
                self._route_kind_key(preview_node)
            )
            preview_id = self._route_node_id(preview_node)
            prefix = "已選路線" if preview_id == selected_id else "目前位置" if preview_id == active_id else "節點預覽"
            self.text(f"{chapter_label}{preview_suffix}｜{prefix}", 590, 158, 17,
                      kind_color, "center", "center", True,
                      max_width=900, max_height=23)
            self.text(description, 590, 132, 12, INK, "center", "center",
                      max_width=900, max_height=18, min_size=11)
        else:
            self.text(f"{chapter_label}{preview_suffix}｜選擇下一段路線", 590, 155, 17,
                      GOLD, "center", "center", True,
                      max_width=900, max_height=23)
        self.text("將滑鼠移到可前往的節點查看內容；點擊後在下方確認。",
                  590, 113, 10, MUTED, "center", "center",
                  max_width=900, max_height=15, min_size=10)
        return True

    def _elite_reward_choice_items(self) -> tuple[Any, ...]:
        if bool(getattr(self, "elite_reward_claimed", False)):
            return ()
        for field in (
            "elite_reward_choices", "pending_elite_reward_choices",
            "pending_elite_potion_choices", "elite_potion_choices",
        ):
            choices = getattr(self, field, ())
            if isinstance(choices, (list, tuple)) and choices:
                return tuple(choices[:3])
        return ()

    def draw_game(self) -> None:
        p = self.player
        job_text = p.job if not p.sub_job else f"{p.job}/{p.sub_job}"
        immersive_scenes = {
            self.Scene.ADVENTURE, self.Scene.EVENT, self.Scene.TALENT,
            self.Scene.SUBCLASS, self.Scene.SHOP, self.Scene.CAMPFIRE,
            self.Scene.REWARD, self.Scene.END,
        }
        immersive_scene = self.scene in immersive_scenes
        if self.scene != self.Scene.BATTLE and not immersive_scene:
            self.panel(20, 465, 315, 235, "角色資料")
            stat_rows = (
                (f"{p.name}｜{p.sex}", 628, 21, INK, True),
                (f"{p.race}・{job_text}　{self.level_label(p.lv)}", 600, 16, GOLD, False),
                (f"血量　{max(0, p.hp)} / {p.max_hp}", 570, 16, RED, True),
                (f"攻擊　{p.attack}　　防禦　{p.defense}", 542, 15, INK, False),
                (f"暴擊　{self.displayed_critical_chance():.0f}%　金幣　{p.gold}G　藥水　{self.total_potions()}", 516, 14, INK, False),
            )
            for value, y, size, color, bold in stat_rows:
                self.text(value, 40, y, size, color, "left", "center", bold,
                          max_width=270, max_height=24, min_size=11)

        battle_log = self.scene == self.Scene.BATTLE
        log_expanded = battle_log and self.battle_log_expanded
        show_inline_log = not immersive_scene and not battle_log
        # In combat the log is a requested overlay, never a persistent column.
        # Immersive scenes also never expose this legacy rail.  The old code
        # drew it at y=-1000 but still translated, wrapped, measured and
        # submitted every card each frame.
        log_bottom = -1000 if immersive_scene or battle_log else 15
        log_height = 685 if log_expanded else (250 if battle_log else 430)
        log_title = "戰鬥紀錄" if log_expanded else "冒險紀錄"
        if show_inline_log:
            self.panel(20, log_bottom, 315, log_height, log_title)
        log_messages = self.combat_messages if battle_log else self.messages
        available_log_height = max(64, log_height - 48)
        if show_inline_log:
            prepared_logs = self.prepared_log_cards(messages=log_messages)
            maximum_log_scroll = self.max_log_scroll(
                prepared_logs, available_log_height
            )
            self.log_scroll = max(0, min(self.log_scroll, maximum_log_scroll))
            visible_logs = self.visible_log_cards(
                available_height=available_log_height, messages=log_messages,
                prepared=prepared_logs,
            )
        else:
            prepared_logs = []
            maximum_log_scroll = 0
            visible_logs = []
        log_cursor = log_bottom + log_height - 51.0
        for index, (icon, lines, accent, card_height) in enumerate(visible_logs):
            newest = index == 0 and self.log_scroll == 0
            card_bottom = log_cursor - card_height
            if newest:
                self.quiet_surface(34, card_bottom, 287, card_height,
                                   selected=True, alpha=145)
            self.text(self.log_badge_text(icon), 57,
                      card_bottom + card_height / 2, 10,
                      accent, "center", "center", True,
                      max_width=18, max_height=17, min_size=8)
            line_color = INK if newest else (194, 201, 210)
            line_start_y = card_bottom + card_height / 2 + (len(lines) - 1) * 10
            for line_index, line in enumerate(lines):
                self.text(line, 76, line_start_y - line_index * 20, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=20, min_size=10)
            log_cursor = card_bottom - 5
        if maximum_log_scroll > 0:
            track_left, track_bottom = 321.0, log_bottom + 17.0
            track_width, track_height = 10, max(30, log_height - 49)
            thumb_height = max(35, int(track_height * len(visible_logs) / len(prepared_logs)))
            thumb_travel = track_height - thumb_height
            scroll_ratio = self.log_scroll / maximum_log_scroll
            thumb_bottom = track_bottom + thumb_travel * (1 - scroll_ratio)
            track_key = ("track", track_width, track_height)
            track_texture = self._scroll_skin_cache.get(track_key)
            if track_texture is None:
                track_texture = make_log_scroll_skin(track_width, track_height, "track")
                self._scroll_skin_cache[track_key] = track_texture
            thumb_key = ("thumb", track_width, thumb_height, self.log_scroll_dragging)
            thumb_texture = self._scroll_skin_cache.get(thumb_key)
            if thumb_texture is None:
                thumb_texture = make_log_scroll_skin(
                    track_width, thumb_height, "thumb", self.log_scroll_dragging
                )
                self._scroll_skin_cache[thumb_key] = thumb_texture
            arcade.draw_texture_rect(
                track_texture,
                arcade.XYWH(track_left + track_width / 2,
                            track_bottom + track_height / 2,
                            track_width, track_height),
            )
            arcade.draw_texture_rect(
                thumb_texture,
                arcade.XYWH(track_left + track_width / 2,
                            thumb_bottom + thumb_height / 2,
                            track_width, thumb_height),
            )
            self._log_scroll_geometry = (
                track_left, track_bottom, track_width, track_height,
                thumb_bottom, float(thumb_height), float(maximum_log_scroll),
                float(max(1, len(visible_logs))),
            )
        else:
            self._log_scroll_geometry = None
            self.log_scroll_dragging = False

        if immersive_scene or (battle_log and not log_expanded):
            self._log_scroll_geometry = None
            self.log_scroll_dragging = False

        if self.scene == self.Scene.TALENT:
            # Preserve the dedicated progression artwork while keeping node
            # copy readable.  Tier cards provide the local contrast, so this
            # veil can stay light enough for the scene identity to show.
            self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 5, 10, 72))
            self.framed_surface(260, 580, 660, 104, kind="panel",
                                accent=COLORS.brass, alpha=244)
            self.text(f"{p.job}天賦", 590, 653, 27, GOLD, "center", "center", True,
                      max_width=620, max_height=34)
            self.text(f"剩餘點數 {p.talent_points}｜已投入 {self.class_talent_spent()} / 10",
                      590, 621, 14, INK, "center", "center",
                      max_width=620, max_height=22)
            self.text("每層投入 3 點就會開啟下一層；最後一層只需要 1 點。",
                      590, 594, 12, MUTED, "center", "center",
                      max_width=620, max_height=18, min_size=12)
            tier_titles = {
                1: "第一層：基本強化",
                2: "第二層：技能強化",
                3: "第三層：生存能力",
                4: "第四層：最終技能",
            }

            # Connectors are drawn first so they sit beneath nodes.  A lit link
            # means the previous tier requirement has been met.
            for tier in (1, 2):
                source_y = 457 - (tier - 1) * 125
                target_y = 428 - (tier - 1) * 125
                link_active = self.class_tier_spent(tier) >= 3
                link_color = COLORS.brass if link_active else COLORS.line[:3]
                link_alpha = 225 if link_active else 85
                for branch_x in (350, 830):
                    arcade.draw_line(branch_x, source_y, branch_x, target_y,
                                     (2, 4, 8, 205), 7)
                    arcade.draw_line(branch_x, source_y, branch_x, target_y,
                                     (*link_color, link_alpha), 3)
            final_active = self.class_tier_spent(3) >= 3
            final_color = COLORS.brass if final_active else COLORS.line[:3]
            final_alpha = 225 if final_active else 85
            for branch_x in (350, 830):
                arcade.draw_line(branch_x, 207, 590, 178,
                                 (2, 4, 8, 205), 7)
                arcade.draw_line(branch_x, 207, 590, 178,
                                 (*final_color, final_alpha), 3)

            for tier, title in tier_titles.items():
                button_y = 505 - (tier - 1) * 125 if tier < 4 else 130
                if tier < 4:
                    self.quiet_surface(172, button_y - 57, 836, 114,
                                       alpha=112)
                    title_y = button_y + 18
                else:
                    self.quiet_surface(410, button_y - 56, 360, 112,
                                       alpha=126)
                    title_y = button_y + 61
                self.text(title, 590, title_y, 12, GOLD, "center", "center", True,
                          max_width=176 if tier < 4 else 260,
                          max_height=18, min_size=12)
            for talent_id, talent in self.class_talent_defs().items():
                tier = int(talent["tier"])
                side = int(talent["side"])
                if tier < 4:
                    card_left = 200 + side * 480
                    button_y = 505 - (tier - 1) * 125
                else:
                    card_left = 440
                    button_y = 130
                rank = self.class_talent_rank(talent_id)
                unlocked = tier == 1 or self.class_tier_spent(tier - 1) >= 3
                self.framed_surface(
                    card_left, button_y - 48, 300, 96, kind="card",
                    accent=COLORS.ember if rank > 0 else COLORS.line[:3],
                    enabled=unlocked, selected=rank > 0, alpha=218,
                )
                job_dir = {
                    "戰士": "warrior", "法師": "mage", "聖騎士": "paladin",
                    "盜賊": "rogue", "術士": "warlock",
                }.get(p.job, "warrior")
                # Generated icons use different transparent margins. Tight
                # cropping makes the visible symbol share the slot centre.
                icon = load_tight_ai_ui_texture(
                    f"icons/talents/{job_dir}/{talent_id}.png", 3
                )
                if icon is not None:
                    slot = load_ai_ui_texture("frame.skill_slot")
                    arcade.draw_texture_rect(
                        slot, arcade.XYWH(card_left + 54, button_y, 74, 74),
                        color=Color(*(COLORS.ember if rank > 0 else (160, 163, 164))),
                        alpha=245 if unlocked else 100,
                    )
                    icon_width, icon_height = fit_texture_size(icon, 48, 48)
                    arcade.draw_texture_rect(
                        icon, arcade.XYWH(card_left + 54, button_y,
                                          icon_width, icon_height),
                        alpha=255 if unlocked else 90,
                    )
        elif self.scene == self.Scene.SUBCLASS:
            # Choice cards are the meaningful containers on this screen.  A
            # full-page parent panel around them was redundant frame-in-frame.
            self.quiet_surface(220, 465, 740, 112, alpha=176)
            self.text("選擇副職業", 590, 555, 34, GOLD, "center", "center", True,
                      max_width=800, max_height=45)
            self.text(f"{p.name}來到第 10 關，可以再選一個不同於{p.job}的職業。",
                      590, 510, 17, INK, "center", "center",
                      max_width=770, max_height=26)
            self.text("你會多一個專屬技能，原本的能力和天賦都會保留。",
                      590, 480, 14, MUTED, "center", "center",
                      max_width=770, max_height=24, min_size=10)
            centers = ((380, 415), (800, 415), (380, 250), (800, 250))
            for index, job in enumerate(self.subclass_options()):
                x, y = centers[index]
                self.quiet_surface(x - 150, y - 80, 300, 145,
                                   alpha=205)
                left = x - 122
                text_top = y - 22
                self.text(self.job_skill_name(job), left, text_top, 17, GOLD,
                          "left", "center", True,
                          max_width=244, max_height=22, min_size=15)
                description_lines, description_size = self.fitted_wrapped_lines(
                    self.job_skill_description(job), 244, 12,
                    min_size=11, max_lines=3,
                )
                for line_index, line in enumerate(description_lines):
                    self.text(line, left, text_top - 24 - line_index * 18, 12, INK,
                              "left", "center", max_width=244, max_height=16,
                              min_size=description_size)
        elif self.scene == self.Scene.BATTLE and self.enemy:
            e = self.enemy
            self.battle_canvas()
            camera_x, camera_y = self.combat_camera_offset()
            player_offset = 0.0
            enemy_offset = 0.0
            if self.attack_animation:
                elapsed = self.attack_animation.elapsed
                if elapsed <= .17:
                    motion = math.sin((elapsed / .17) * math.pi / 2)
                else:
                    motion = max(0, 1 - (elapsed - .17) / .31)
                if self.attack_animation.attacker == "player":
                    lunge = 18 if p.job in {"法師", "術士"} else 64
                    player_offset = lunge * motion
                else:
                    enemy_offset = -64 * motion
                if self.attack_animation.critical and elapsed >= .17:
                    impact_phase = min(1, (elapsed - .17) / .31)
                    shake = math.sin(impact_phase * math.pi * 8) * 14 * (1 - impact_phase)
                    if self.attack_animation.attacker == "player":
                        enemy_offset += shake
                    else:
                        player_offset += shake
            player_offset += self.combat_knockback_offset("player")
            player_x = 330.0
            player_pose = (
                "attack"
                if self.attack_animation and self.attack_animation.attacker == "player"
                else combat_reaction_pose(self.attack_animation, "player")
            )
            player_texture = {
                "idle": self.hero_portrait,
                "attack": self.hero_attack_portrait,
                "hurt": getattr(self, "hero_hurt_portrait", None),
                "block": getattr(self, "hero_block_portrait", None),
            }.get(player_pose) or self.hero_portrait
            player_width, player_height = fit_player_texture_size(
                player_texture, p.sex, p.race, p.job, player_pose, 230.0, 270.0,
            )
            player_draw_x = player_x
            sex_dir = PLAYER_ART_SEX_DIRS.get(p.sex)
            race_dir = PLAYER_ART_RACE_DIRS.get(p.race)
            filename = PLAYER_ART_JOB_FILES.get(p.job)
            if sex_dir and race_dir and filename:
                player_scale = player_height / max(1.0, float(player_texture.height))
                player_anchor_x = player_pose_anchor_x(
                    sex_dir, race_dir, Path(filename).stem, player_pose,
                )
                player_draw_x -= canvas_center_offset(
                    player_anchor_x, float(player_texture.width), player_scale,
                )
            player_visible_bottom, _ = self.texture_visible_vertical_bounds(
                player_texture, player_height
            )
            # This is the shared midground road baseline in stage_01. Keeping
            # health bars below it preserves contact while leaving the dock clear.
            player_ground_y = 228.0
            player_y = player_ground_y - player_visible_bottom
            ground_shadow = load_ai_ui_texture("icons/markers/ground_shadow.png")
            player_visible_left, player_visible_right = self.texture_visible_horizontal_bounds(
                player_texture, player_width
            )
            arcade.draw_texture_rect(
                ground_shadow,
                arcade.XYWH(player_x + camera_x, player_ground_y + 3 + camera_y,
                            max(88.0, (player_visible_right - player_visible_left) * .72),
                            18), alpha=105,
            )
            player_rect = arcade.XYWH(
                player_draw_x + player_offset + camera_x, player_y + camera_y,
                player_width, player_height,
            )
            arcade.draw_texture_rect(
                player_texture, player_rect,
            )
            self.draw_combat_hit_flash(
                player_texture, player_rect,
                self.combat_flash_alpha("player"),
            )
            dual = len(self.enemies) > 1
            self.enemy_hitboxes = [(0.0, 0.0, 0.0, 0.0)] * len(self.enemies)
            self.enemy_intent_hitboxes = [(0.0, 0.0, 0.0, 0.0)] * len(self.enemies)
            anim_index = self.attack_animation.enemy_index if self.attack_animation else -1
            if dual:
                target_index = min(self.target_index, len(self.enemies) - 1)
                # Paint the chosen target last so its forward step also reads
                # as foreground when the portraits overlap visually.
                draw_order = [index for index in range(len(self.enemies))
                              if index != target_index] + [target_index]
                for index in draw_order:
                    foe = self.enemies[index]
                    enemy_is_attacking = (
                        self.attack_animation is not None
                        and self.attack_animation.attacker == "enemy"
                        and index == anim_index
                    )
                    enemy_pose = (
                        "attack" if enemy_is_attacking
                        else combat_reaction_pose(
                            self.attack_animation, "enemy", index,
                        )
                    )
                    portraits = {
                        "idle": self.enemy_portraits,
                        "attack": self.enemy_attack_portraits,
                        "hurt": getattr(self, "enemy_hurt_portraits", ()),
                        "block": getattr(self, "enemy_block_portraits", ()),
                    }[enemy_pose]
                    fallback = {
                        "idle": self.enemy_portrait,
                        "attack": self.enemy_attack_portrait,
                        "hurt": getattr(self, "enemy_hurt_portrait", None),
                        "block": getattr(self, "enemy_block_portrait", None),
                    }[enemy_pose] or self.enemy_portrait
                    portrait = portraits[index] if index < len(portraits) else fallback
                    portrait_width, portrait_height = self.battle_enemy_texture_size(
                        portrait, index, enemy_pose
                    )
                    portrait_x, portrait_y = self.battle_enemy_visual_position(
                        index, portrait, portrait_height,
                        enemy_pose,
                    )
                    _anchor_x, ground_y = self.battle_enemy_ground_position(index)
                    ex = (portrait_x
                          + (enemy_offset if index == anim_index else 0)
                          + self.combat_knockback_offset("enemy", index))
                    shadow_alpha = 115 if index == target_index else 72
                    visible_left, visible_right = self.texture_visible_horizontal_bounds(
                        portrait, portrait_width
                    )
                    visible_bottom, visible_top = self.texture_visible_vertical_bounds(
                        portrait, portrait_height
                    )
                    arcade.draw_texture_rect(
                        ground_shadow,
                        arcade.XYWH(portrait_x + camera_x, ground_y + 3 + camera_y,
                                    max(70.0, (visible_right - visible_left) * .72),
                                    16), alpha=shadow_alpha,
                    )
                    enemy_rect = arcade.XYWH(
                        ex + camera_x, portrait_y + camera_y,
                        portrait_width, portrait_height,
                    )
                    arcade.draw_texture_rect(
                        portrait, enemy_rect,
                    )
                    self.draw_combat_hit_flash(
                        portrait, enemy_rect,
                        self.combat_flash_alpha("enemy", index),
                    )
                    self.enemy_hitboxes[index] = (
                        portrait_x + visible_left,
                        portrait_y + visible_bottom,
                        visible_right - visible_left,
                        visible_top - visible_bottom,
                    )
                    targeted = index == self.target_index
                    info_x = portrait_x
                    intent_y = self.portrait_visual_top(
                        portrait, portrait_y, portrait_height
                    ) + 27
                    intent_x = portrait_x + (-52 if portrait_x < 850 else 52)
                    impact_hides_intent = (
                        self.combat_impact_remaining > 0
                        and self.combat_impact_target == "enemy"
                        and self.combat_impact_enemy_index == index
                    )
                    if not impact_hides_intent:
                        self.draw_intent_icon(
                            foe, intent_x, intent_y,
                            selected=targeted,
                        )
                    self.enemy_intent_hitboxes[index] = (
                        intent_x - 41, intent_y - 41, 82, 82
                    )
                    displayed_hp = self.display_enemy_hp[index]
                    displayed_block = self.display_enemy_block[index]
                    self.bar(info_x - 88, ground_y - 48, 176,
                             displayed_hp, foe.max_hp, RED,
                             f"{max(0, foe.hp)}/{foe.max_hp}", foe.hp)
                    self.text(foe.name, info_x, ground_y - 10, 10, INK,
                              "center", "center", True,
                              max_width=200, max_height=14, min_size=12)
                    if foe.block > 0 or displayed_block > .1:
                        self.shield_bar(info_x - 88, ground_y - 76, 176,
                                        displayed_block, foe.max_hp, foe.block)
                    self.draw_status_badges(
                        collect_enemy_status_badges(foe),
                        info_x, intent_y + 45, 196,
                    )
            else:
                enemy_pose = (
                    "attack"
                    if self.attack_animation and self.attack_animation.attacker == "enemy"
                    else combat_reaction_pose(self.attack_animation, "enemy", 0)
                )
                enemy_texture = {
                    "idle": self.enemy_portrait,
                    "attack": self.enemy_attack_portrait,
                    "hurt": getattr(self, "enemy_hurt_portrait", None),
                    "block": getattr(self, "enemy_block_portrait", None),
                }[enemy_pose] or self.enemy_portrait
                enemy_width, enemy_height = self.battle_enemy_texture_size(
                    enemy_texture, 0, enemy_pose
                )
                enemy_x, enemy_y = self.battle_enemy_visual_position(
                    0, enemy_texture, enemy_height,
                    enemy_pose,
                )
                _anchor_x, enemy_ground_y = self.battle_enemy_ground_position(0)
                visible_bottom, _ = self.texture_visible_vertical_bounds(
                    enemy_texture, enemy_height
                )
                visible_left, visible_right = self.texture_visible_horizontal_bounds(
                    enemy_texture, enemy_width
                )
                arcade.draw_texture_rect(
                    ground_shadow,
                    arcade.XYWH(enemy_x + camera_x, enemy_ground_y + 3 + camera_y,
                                max(90.0, (visible_right - visible_left) * .72),
                                18), alpha=105,
                )
                enemy_rect = arcade.XYWH(
                    enemy_x + enemy_offset
                    + self.combat_knockback_offset("enemy", 0) + camera_x,
                    enemy_y + camera_y, enemy_width, enemy_height,
                )
                arcade.draw_texture_rect(
                    enemy_texture, enemy_rect,
                )
                self.draw_combat_hit_flash(
                    enemy_texture, enemy_rect,
                    self.combat_flash_alpha("enemy", 0),
                )
                enemy_visible_bottom, enemy_visible_top = (
                    self.texture_visible_vertical_bounds(enemy_texture, enemy_height)
                )
                self.enemy_hitboxes[0] = (
                    enemy_x + visible_left,
                    enemy_y + enemy_visible_bottom,
                    visible_right - visible_left,
                    enemy_visible_top - enemy_visible_bottom,
                )
                enemy_intent_y = self.portrait_visual_top(
                    enemy_texture, enemy_y, enemy_height
                ) + 27
                enemy_intent_x = enemy_x + 56
                impact_hides_intent = (
                    self.combat_impact_remaining > 0
                    and self.combat_impact_target == "enemy"
                    and self.combat_impact_enemy_index == 0
                )
                if not impact_hides_intent:
                    self.draw_intent_icon(
                        e, enemy_intent_x, enemy_intent_y
                    )
                self.enemy_intent_hitboxes[0] = (
                    enemy_intent_x - 41, enemy_intent_y - 41, 82, 82
                )
            self.draw_skill_effects()
            self.bar(210, player_ground_y - 48, 240,
                     self.display_player_hp, p.max_hp, RED,
                     f"{max(0, p.hp)}/{p.max_hp}", p.hp)
            self.text(f"{p.name}・{p.job}", 330, player_ground_y - 10,
                      11, INK, "center", "center", True,
                      max_width=300, max_height=15, min_size=12)
            if self.player_block > 0 or self.display_player_block > .1:
                self.shield_bar(210, player_ground_y - 76, 240,
                                self.display_player_block, p.max_hp,
                                self.player_block)
            if not dual:
                displayed_enemy_hp = self.display_enemy_hp[0]
                displayed_enemy_block = self.display_enemy_block[0]
                self.bar(730, enemy_ground_y - 48, 240,
                         displayed_enemy_hp, e.max_hp, RED,
                         f"{max(0, e.hp)}/{e.max_hp}", e.hp)
                self.text(e.name, 850, enemy_ground_y - 10, 11, INK,
                          "center", "center", True,
                          max_width=232, max_height=15, min_size=9)
                if self.enemy_block > 0 or displayed_enemy_block > .1:
                    self.shield_bar(730, enemy_ground_y - 76, 240,
                                    displayed_enemy_block, e.max_hp,
                                    self.enemy_block)
                self.draw_status_badges(
                    collect_enemy_status_badges(e),
                    850, enemy_intent_y + 47, 280,
                )
            self.draw_status_badges(
                collect_player_status_badges(self),
                330,
                self.portrait_visual_top(
                    player_texture, player_y, player_height
                ) + 30,
                320,
            )
            self.prime_attack_floating_label()
            for floating in self.floating_damage:
                if floating.target == "player":
                    x = 330
                    floating_base_y = player_y + 142
                elif dual:
                    floating_index = min(floating.target_index, len(self.enemies) - 1)
                    x, floating_enemy_y = self.battle_enemy_visual_position(floating_index)
                    floating_base_y = floating_enemy_y + 112
                else:
                    x, floating_enemy_y = self.battle_enemy_visual_position(0)
                    floating_base_y = floating_enemy_y + 137
                on_dual_enemy = dual and floating.target == "enemy"
                float_progress = min(1.0, floating.elapsed / 1.05)
                rise = 72 * (1.0 - (1.0 - float_progress) ** 2)
                bounce = math.sin(min(1.0, float_progress / .33) * math.pi) * 22
                y = floating_base_y + rise + bounce
                if floating.critical:
                    x += math.sin(float_progress * math.pi * 3) * 4
                fade_progress = max(0.0, (float_progress - .58) / .42)
                alpha = int(255 * (1.0 - fade_progress) ** 1.4)
                if (not floating.critical and not floating.healing
                        and not floating.shielding
                        and floating.amount > 0 and floating.elapsed < .42):
                    impact_phase = floating.elapsed / .42
                    impact_size = (78 + 54 * impact_phase) * (
                        .78 if on_dual_enemy else 1.0
                    )
                    impact_y = (player_y + 8 if floating.target == "player" else
                                floating_base_y - (24 if on_dual_enemy else 32))
                    arcade.draw_texture_rect(
                        self._ensure_critical_effect(),
                        arcade.XYWH(x, impact_y, impact_size, impact_size),
                        angle=(-12 if floating.target == "player" else 12),
                        alpha=int(120 * (1 - impact_phase)),
                    )
                if (floating.critical and not floating.healing
                        and not floating.shielding and floating.elapsed < .68):
                    burst_phase = floating.elapsed / .68
                    burst_alpha = int(255 * (1 - burst_phase) ** 1.35)
                    burst_scale = .72 if on_dual_enemy else 1.0
                    burst_size = (125 + 115 * burst_phase) * burst_scale
                    burst_y = (player_y + 10 if floating.target == "player" else
                               floating_base_y - (28 if on_dual_enemy else 36))
                    burst_angle = (-18 if floating.target == "player" else 18) + burst_phase * 42
                    arcade.draw_texture_rect(
                        self._ensure_critical_effect(),
                        arcade.XYWH(x, burst_y, burst_size, burst_size),
                        angle=burst_angle,
                        alpha=burst_alpha,
                    )
                    if burst_phase < .38:
                        echo_phase = burst_phase / .38
                        arcade.draw_texture_rect(
                            self._ensure_critical_effect(),
                            arcade.XYWH(x, burst_y, burst_size * (.58 + echo_phase * .28),
                                        burst_size * (.58 + echo_phase * .28)),
                            angle=-burst_angle * .65,
                            alpha=int(burst_alpha * .48),
                        )
                if floating.shielding:
                    value, color = f"◆ +{floating.amount}", (*BLUE, alpha)
                elif floating.healing:
                    value, color = f"+{floating.amount}", (*GREEN, alpha)
                else:
                    value = "0" if floating.amount == 0 else f"{'暴擊 ' if floating.critical else ''}-{floating.amount}"
                    color = (*GOLD, alpha) if floating.critical else (*RED, alpha)
                value = self.display_text(value)
                if (floating.label is None
                        or getattr(floating.label, "text", "") != value):
                    float_size = 31 if floating.critical else 27
                    while True:
                        floating.label = arcade.Text(
                            value, x, y, color, float_size,
                            anchor_x="center", anchor_y="center", bold=True,
                            font_name=current_font_stack(),
                        )
                        if floating.label.content_width <= 230 or float_size <= 13:
                            break
                        float_size -= 1
                    floating.outline_labels = [
                        arcade.Text(
                            value, x + dx, y + dy, (4, 7, 11, min(230, alpha)),
                            float_size, anchor_x="center", anchor_y="center",
                            bold=True, font_name=current_font_stack(),
                        )
                        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2))
                    ]
                else:
                    floating.label.x = x
                    floating.label.y = y
                    floating.label.color = color
                for outline, (dx, dy) in zip(
                        floating.outline_labels,
                        ((-2, 0), (2, 0), (0, -2), (0, 2))):
                    outline.x = x + dx
                    outline.y = y + dy
                    outline.color = (4, 7, 11, min(230, alpha))
                    outline.draw()
                floating.label.draw()
        elif self.scene == self.Scene.REWARD:
            self.panel(275, 125, 630, 465)
            elite_choices = self._elite_reward_choice_items()
            reward_icon = load_context_icon("reward_ember")
            arcade.draw_texture_rect(reward_icon, arcade.XYWH(590, 493, 62, 62))
            self.text("戰鬥勝利", 590, 550, 30, GOLD, "center", "center", True,
                      max_width=560, max_height=48)
            self.text(f"金幣 +{self.pending_reward_gold}G", 590, 435, 20, GOLD,
                      "center", "center", True, max_width=470, max_height=28)
            level_text = (
                f"等級提升　{self.reward_level_before} → {self.reward_level_after}"
                if self.reward_level_after > self.reward_level_before else
                f"目前等級 {self.reward_level_after}"
            )
            self.text(level_text, 590, 397, 17, INK, "center", "center", True,
                      max_width=470, max_height=24)
            self.text(
                f"目前血量 {max(0, p.hp)}/{p.max_hp}　攻擊 {p.attack}　防禦 {p.defense}　暴擊 {self.displayed_critical_chance():.0f}%",
                590, 330 if elite_choices else 315, 15, INK, "center", "center",
                max_width=560, max_height=24, min_size=13,
            )
            if p.talent_points > 0:
                self.text(f"還有 {p.talent_points} 點天賦可以使用", 590,
                          300 if elite_choices else 275, 13 if elite_choices else 15,
                          PURPLE, "center", "center", True,
                          max_width=500, max_height=22)
            if elite_choices:
                self.text("菁英戰利品｜免費選擇一瓶藥水", 590, 270, 15,
                          GOLD, "center", "center", True,
                          max_width=520, max_height=22)
                # The three reward Buttons are drawn immediately after the
                # scene and already carry their existing potion icons. Keeping
                # this layer to a single heading avoids drawing duplicate art
                # underneath those interactive controls.
        elif self.scene == self.Scene.CAMPFIRE:
            self.activity_canvas(self._ensure_campfire_background(), "營火")
            self.quiet_surface(260, 576, 660, 60, alpha=212)
            self.text(f"{p.name or '冒險者'}｜{p.race}・{p.job}｜等級 {p.lv}",
                      590, 618, 14, GOLD, "center", "center", True,
                      max_width=620, max_height=22, min_size=12)
            self.text(
                f"血量 {max(0, p.hp)}/{p.max_hp}　攻擊 {p.attack}　防禦 {p.defense}　"
                f"暴擊 {self.displayed_critical_chance():.0f}%　金幣 {p.gold}G",
                590, 592, 13, INK, "center", "center", True,
                max_width=620, max_height=22, min_size=11,
            )
            self.quiet_surface(318, 94, 544, 48, alpha=208)
            self.draw_text_block(
                "營火只能選擇一項；確認後會立即繼續旅程。",
                590, 118, 524, 12, INK, line_spacing=18,
                max_lines=2, min_size=11, bold=True,
            )
        elif self.scene == self.Scene.SHOP:
            self.activity_canvas(self._ensure_shop_background(), "藥水商")
            shop_inventory = getattr(
                self, "shop_inventory", tuple(self.POTIONS)
            )
            affordable_count = sum(
                1 for kind in shop_inventory if self.potion_available(kind)
            )
            self.quiet_surface(250, 590, 680, 44, alpha=212)
            self.draw_text_block(
                f"持有 {p.gold}G｜買得起 {affordable_count}/{len(shop_inventory)} 種｜本關庫存已鎖定",
                590, 612, 620, 14, INK, line_spacing=19,
                max_lines=2, min_size=12, bold=True,
            )
            self.quiet_surface(190, 540, 800, 40, alpha=196)
            self.draw_text_block(
                self.shop_lore, 590, 560, 750, 12, MUTED,
                line_spacing=17, max_lines=2, min_size=11,
            )
            # Compact buttons draw their own surface; the former full-width
            # backing strips obscured the merchant shelf without adding meaning.
        elif self.scene == self.Scene.EVENT:
            background_number = self.event_background_number(self.event_number)
            self.activity_canvas(self.event_background(background_number), self.event_title)
            (panel_left, panel_bottom, panel_width, panel_height,
             content_left, content_width, _button_x, _button_ys) = self.event_panel_layout()
            content_center_y = panel_bottom + panel_height / 2
            self.quiet_surface(panel_left, panel_bottom,
                               panel_width, panel_height, alpha=232)
            if self.event_resolved and len(self.event_messages) >= 3:
                choice_message = self.event_messages[-3]
                result_message = self.event_messages[-2]
                changes_message = self.event_messages[-1]
                choice_text = choice_message.removeprefix("你選擇").rstrip("。")
                blocks = (
                    (self.wrap_text_pixels(choice_text, content_width, 11), 11, GOLD, 17, True),
                    (self.wrap_text_pixels(result_message, content_width, 13), 13, INK, 20, False),
                    (self.wrap_text_pixels(changes_message, content_width, 11), 11, GOLD, 17, True),
                )
                visible_blocks = [block for block in blocks if block[0]]
                total_height = sum(len(lines) * spacing
                                   for lines, _, _, spacing, _ in visible_blocks)
                total_height += max(0, len(visible_blocks) - 1) * 8
                cursor_y = content_center_y + total_height / 2
                for block_index, (lines, size, text_color, spacing, bold) in enumerate(visible_blocks):
                    if block_index:
                        cursor_y -= 8
                    for line in lines:
                        cursor_y -= spacing / 2
                        self.text(line, content_left, cursor_y, size, text_color,
                                  "left", "center", bold, max_width=content_width,
                                  max_height=spacing, min_size=max(9, size - 2))
                        cursor_y -= spacing / 2
            else:
                intro = self.event_messages[-1] if self.event_messages else ""
                intro_lines = self.wrap_text_pixels(intro, content_width, 13)
                intro_start = content_center_y + (len(intro_lines) - 1) * 10.5
                for line_index, line in enumerate(intro_lines):
                    self.text(line, content_left, intro_start - line_index * 21,
                              13, INK, "left", "center",
                              max_width=content_width, max_height=19, min_size=10)
        elif self.scene == self.Scene.END:
            self._log_scroll_geometry = None
            ending = load_end_background(self.victory)
            source_ratio = ending.width / max(1.0, ending.height)
            canvas_ratio = SCREEN_WIDTH / SCREEN_HEIGHT
            if source_ratio >= canvas_ratio:
                draw_height = float(SCREEN_HEIGHT)
                draw_width = draw_height * source_ratio
            else:
                draw_width = float(SCREEN_WIDTH)
                draw_height = draw_width / source_ratio
            arcade.draw_texture_rect(
                ending,
                arcade.XYWH(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2,
                            draw_width, draw_height),
            )
            if self.victory:
                arcade.draw_texture_rect(
                    load_victory_emblem(), arcade.XYWH(590, 570, 650, 217)
                )
                final_name = self.final_enemy_name or "終焉之主"
                outcome = f"{p.name}擊敗{final_name}，王城終於迎回黎明！"
            else:
                arcade.draw_texture_rect(
                    load_death_emblem(), arcade.XYWH(590, 570, 650, 217)
                )
                outcome = f"{p.name}倒在了冒險途中。"
            self.quiet_surface(285, 116, 610, 76, alpha=176)
            self.draw_text_block(
                outcome, 590, 154, 560, 17, INK, line_spacing=24,
                max_lines=2, min_size=13, bold=True,
            )
        else:
            # Adventure is the run hub, so the map owns the page.  Character
            # resources live in one compact coloured strip instead of two
            # permanent side panels competing with the route.
            # The map is submitted by ``draw_background_batch`` and covers the
            # viewport. Footer controls deliberately overlay its lower edge so
            # the route can use the page depth.
            self.quiet_surface(70, 629, 1040, 42, alpha=218)
            self.text(f"{p.name}　{p.race}・{job_text}　{self.level_label(p.lv)}",
                      94, 650, 14, GOLD, "left", "center", True,
                      max_width=430, max_height=22, min_size=12)
            self.text(f"血量 {max(0, p.hp)}/{p.max_hp}", 560, 650, 13, RED,
                      "left", "center", True, max_width=150, max_height=20)
            self.text(f"金幣 {p.gold}G　藥水 {self.total_potions()}　天賦點 {p.talent_points}",
                      1080, 650, 12, INK, "right", "center", True,
                      max_width=350, max_height=20, min_size=11)
            if not self.draw_journey_route_map():
                # Legacy/corrupt saves can briefly reach Adventure before the
                # route migration has populated its graph. Keep that frame
                # readable without reviving the obsolete five-marker route.
                stage_title, stage_text = self.journey_stage()
                self.quiet_surface(75, 104, 1030, 72, alpha=224)
                self.text(stage_title, 590, 158, 18, GOLD,
                          "center", "center", True,
                          max_width=900, max_height=25)
                self.text(f"{stage_text}｜正在展開本章路線……",
                          590, 128, 11, MUTED, "center", "center",
                          max_width=920, max_height=17, min_size=10)
