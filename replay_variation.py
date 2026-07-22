"""Deterministic, side-effect-free selection helpers for replay variation.

The selectors in this module deliberately know nothing about Arcade or the
game's save model.  Callers provide a ``random.Random`` instance and small
predicate functions, which keeps the rules easy to simulate and unit test.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable, Sequence
import random
from typing import Generic, TypeVar


T = TypeVar("T", bound=Hashable)


def _unique(items: Sequence[T]) -> tuple[T, ...]:
    """Return items in catalog order with duplicate identifiers removed."""
    return tuple(dict.fromkeys(items))


class RecentEventPicker(Generic[T]):
    """Pick events while avoiding the most recently returned identifiers.

    The recent exclusion window is strict whenever at least one eligible event
    remains.  With a catalog smaller than the configured window, the picker
    falls back to the least-recently used choices and still avoids an immediate
    repeat whenever the catalog contains more than one event.
    """

    def __init__(self, rng: random.Random, recent_window: int = 3) -> None:
        if recent_window < 0:
            raise ValueError("recent_window must be non-negative")
        self._rng = rng
        self._recent: deque[T] = deque(maxlen=recent_window)

    @property
    def recent(self) -> tuple[T, ...]:
        return tuple(self._recent)

    def reset(self) -> None:
        self._recent.clear()

    def restore_recent(self, events: Sequence[T]) -> None:
        """Restore a save-compatible recent history in chronological order."""
        self._recent.clear()
        if self._recent.maxlen:
            for event in events[-self._recent.maxlen:]:
                self._recent.append(event)

    def pick(self, events: Sequence[T]) -> T:
        catalog = _unique(events)
        if not catalog:
            raise ValueError("events must not be empty")

        recent_set = set(self._recent)
        eligible = [event for event in catalog if event not in recent_set]
        if not eligible:
            # A strict window is impossible when it covers the entire catalog.
            # Prefer older entries, but never immediately repeat when another
            # choice exists.
            latest = self._recent[-1] if self._recent else None
            eligible = [event for event in catalog if event != latest]
            if not eligible:
                eligible = list(catalog)

            if self._recent:
                age = {event: index for index, event in enumerate(self._recent)}
                oldest_age = min(age.get(event, -1) for event in eligible)
                eligible = [
                    event for event in eligible
                    if age.get(event, -1) == oldest_age
                ]

        selected = self._rng.choice(eligible)
        if self._recent.maxlen:
            self._recent.append(selected)
        return selected


class ShopInventorySelector(Generic[T]):
    """Create and cache one guaranteed inventory snapshot per shop visit."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._snapshots: dict[Hashable, tuple[T, ...]] = {}

    def clear_visit(self, visit_key: Hashable) -> None:
        self._snapshots.pop(visit_key, None)

    def select(
        self,
        visit_key: Hashable,
        items: Sequence[T],
        size: int,
        *,
        is_healing: Callable[[T], bool],
        is_affordable: Callable[[T], bool],
    ) -> tuple[T, ...]:
        """Return a stable subset containing healing and affordable offers.

        The cached snapshot wins for a repeated ``visit_key``; predicates are
        intentionally not reevaluated, so redraws cannot reroll a shop visit.
        """
        if visit_key in self._snapshots:
            return self._snapshots[visit_key]

        catalog = _unique(items)
        if not catalog:
            raise ValueError("items must not be empty")
        if size < 1 or size > len(catalog):
            raise ValueError("size must be between 1 and the catalog size")

        healing = [item for item in catalog if is_healing(item)]
        affordable = [item for item in catalog if is_affordable(item)]
        if not healing:
            raise ValueError("shop catalog has no healing item")
        if not affordable:
            raise ValueError("shop catalog has no affordable item")

        selected: list[T] = []
        overlap = [item for item in healing if is_affordable(item)]
        if overlap:
            selected.append(self._rng.choice(overlap))
        else:
            if size < 2:
                raise ValueError(
                    "size is too small for distinct healing and affordable guarantees"
                )
            selected.append(self._rng.choice(healing))
            affordable_remaining = [item for item in affordable if item not in selected]
            if not affordable_remaining:
                raise ValueError("guarantees cannot be satisfied by distinct items")
            selected.append(self._rng.choice(affordable_remaining))

        remaining = [item for item in catalog if item not in selected]
        fill_count = size - len(selected)
        if fill_count:
            selected.extend(self._rng.sample(remaining, fill_count))

        selected_set = set(selected)
        snapshot = tuple(item for item in catalog if item in selected_set)
        self._snapshots[visit_key] = snapshot
        return snapshot


class CampfireOptionSelector(Generic[T]):
    """Select campfire choices with recovery, growth, and resource coverage."""

    REQUIRED_CATEGORIES = ("recovery", "growth", "resource")

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def select(
        self,
        options: Sequence[T],
        size: int,
        *,
        category_of: Callable[[T], str],
    ) -> tuple[T, ...]:
        catalog = _unique(options)
        if size < len(self.REQUIRED_CATEGORIES):
            raise ValueError("size must allow all required campfire categories")
        if size > len(catalog):
            raise ValueError("size must not exceed the option catalog")

        by_category = {
            category: [
                option for option in catalog
                if category_of(option) == category
            ]
            for category in self.REQUIRED_CATEGORIES
        }
        missing = [category for category, values in by_category.items() if not values]
        if missing:
            raise ValueError(
                "campfire catalog is missing categories: " + ", ".join(missing)
            )

        selected = [
            self._rng.choice(by_category[category])
            for category in self.REQUIRED_CATEGORIES
        ]
        remaining = [option for option in catalog if option not in selected]
        fill_count = size - len(selected)
        if fill_count:
            selected.extend(self._rng.sample(remaining, fill_count))

        selected_set = set(selected)
        return tuple(option for option in catalog if option in selected_set)


__all__ = [
    "CampfireOptionSelector",
    "RecentEventPicker",
    "ShopInventorySelector",
]
