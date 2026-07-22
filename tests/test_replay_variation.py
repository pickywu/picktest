from __future__ import annotations

import random
import unittest

from replay_variation import (
    CampfireOptionSelector,
    RecentEventPicker,
    ShopInventorySelector,
)


class RecentEventPickerTests(unittest.TestCase):
    def test_avoids_recent_events_while_choices_remain(self) -> None:
        picker = RecentEventPicker(random.Random(13), recent_window=3)
        catalog = ("a", "b", "c", "d", "e")
        history: list[str] = []
        for _ in range(40):
            selected = picker.pick(catalog)
            self.assertNotIn(selected, history[-3:])
            history.append(selected)

    def test_small_catalog_fallback_avoids_immediate_repeat(self) -> None:
        picker = RecentEventPicker(random.Random(4), recent_window=5)
        history = [picker.pick(("a", "b")) for _ in range(20)]
        self.assertTrue(all(left != right for left, right in zip(history, history[1:])))

    def test_injected_rng_is_reproducible(self) -> None:
        first = RecentEventPicker(random.Random(99), recent_window=2)
        second = RecentEventPicker(random.Random(99), recent_window=2)
        catalog = tuple(range(8))
        self.assertEqual(
            [first.pick(catalog) for _ in range(30)],
            [second.pick(catalog) for _ in range(30)],
        )

    def test_saved_recent_history_can_be_restored(self) -> None:
        picker = RecentEventPicker(random.Random(7), recent_window=3)
        picker.restore_recent((1, 2, 3, 4))
        self.assertEqual(picker.recent, (2, 3, 4))
        self.assertNotIn(picker.pick((1, 2, 3, 4, 5)), (2, 3, 4))


class ShopInventorySelectorTests(unittest.TestCase):
    ITEMS = ("full_heal", "cheap_attack", "expensive_guard", "utility", "elixir")

    @staticmethod
    def is_healing(item: str) -> bool:
        return item in {"full_heal", "elixir"}

    @staticmethod
    def is_affordable(item: str) -> bool:
        return item in {"cheap_attack", "utility"}

    def test_snapshot_satisfies_both_guarantees(self) -> None:
        for seed in range(30):
            selector = ShopInventorySelector(random.Random(seed))
            snapshot = selector.select(
                "level-4-shop", self.ITEMS, 3,
                is_healing=self.is_healing,
                is_affordable=self.is_affordable,
            )
            self.assertEqual(len(snapshot), 3)
            self.assertTrue(any(self.is_healing(item) for item in snapshot))
            self.assertTrue(any(self.is_affordable(item) for item in snapshot))

    def test_same_visit_key_never_rerolls(self) -> None:
        selector = ShopInventorySelector(random.Random(8))
        original = selector.select(
            "visit-1", self.ITEMS, 3,
            is_healing=self.is_healing,
            is_affordable=self.is_affordable,
        )
        repeated = selector.select(
            "visit-1", tuple(reversed(self.ITEMS)), 1,
            is_healing=lambda _item: False,
            is_affordable=lambda _item: False,
        )
        self.assertIs(original, repeated)

    def test_impossible_single_slot_guarantees_raise(self) -> None:
        selector = ShopInventorySelector(random.Random(1))
        with self.assertRaises(ValueError):
            selector.select(
                "visit", ("heal", "cheap"), 1,
                is_healing=lambda item: item == "heal",
                is_affordable=lambda item: item == "cheap",
            )


class CampfireOptionSelectorTests(unittest.TestCase):
    OPTIONS = (
        "rest", "full_rest", "attack", "defense", "gold", "potion",
    )
    CATEGORIES = {
        "rest": "recovery",
        "full_rest": "recovery",
        "attack": "growth",
        "defense": "growth",
        "gold": "resource",
        "potion": "resource",
    }

    def test_every_snapshot_contains_all_required_categories(self) -> None:
        for seed in range(30):
            selector = CampfireOptionSelector(random.Random(seed))
            selected = selector.select(
                self.OPTIONS, 4, category_of=self.CATEGORIES.__getitem__
            )
            categories = {self.CATEGORIES[item] for item in selected}
            self.assertEqual(
                categories, {"recovery", "growth", "resource"}
            )
            self.assertEqual(len(selected), 4)

    def test_missing_required_category_raises(self) -> None:
        selector = CampfireOptionSelector(random.Random(1))
        with self.assertRaisesRegex(ValueError, "resource"):
            selector.select(
                ("rest", "attack", "defense"), 3,
                category_of=self.CATEGORIES.__getitem__,
            )


if __name__ == "__main__":
    unittest.main()
