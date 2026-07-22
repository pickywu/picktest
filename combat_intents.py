"""Pure combat-intent classification and selection rules.

This module deliberately has no Arcade or game-window dependency.  The game can
therefore simulate and balance enemy behaviour with a seeded ``random.Random``
without opening a window.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random
from types import MappingProxyType
from typing import Mapping, Sequence


class IntentCategory(str, Enum):
    """Mechanical category used by protection and aggression rules."""

    NON_HOSTILE = "non_hostile"
    PRESSURE = "pressure"
    DELAYED_DAMAGE = "delayed_damage"
    IMMEDIATE_DAMAGE = "immediate_damage"


@dataclass(frozen=True, slots=True)
class IntentSpec:
    """Stable metadata for one enemy intent.

    ``damages_this_round`` is separate from ``category`` for future actions
    whose damage is resolved later in the same enemy round.  Immediate damage
    always satisfies the round-damage guarantee.  A charge-only action such as
    ``heavy_blow`` must leave this flag false.
    """

    key: str
    category: IntentCategory
    damages_this_round: bool = False

    @property
    def hostile(self) -> bool:
        return self.category is not IntentCategory.NON_HOSTILE

    @property
    def immediate_damage(self) -> bool:
        return self.category is IntentCategory.IMMEDIATE_DAMAGE

    @property
    def contributes_round_damage(self) -> bool:
        return self.immediate_damage or self.damages_this_round


def _spec(key: str, category: IntentCategory, *, this_round: bool = False) -> IntentSpec:
    return IntentSpec(key, category, damages_this_round=this_round)


# Keep this registry data-only.  Presentation labels, values and execution
# callbacks belong to the game layer and can evolve independently.
_INTENT_SPECS = {
    # Existing direct attacks.
    "attack": _spec("attack", IntentCategory.IMMEDIATE_DAMAGE),
    "strong_attack": _spec("strong_attack", IntentCategory.IMMEDIATE_DAMAGE),
    # Existing damage-over-time setup.  Applying these statuses is not an
    # immediate hit, even though an already-active status may tick separately.
    "dot": _spec("dot", IntentCategory.DELAYED_DAMAGE),
    "strong_dot": _spec("strong_dot", IntentCategory.DELAYED_DAMAGE),
    # Existing hostile control actions.
    "curse": _spec("curse", IntentCategory.PRESSURE),
    "stun": _spec("stun", IntentCategory.PRESSURE),
    # Existing setup/defensive actions.
    "defend": _spec("defend", IntentCategory.NON_HOSTILE),
    "immune": _spec("immune", IntentCategory.NON_HOSTILE),
    "reflect": _spec("reflect", IntentCategory.NON_HOSTILE),
    "cleanse": _spec("cleanse", IntentCategory.NON_HOSTILE),
    "berserk": _spec("berserk", IntentCategory.NON_HOSTILE),
    "bulwark": _spec("bulwark", IntentCategory.NON_HOSTILE),
    # First intent expansion slice.
    "heavy_blow": _spec("heavy_blow", IntentCategory.DELAYED_DAMAGE),
    "lifedrain": _spec("lifedrain", IntentCategory.IMMEDIATE_DAMAGE),
}

INTENT_SPECS: Mapping[str, IntentSpec] = MappingProxyType(_INTENT_SPECS)


def get_intent_spec(intent: str) -> IntentSpec:
    """Return registered metadata, rejecting silent classification mistakes."""

    try:
        return INTENT_SPECS[intent]
    except KeyError as exc:
        raise KeyError(f"unregistered enemy intent: {intent!r}") from exc


@dataclass(slots=True)
class IntentStreak:
    """Per-enemy consecutive-choice counters; never shared between enemies."""

    non_hostile: int = 0
    no_immediate: int = 0

    def record(self, intent: str | IntentSpec) -> None:
        spec = get_intent_spec(intent) if isinstance(intent, str) else intent
        self.non_hostile = self.non_hostile + 1 if not spec.hostile else 0
        self.no_immediate = self.no_immediate + 1 if not spec.immediate_damage else 0


class AggressiveIntentSelector:
    """Seedable intent picker with per-enemy and group aggression safeguards.

    Limits describe how many consecutive turns are allowed *before* the next
    choice is forced.  For example, with ``max_non_hostile_streak=2``, an enemy
    that has already chosen two non-hostile actions must choose a hostile action
    when its pool offers one.
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        *,
        hostile_bias: float = 0.60,
        max_non_hostile_streak: int = 2,
        max_no_immediate_streak: int = 2,
        ensure_group_round_damage: bool = True,
    ) -> None:
        if not 0.0 <= hostile_bias <= 1.0:
            raise ValueError("hostile_bias must be between 0 and 1")
        if max_non_hostile_streak < 0 or max_no_immediate_streak < 0:
            raise ValueError("streak limits cannot be negative")
        self.rng = rng if rng is not None else random.Random()
        self.hostile_bias = hostile_bias
        self.max_non_hostile_streak = max_non_hostile_streak
        self.max_no_immediate_streak = max_no_immediate_streak
        self.ensure_group_round_damage = ensure_group_round_damage

    def choose_one(self, pool: Sequence[str], streak: IntentStreak) -> str:
        """Choose one registered intent without mutating ``streak``."""

        candidates = self._validated_pool(pool)

        if streak.no_immediate >= self.max_no_immediate_streak:
            immediate = [spec for spec in candidates if spec.immediate_damage]
            if immediate:
                return self.rng.choice(immediate).key

        if streak.non_hostile >= self.max_non_hostile_streak:
            hostile = [spec for spec in candidates if spec.hostile]
            if hostile:
                candidates = hostile

        hostile = [spec for spec in candidates if spec.hostile]
        non_hostile = [spec for spec in candidates if not spec.hostile]
        if hostile and non_hostile:
            candidates = hostile if self.rng.random() < self.hostile_bias else non_hostile
        return self.rng.choice(candidates).key

    def choose_group(
        self,
        pools: Sequence[Sequence[str]],
        streaks: Sequence[IntentStreak],
    ) -> tuple[str, ...]:
        """Choose intents and then atomically update each enemy's counters.

        With two or more living enemies, at least one choice contributes damage
        in the current round whenever any pool provides such an action.  The
        replacement enemy is selected by RNG, not attack power or list order.
        """

        if len(pools) != len(streaks):
            raise ValueError("pools and streaks must have the same length")
        if not pools:
            return ()

        choices = [self.choose_one(pool, streak) for pool, streak in zip(pools, streaks)]
        if self.ensure_group_round_damage and len(choices) >= 2:
            specs = [get_intent_spec(choice) for choice in choices]
            if not any(spec.contributes_round_damage for spec in specs):
                replacements: list[tuple[int, list[IntentSpec]]] = []
                for index, pool in enumerate(pools):
                    damaging = [
                        get_intent_spec(intent)
                        for intent in pool
                        if get_intent_spec(intent).contributes_round_damage
                    ]
                    if damaging:
                        replacements.append((index, damaging))
                if replacements:
                    index, damaging = self.rng.choice(replacements)
                    choices[index] = self.rng.choice(damaging).key

        for streak, choice in zip(streaks, choices):
            streak.record(choice)
        return tuple(choices)

    @staticmethod
    def _validated_pool(pool: Sequence[str]) -> list[IntentSpec]:
        if not pool:
            raise ValueError("enemy intent pool cannot be empty")
        return [get_intent_spec(intent) for intent in pool]


__all__ = [
    "AggressiveIntentSelector",
    "INTENT_SPECS",
    "IntentCategory",
    "IntentSpec",
    "IntentStreak",
    "get_intent_spec",
]
