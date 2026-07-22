from __future__ import annotations

import random
import unittest

from combat_intents import (
    AggressiveIntentSelector,
    INTENT_SPECS,
    IntentCategory,
    IntentStreak,
    get_intent_spec,
)


class IntentRegistryTests(unittest.TestCase):
    def test_existing_and_first_slice_intents_are_registered(self) -> None:
        expected = {
            "attack", "strong_attack", "dot", "strong_dot", "curse", "stun",
            "defend", "immune", "reflect", "cleanse", "berserk", "bulwark",
            "heavy_blow", "lifedrain",
        }
        self.assertEqual(set(INTENT_SPECS), expected)

    def test_categories_do_not_conflate_hostility_and_immediate_damage(self) -> None:
        self.assertEqual(get_intent_spec("curse").category, IntentCategory.PRESSURE)
        self.assertTrue(get_intent_spec("curse").hostile)
        self.assertFalse(get_intent_spec("curse").immediate_damage)
        self.assertEqual(get_intent_spec("defend").category, IntentCategory.NON_HOSTILE)
        self.assertFalse(get_intent_spec("defend").hostile)

    def test_heavy_blow_charge_is_not_immediate_or_current_round_damage(self) -> None:
        heavy_blow = get_intent_spec("heavy_blow")
        self.assertEqual(heavy_blow.category, IntentCategory.DELAYED_DAMAGE)
        self.assertFalse(heavy_blow.immediate_damage)
        self.assertFalse(heavy_blow.contributes_round_damage)
        self.assertTrue(get_intent_spec("lifedrain").contributes_round_damage)

    def test_unknown_intents_fail_loudly(self) -> None:
        with self.assertRaisesRegex(KeyError, "unregistered enemy intent"):
            get_intent_spec("typo_attack")


class IntentStreakTests(unittest.TestCase):
    def test_counters_track_different_mechanics(self) -> None:
        streak = IntentStreak()
        streak.record("defend")
        self.assertEqual((streak.non_hostile, streak.no_immediate), (1, 1))
        streak.record("curse")
        self.assertEqual((streak.non_hostile, streak.no_immediate), (0, 2))
        streak.record("heavy_blow")
        self.assertEqual((streak.non_hostile, streak.no_immediate), (0, 3))
        streak.record("lifedrain")
        self.assertEqual((streak.non_hostile, streak.no_immediate), (0, 0))


class AggressiveIntentSelectorTests(unittest.TestCase):
    def test_seeded_selection_is_reproducible(self) -> None:
        pools = [("attack", "defend", "curse")] * 2
        first = AggressiveIntentSelector(random.Random(8128))
        second = AggressiveIntentSelector(random.Random(8128))
        first_states = [IntentStreak(), IntentStreak()]
        second_states = [IntentStreak(), IntentStreak()]
        first_results = [first.choose_group(pools, first_states) for _ in range(20)]
        second_results = [second.choose_group(pools, second_states) for _ in range(20)]
        self.assertEqual(first_results, second_results)
        self.assertEqual(first_states, second_states)

    def test_non_hostile_limit_forces_a_hostile_choice(self) -> None:
        selector = AggressiveIntentSelector(random.Random(1), hostile_bias=0.0)
        state = IntentStreak(non_hostile=2)
        choice = selector.choose_one(("defend", "curse"), state)
        self.assertEqual(choice, "curse")

    def test_no_immediate_limit_forces_actual_immediate_damage(self) -> None:
        selector = AggressiveIntentSelector(random.Random(2))
        state = IntentStreak(no_immediate=2)
        choices = {
            selector.choose_one(("heavy_blow", "curse", "lifedrain"), state)
            for _ in range(20)
        }
        self.assertEqual(choices, {"lifedrain"})

    def test_dual_enemy_rule_guarantees_round_damage_when_available(self) -> None:
        for seed in range(50):
            selector = AggressiveIntentSelector(random.Random(seed), hostile_bias=0.0)
            states = [IntentStreak(), IntentStreak()]
            choices = selector.choose_group(
                [("defend", "attack"), ("immune", "lifedrain")], states,
            )
            self.assertTrue(any(
                get_intent_spec(choice).contributes_round_damage for choice in choices
            ))

    def test_dual_enemy_replacement_is_not_fixed_to_one_enemy(self) -> None:
        replaced_indices: set[int] = set()
        for seed in range(100):
            selector = AggressiveIntentSelector(random.Random(seed), hostile_bias=0.0)
            choices = selector.choose_group(
                [("defend", "attack"), ("immune", "lifedrain")],
                [IntentStreak(), IntentStreak()],
            )
            replaced_indices.add(0 if choices[0] == "attack" else 1)
        self.assertEqual(replaced_indices, {0, 1})

    def test_dual_enemy_rule_does_not_treat_heavy_blow_as_damage(self) -> None:
        selector = AggressiveIntentSelector(random.Random(5), hostile_bias=0.0)
        choices = selector.choose_group(
            [("defend", "heavy_blow"), ("immune", "attack")],
            [IntentStreak(), IntentStreak()],
        )
        self.assertEqual(choices[1], "attack")

    def test_no_damaging_option_falls_back_without_crashing(self) -> None:
        selector = AggressiveIntentSelector(random.Random(8), hostile_bias=0.0)
        choices = selector.choose_group(
            [("defend", "curse"), ("immune", "heavy_blow")],
            [IntentStreak(), IntentStreak()],
        )
        self.assertEqual(len(choices), 2)
        self.assertFalse(any(
            get_intent_spec(choice).contributes_round_damage for choice in choices
        ))

    def test_invalid_inputs_are_rejected(self) -> None:
        selector = AggressiveIntentSelector(random.Random(0))
        with self.assertRaisesRegex(ValueError, "same length"):
            selector.choose_group([("attack",)], [])
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            selector.choose_one((), IntentStreak())


if __name__ == "__main__":
    unittest.main()
