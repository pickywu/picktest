"""Semantic icon registry for combat intents and persistent statuses.

The renderer used to choose images ad hoc, which made mechanically different
actions such as a normal strike, a charged heavy blow, and life drain look the
same.  This module is intentionally Arcade-free: gameplay, tests, asset audits,
and the renderer can all agree on one stable visual vocabulary.

Paths are relative to ``assets/ui``.  ``asset_path`` is the desired, explicit
art asset; ``fallback_asset_path`` is only a compatibility bridge while newly
specified art is being produced.  New UI code should call ``best_asset_path``
instead of silently inventing another fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from combat_intents import INTENT_SPECS


@dataclass(frozen=True, slots=True)
class CombatIconSpec:
    """Presentation contract for one mechanic.

    ``semantic_key`` describes what the silhouette must communicate to the
    player.  It is deliberately distinct from the gameplay key so related
    mechanics may share an image only when their meaning is genuinely the same.
    ``tone`` gives the renderer a consistent badge colour family.
    """

    semantic_key: str
    asset_path: str
    meaning: str
    tone: str
    fallback_asset_path: str | None = None

    def best_asset_path(self, ui_asset_root: str | Path) -> str:
        """Return the primary art when installed, otherwise its declared bridge."""

        root = Path(ui_asset_root)
        if (root / self.asset_path).is_file():
            return self.asset_path
        if self.fallback_asset_path and (root / self.fallback_asset_path).is_file():
            return self.fallback_asset_path
        return self.asset_path


@dataclass(frozen=True, slots=True)
class StatusBadge:
    """One active status ready for compact overhead rendering."""

    key: str
    label_zh: str
    label_en: str
    value: str
    icon: CombatIconSpec

    def label(self, locale: str) -> str:
        return self.label_en if str(locale).upper().startswith("EN") else self.label_zh


def _icon(
    semantic_key: str,
    asset_path: str,
    meaning: str,
    tone: str,
    fallback: str | None = None,
) -> CombatIconSpec:
    return CombatIconSpec(semantic_key, asset_path, meaning, tone, fallback)


# Every gameplay intent gets its own silhouette when its outcome differs.  The
# four fallbacks document the legacy mismatches without preserving them as the
# desired visual language.
_INTENT_ICONS = {
    "attack": _icon(
        "weapon_strike", "icons/intents/attack.png",
        "Immediate weapon damage", "danger",
    ),
    "strong_attack": _icon(
        "empowered_strike", "icons/intents/strong_attack.png",
        "A stronger immediate attack", "danger",
        "icons/intents/attack.png",
    ),
    "heavy_blow": _icon(
        "charged_heavy_blow", "icons/intents/heavy_blow.png",
        "Charge now and release a crushing blow later", "warning",
        "icons/intents/attack.png",
    ),
    "lifedrain": _icon(
        "life_drain", "icons/intents/lifedrain.png",
        "Damage the player and heal the attacker", "drain",
        "icons/intents/curse.png",
    ),
    "dot": _icon(
        "damage_over_time", "icons/intents/dot.png",
        "Apply recurring damage", "ailment",
    ),
    "strong_dot": _icon(
        "severe_damage_over_time", "icons/intents/strong_dot.png",
        "Apply stronger recurring damage", "ailment",
        "icons/intents/dot.png",
    ),
    "curse": _icon(
        "curse_debuff", "icons/intents/curse.png",
        "Reduce the player's attack and defense", "ailment",
    ),
    "stun": _icon(
        "stun_control", "icons/intents/stun.png",
        "Make the player lose an action turn", "warning",
    ),
    "defend": _icon(
        "raise_block", "icons/intents/defend.png",
        "Gain a damage-absorbing shield", "guard",
    ),
    "immune": _icon(
        "next_hit_immunity", "icons/intents/immune.png",
        "Negate the next incoming hit", "guard",
    ),
    "reflect": _icon(
        "damage_reflection", "icons/intents/reflect.png",
        "Return part of incoming damage", "counter",
    ),
    "cleanse": _icon(
        "cleanse_and_recover", "icons/intents/cleanse.png",
        "Remove ailments and recover", "recovery",
    ),
    "berserk": _icon(
        "attack_growth", "icons/intents/berserk.png",
        "Permanently increase attack for this battle", "danger",
    ),
    "bulwark": _icon(
        "defense_growth", "icons/intents/bulwark.png",
        "Permanently increase defense for this battle", "guard",
    ),
}
INTENT_ICONS: Mapping[str, CombatIconSpec] = MappingProxyType(_INTENT_ICONS)


# These are the player-facing states that can materially change the next action
# or incoming hit.  Temporary potion buffs are included even though the current
# renderer omits them; otherwise the player receives no visible confirmation.
_PLAYER_STATUS_ICONS = {
    "block": _icon(
        "player_block", "icons/intents/defend.png",
        "Damage-absorbing shield currently held", "guard",
    ),
    "dark_mist": _icon(
        "player_damage_over_time", "icons/intents/dot.png",
        "Recurring black-mist damage", "ailment",
    ),
    "curse": _icon(
        "player_curse", "icons/intents/curse.png",
        "Attack and defense are reduced", "ailment",
    ),
    "stunned": _icon(
        "player_stunned", "icons/intents/stun.png",
        "The next player turn is skipped", "warning",
    ),
    "attack_immunity": _icon(
        "player_attack_immunity", "icons/talents/paladin/sanctuary.png",
        "The next incoming attack is negated", "guard",
    ),
    "stun_immunity": _icon(
        "player_stun_immunity", "icons/potions/stun_ward.png",
        "The next stun is negated", "guard",
    ),
    "ice_barrier": _icon(
        "player_ice_barrier", "icons/talents/mage/ice_barrier.png",
        "The next incoming attack is absorbed by ice", "guard",
    ),
    "blood_sacrifice": _icon(
        "player_blood_sacrifice", "icons/status/player/blood_sacrifice.png",
        "Bonus damage is queued from sacrificed health", "power",
        "icons/talents/warrior/last_stand.png",
    ),
    "blood_regeneration": _icon(
        "player_blood_regeneration", "icons/potions/heal.png",
        "Health will regenerate over subsequent turns", "recovery",
    ),
    "stealth": _icon(
        "player_stealth", "icons/talents/rogue/vanish.png",
        "The next incoming attack is avoided", "evasion",
    ),
    "guaranteed_critical": _icon(
        "player_guaranteed_critical", "icons/talents/rogue/assassinate.png",
        "The next attack is guaranteed to critically hit", "power",
    ),
    "attack_boost": _icon(
        "player_attack_boost", "icons/potions/attack.png",
        "The next attack gains the potion damage multiplier", "power",
    ),
    "defense_boost": _icon(
        "player_defense_boost", "icons/potions/defense.png",
        "The next defend action gains the potion block multiplier", "guard",
    ),
    "iron_skin": _icon(
        "player_iron_skin", "icons/potions/iron_skin.png",
        "Incoming damage is reduced for the active turn", "guard",
    ),
}
PLAYER_STATUS_ICONS: Mapping[str, CombatIconSpec] = MappingProxyType(
    _PLAYER_STATUS_ICONS
)

PLAYER_STATUS_LABELS: Mapping[str, tuple[str, str]] = MappingProxyType({
    "block": ("護盾", "SHIELD"),
    "dark_mist": ("黑霧", "BLACK MIST"),
    "curse": ("詛咒", "CURSE"),
    "stunned": ("昏迷", "STUNNED"),
    "attack_immunity": ("庇護", "AEGIS"),
    "stun_immunity": ("醒神", "STUN WARD"),
    "ice_barrier": ("冰障", "ICE BARRIER"),
    "blood_sacrifice": ("血祭", "BLOOD RITE"),
    "blood_regeneration": ("回流", "BLOOD REGEN"),
    "stealth": ("隱身", "STEALTH"),
    "guaranteed_critical": ("必定暴擊", "GUARANTEED CRIT"),
    "attack_boost": ("攻擊強化", "ATTACK UP"),
    "defense_boost": ("防禦強化", "DEFENSE UP"),
    "iron_skin": ("鐵膚", "IRONSKIN"),
})


# Enemy statuses are registered as well so status badges beside multi-enemy
# portraits cannot drift back to text-only abbreviations.
_ENEMY_STATUS_ICONS = {
    "block": _icon(
        "enemy_block", "icons/intents/defend.png",
        "Damage-absorbing shield currently held", "guard",
    ),
    "corrosion": _icon(
        "enemy_corrosion", "icons/talents/warlock/corruption_mastery.png",
        "Recurring corrosion damage", "ailment",
    ),
    "agony": _icon(
        "enemy_agony", "icons/talents/warlock/agony.png",
        "Stacking agony damage", "ailment",
    ),
    "doom": _icon(
        "enemy_doom", "icons/talents/warlock/doom.png",
        "Delayed burst damage countdown", "ailment",
    ),
    "weak": _icon(
        "enemy_attack_weakened", "icons/talents/warlock/hex.png",
        "Attack output is reduced", "ailment",
    ),
    "immune": _icon(
        "enemy_attack_immunity", "icons/intents/immune.png",
        "The next incoming hit is negated", "guard",
    ),
    "reflect": _icon(
        "enemy_damage_reflection", "icons/intents/reflect.png",
        "Incoming damage is partly reflected", "counter",
    ),
    "stealth": _icon(
        "enemy_stealth", "icons/talents/rogue/vanish.png",
        "The next incoming hit is avoided", "evasion",
    ),
    "stunned": _icon(
        "enemy_stunned", "icons/intents/stun.png",
        "The enemy loses its action turn", "warning",
    ),
    "heavy_blow_charged": _icon(
        "enemy_heavy_blow_charged", "icons/intents/heavy_blow.png",
        "A charged heavy blow will release next", "warning",
        "icons/intents/attack.png",
    ),
    "berserk": _icon(
        "enemy_attack_growth", "icons/intents/berserk.png",
        "Attack has increased in this battle", "danger",
    ),
    "bulwark": _icon(
        "enemy_defense_growth", "icons/intents/bulwark.png",
        "Defense has increased in this battle", "guard",
    ),
}
ENEMY_STATUS_ICONS: Mapping[str, CombatIconSpec] = MappingProxyType(
    _ENEMY_STATUS_ICONS
)

ENEMY_STATUS_LABELS: Mapping[str, tuple[str, str]] = MappingProxyType({
    "block": ("護盾", "SHIELD"),
    "corrosion": ("腐蝕", "CORROSION"),
    "agony": ("痛苦", "AGONY"),
    "doom": ("末日", "DOOM"),
    "weak": ("衰弱", "WEAKENED"),
    "immune": ("免疫", "IMMUNE"),
    "reflect": ("反彈", "REFLECT"),
    "stealth": ("隱身", "STEALTH"),
    "stunned": ("昏迷", "STUNNED"),
    "heavy_blow_charged": ("蓄力", "CHARGED"),
    "berserk": ("狂暴", "BERSERK"),
    "bulwark": ("壁壘", "BULWARK"),
})


def _status_badge(
    key: str,
    value: object,
    icons: Mapping[str, CombatIconSpec],
    labels: Mapping[str, tuple[str, str]],
) -> StatusBadge:
    zh, en = labels[key]
    return StatusBadge(key, zh, en, str(value), icons[key])


def collect_player_status_badges(state: object) -> tuple[StatusBadge, ...]:
    """Collect every active player overhead mechanic in display priority order.

    The function uses a structural ``state`` object instead of importing the RPG
    window, so it remains cheap to test and cannot create an Arcade dependency.
    Values are intentionally compact; the hover/tooltip layer can use the icon
    registry's longer ``meaning`` text.
    """

    badges: list[StatusBadge] = []
    add = lambda key, value: badges.append(  # noqa: E731 - local collector
        _status_badge(key, value, PLAYER_STATUS_ICONS, PLAYER_STATUS_LABELS)
    )

    stunned = int(getattr(state, "player_stun_turns", 0) or 0)
    dot_damage = int(getattr(state, "player_dot_damage", 0) or 0)
    dot_turns = int(getattr(state, "player_dot_turns", 0) or 0)
    dot_stacks = max(1, int(getattr(state, "player_dot_stacks", 0) or 0))
    curse_turns = int(getattr(state, "player_curse_turns", 0) or 0)
    block = int(getattr(state, "player_block", 0) or 0)

    if stunned > 0:
        add("stunned", stunned)
    if dot_damage > 0 and dot_turns > 0:
        value = f"{dot_damage * dot_stacks}×{dot_turns}"
        if dot_stacks > 1:
            value += f" ·{dot_stacks}"
        add("dark_mist", value)
    if curse_turns > 0:
        add("curse", curse_turns)
    if block > 0:
        add("block", block)

    counted_fields = (
        ("attack_immunity", "player_attack_immunity_turns"),
        ("ice_barrier", "mage_ice_barrier_turns"),
        ("stun_immunity", "player_stun_immunity_turns"),
        ("iron_skin", "potion_iron_skin_turns"),
        ("stealth", "stealth_turns"),
    )
    for key, field in counted_fields:
        turns = int(getattr(state, field, 0) or 0)
        if turns > 0:
            add(key, turns)

    if bool(getattr(state, "potion_attack_boost", False)):
        add("attack_boost", "+50%")
    if bool(getattr(state, "potion_defense_boost", False)):
        add("defense_boost", "+50%")

    attack_bonus = int(getattr(state, "warrior_attack_bonus", 0) or 0)
    if attack_bonus > 0:
        add("blood_sacrifice", f"+{attack_bonus}")
    regen_turns = int(getattr(state, "warrior_blood_regen_turns", 0) or 0)
    regen = int(getattr(state, "warrior_blood_regen", 0) or 0)
    if regen > 0 and regen_turns > 0:
        add("blood_regeneration", f"{regen}×{regen_turns}")

    critical_chance = None
    displayed_critical = getattr(state, "displayed_critical_chance", None)
    if callable(displayed_critical):
        critical_chance = float(displayed_critical())
    elif bool(getattr(state, "forced_critical", False)):
        critical_chance = 100.0
    if critical_chance is not None and critical_chance >= 100.0:
        add("guaranteed_critical", "100%")

    return tuple(badges)


def collect_enemy_status_badges(enemy: object) -> tuple[StatusBadge, ...]:
    """Collect the status mechanics currently represented near an enemy portrait."""

    badges: list[StatusBadge] = []
    add = lambda key, value: badges.append(  # noqa: E731 - local collector
        _status_badge(key, value, ENEMY_STATUS_ICONS, ENEMY_STATUS_LABELS)
    )

    block = int(getattr(enemy, "block", 0) or 0)
    if block > 0:
        add("block", block)
    corrosion_turns = int(getattr(enemy, "corrosion_turns", 0) or 0)
    corrosion_damage = int(getattr(enemy, "corrosion_damage", 0) or 0)
    if corrosion_damage > 0 and corrosion_turns > 0:
        add("corrosion", f"{corrosion_damage}×{corrosion_turns}")
    agony_turns = int(getattr(enemy, "agony_turns", 0) or 0)
    agony_damage = int(getattr(enemy, "agony_damage", 0) or 0)
    agony_stacks = max(1, int(getattr(enemy, "agony_stacks", 0) or 0))
    if agony_damage > 0 and agony_turns > 0:
        add("agony", f"{agony_damage * agony_stacks}×{agony_turns} ·{agony_stacks}")
    doom_turns = int(getattr(enemy, "doom_turns", 0) or 0)
    doom_damage = int(getattr(enemy, "doom_damage", 0) or 0)
    if doom_damage > 0 and doom_turns > 0:
        add("doom", f"{doom_damage}@{doom_turns}")
    weak_turns = int(getattr(enemy, "weak_turns", 0) or 0)
    if weak_turns > 0:
        add("weak", weak_turns)

    for key, field in (
        ("immune", "immune_turns"),
        ("reflect", "reflect_turns"),
        ("stealth", "stealth_turns"),
        ("stunned", "skip_turns"),
    ):
        turns = int(getattr(enemy, field, 0) or 0)
        if turns > 0:
            add(key, turns)
    if bool(getattr(enemy, "heavy_blow_charged", False)):
        add("heavy_blow_charged", "!")
    berserk = int(getattr(enemy, "berserk_stacks", 0) or 0)
    if berserk > 0:
        add("berserk", berserk)
    bulwark = int(getattr(enemy, "bulwark_stacks", 0) or 0)
    if bulwark > 0:
        add("bulwark", bulwark)
    return tuple(badges)


def intent_icon(intent: str) -> CombatIconSpec:
    """Return a registered intent icon and reject silent unknown artwork."""

    try:
        return INTENT_ICONS[intent]
    except KeyError as exc:
        raise KeyError(f"unregistered enemy intent icon: {intent!r}") from exc


def player_status_icon(status: str) -> CombatIconSpec:
    try:
        return PLAYER_STATUS_ICONS[status]
    except KeyError as exc:
        raise KeyError(f"unregistered player status icon: {status!r}") from exc


def enemy_status_icon(status: str) -> CombatIconSpec:
    try:
        return ENEMY_STATUS_ICONS[status]
    except KeyError as exc:
        raise KeyError(f"unregistered enemy status icon: {status!r}") from exc


def missing_primary_assets(
    ui_asset_root: str | Path,
    *registries: Mapping[str, CombatIconSpec],
) -> tuple[str, ...]:
    """Return a stable, deduplicated asset-production work list."""

    selected = registries or (
        INTENT_ICONS,
        PLAYER_STATUS_ICONS,
        ENEMY_STATUS_ICONS,
    )
    root = Path(ui_asset_root)
    return tuple(sorted({
        spec.asset_path
        for registry in selected
        for spec in registry.values()
        if not (root / spec.asset_path).is_file()
    }))


# Fail during import when a gameplay intent is added without a visual contract.
if set(INTENT_ICONS) != set(INTENT_SPECS):
    missing = sorted(set(INTENT_SPECS) - set(INTENT_ICONS))
    stale = sorted(set(INTENT_ICONS) - set(INTENT_SPECS))
    raise RuntimeError(
        f"combat intent icon registry mismatch: missing={missing}, stale={stale}"
    )


__all__ = [
    "CombatIconSpec",
    "ENEMY_STATUS_ICONS",
    "ENEMY_STATUS_LABELS",
    "INTENT_ICONS",
    "PLAYER_STATUS_ICONS",
    "PLAYER_STATUS_LABELS",
    "StatusBadge",
    "collect_enemy_status_badges",
    "collect_player_status_badges",
    "enemy_status_icon",
    "intent_icon",
    "missing_primary_assets",
    "player_status_icon",
]
