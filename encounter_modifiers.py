"""Pure encounter-modifier rules.

This module intentionally has no Arcade or ``rpg`` dependency.  Selection and
all derived values can therefore be exercised by balance simulations without
opening a game window.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import random
from typing import Iterable


class BattleModifier(str, Enum):
    """The battle modifiers currently safe to expose to encounter selection."""

    RAMPART = "rampart"
    GREED = "greed"


@dataclass(frozen=True, slots=True)
class EncounterModifierSpec:
    """Immutable balance data for one battle modifier."""

    modifier: BattleModifier
    weight: float
    reward_multiplier: float = 1.0
    enemy_hp_multiplier: float = 1.0
    enemy_attack_multiplier: float = 1.0
    enemy_defense_multiplier: float = 1.0
    opening_shield_defense_multiplier: float = 0.0

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("modifier weight must be greater than zero")
        for name in (
            "reward_multiplier",
            "enemy_hp_multiplier",
            "enemy_attack_multiplier",
            "enemy_defense_multiplier",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if self.opening_shield_defense_multiplier < 0:
            raise ValueError(
                "opening_shield_defense_multiplier cannot be negative"
            )


# A normal non-boss battle has a 35% chance to receive exactly one modifier.
# Within that 35%, Rampart is 60% and Greed is 40% (weights 3:2).
DEFAULT_MODIFIER_CHANCE = 0.35
ENCOUNTER_MODIFIER_SPECS: tuple[EncounterModifierSpec, ...] = (
    EncounterModifierSpec(
        modifier=BattleModifier.RAMPART,
        weight=3.0,
        # Reuse the existing defend scale: opening shield equals enemy defense.
        opening_shield_defense_multiplier=1.0,
    ),
    EncounterModifierSpec(
        modifier=BattleModifier.GREED,
        weight=2.0,
        # Greed increases pressure without adding HP/defense and prolonging fights.
        enemy_attack_multiplier=1.15,
        reward_multiplier=2.0,
    ),
)
_SPEC_BY_MODIFIER = {
    spec.modifier: spec for spec in ENCOUNTER_MODIFIER_SPECS
}


def modifier_spec(
    modifier: BattleModifier | None,
) -> EncounterModifierSpec | None:
    """Return the canonical spec for ``modifier``; ``None`` means no modifier."""

    if modifier is None:
        return None
    return _SPEC_BY_MODIFIER[BattleModifier(modifier)]


def choose_battle_modifier(
    *,
    rng: random.Random,
    is_first_battle: bool,
    is_boss: bool,
    modifier_chance: float = DEFAULT_MODIFIER_CHANCE,
    specs: Iterable[EncounterModifierSpec] = ENCOUNTER_MODIFIER_SPECS,
) -> BattleModifier | None:
    """Select at most one modifier for an eligible encounter.

    The caller owns ``rng`` so a run can use a stable seed independently from
    cosmetic randomness.  First battles and bosses are excluded before the RNG
    is touched, keeping their later rolls reproducible.
    """

    if not 0.0 <= modifier_chance <= 1.0:
        raise ValueError("modifier_chance must be between 0 and 1")
    if is_first_battle or is_boss:
        return None
    if rng.random() >= modifier_chance:
        return None

    candidates = tuple(specs)
    if not candidates:
        return None
    total_weight = sum(spec.weight for spec in candidates)
    if total_weight <= 0:
        raise ValueError("modifier specs must have positive total weight")

    roll = rng.random() * total_weight
    cumulative = 0.0
    for spec in candidates:
        cumulative += spec.weight
        if roll < cumulative:
            return spec.modifier
    # Floating-point rounding can only put the roll on the upper boundary.
    return candidates[-1].modifier


def reward_multiplier_for(modifier: BattleModifier | None) -> float:
    """Return the encounter reward multiplier (normal encounters use 1.0)."""

    spec = modifier_spec(modifier)
    return spec.reward_multiplier if spec else 1.0


def opening_shield_for(
    modifier: BattleModifier | None,
    *,
    enemy_defense: int,
) -> int:
    """Calculate the one-time shield granted when an encounter opens."""

    spec = modifier_spec(modifier)
    if spec is None or spec.opening_shield_defense_multiplier <= 0:
        return 0
    defense = max(0, int(enemy_defense))
    return max(
        1,
        math.ceil(defense * spec.opening_shield_defense_multiplier),
    )


def modified_enemy_stats(
    modifier: BattleModifier | None,
    *,
    max_hp: int,
    attack: int,
    defense: int,
) -> tuple[int, int, int]:
    """Apply a modifier's explicit encounter-stat multipliers."""

    spec = modifier_spec(modifier)
    if spec is None:
        return max_hp, attack, defense
    return (
        max(1, math.ceil(max_hp * spec.enemy_hp_multiplier)),
        max(1, math.ceil(attack * spec.enemy_attack_multiplier)),
        max(0, math.ceil(defense * spec.enemy_defense_multiplier)),
    )


__all__ = [
    "BattleModifier",
    "EncounterModifierSpec",
    "DEFAULT_MODIFIER_CHANCE",
    "ENCOUNTER_MODIFIER_SPECS",
    "choose_battle_modifier",
    "modified_enemy_stats",
    "modifier_spec",
    "opening_shield_for",
    "reward_multiplier_for",
]
