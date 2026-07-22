"""Canonical UI asset names and path resolution."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "assets" / "ui"


# Public semantic keys always resolve to the final, version-free UI tree.
# Callers may also pass a canonical relative path directly.
UI_ASSETS = {
    "frame.panel": "frames/container.png",
    "frame.card": "frames/content_card.png",
    "frame.status": "frames/status_ribbon.png",
    "frame.perimeter": "frames/perimeter.png",
    "frame.skill_slot": "slots/skill.png",  # Backward-compatible key.
    "slot.skill": "slots/skill.png",
    "frame.battle_dock": "frames/battle_dock.png",
    "divider.section": "dividers/horizontal.png",
    "surface.material": "surfaces/control.png",
    "meter.frame": "meters/frame.png",
    "meter.hp": "meters/hp_fill.png",
    "meter.shield": "meters/shield_fill.png",
    "scrollbar.track": "scrollbars/track.png",
    "scrollbar.thumb": "scrollbars/thumb.png",
    "icon.action.guard": "icons/actions/guard.png",
    "icon.action.slash": "icons/actions/slash.png",
    "icon.potion_bag": "icons/potions/bag.png",
    "icon.reward": "icons/rewards/ember.png",
}


# Exact old logical paths accepted by the original drawing helpers.
_LEGACY_PATH_ALIASES = {
    "full/frames/content_card.png": "frames/content_card.png",
    "full/frames/status_ribbon.png": "frames/status_ribbon.png",
    "full/markers/skill_slot.png": "slots/skill.png",
    "overlays/surface.png": "surfaces/control.png",
    "frames/meter_frame.png": "meters/frame.png",
    "frames/meter_fill_hp.png": "meters/hp_fill.png",
    "frames/meter_fill_shield.png": "meters/shield_fill.png",
    "frames/scrollbar_track.png": "scrollbars/track.png",
    "frames/scrollbar_thumb.png": "scrollbars/thumb.png",
}

_LEGACY_PREFIX_ALIASES = (
    ("talents/", "icons/talents/"),
    ("potions/", "icons/potions/"),
    ("markers/", "icons/markers/"),
    ("map/", "icons/map/"),
    ("intent/", "icons/intents/"),
)


def canonical_ui_asset(name_or_path: str) -> str:
    """Return a stable path inside the canonical ``assets/ui`` tree.

    Existing semantic keys and old logical relative paths remain accepted so
    drawing call sites can migrate independently from the on-disk layout.
    """
    path = UI_ASSETS.get(name_or_path, name_or_path).replace("\\", "/")
    path = _LEGACY_PATH_ALIASES.get(path, path)
    for legacy_prefix, canonical_prefix in _LEGACY_PREFIX_ALIASES:
        if path.startswith(legacy_prefix):
            return canonical_prefix + path.removeprefix(legacy_prefix)
    return path


_SURFACE_BACKED_PATHS = frozenset({
    UI_ASSETS["frame.panel"],
    UI_ASSETS["frame.card"],
    UI_ASSETS["frame.status"],
})
_INTEGRATED_SURFACE_PATHS = frozenset({
    UI_ASSETS["frame.card"],
    UI_ASSETS["frame.status"],
})


def ui_asset_has_surface(name_or_path: str) -> bool:
    """Whether the asset is a frame designed to sit on an opaque surface."""
    return canonical_ui_asset(name_or_path) in _SURFACE_BACKED_PATHS


def ui_asset_has_integrated_surface(name_or_path: str) -> bool:
    """Whether the generated frame already includes its own centre material."""
    return canonical_ui_asset(name_or_path) in _INTEGRATED_SURFACE_PATHS


def resolve_ui_asset(relative_path: str) -> Path:
    """Resolve a semantic, canonical, or old logical name to its file."""
    canonical_path = canonical_ui_asset(relative_path)
    candidate = UI_ROOT / canonical_path
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"缺少 UI 資產：{canonical_path}")


__all__ = [
    "UI_ASSETS", "canonical_ui_asset", "resolve_ui_asset",
    "ui_asset_has_integrated_surface", "ui_asset_has_surface",
]
