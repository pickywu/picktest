from __future__ import annotations

import random
import unittest

from encounter_modifiers import (
    BattleModifier,
    DEFAULT_MODIFIER_CHANCE,
    ENCOUNTER_MODIFIER_SPECS,
    choose_battle_modifier,
    modified_enemy_stats,
    modifier_spec,
    opening_shield_for,
    reward_multiplier_for,
)


class _FailIfUsedRandom(random.Random):
    def random(self) -> float:
        raise AssertionError("excluded encounters must not consume RNG")


class EncounterModifierTests(unittest.TestCase):
    def test_specs_have_explicit_three_to_two_weights(self) -> None:
        weights = {
            spec.modifier: spec.weight for spec in ENCOUNTER_MODIFIER_SPECS
        }
        self.assertEqual(
            weights,
            {BattleModifier.RAMPART: 3.0, BattleModifier.GREED: 2.0},
        )
        self.assertEqual(DEFAULT_MODIFIER_CHANCE, 0.35)

    def test_seeded_selection_is_deterministic(self) -> None:
        def sample(seed: int) -> list[BattleModifier | None]:
            rng = random.Random(seed)
            return [
                choose_battle_modifier(
                    rng=rng,
                    is_first_battle=False,
                    is_boss=False,
                )
                for _ in range(20)
            ]

        self.assertEqual(sample(8128), sample(8128))
        self.assertNotEqual(sample(8128), sample(8129))

    def test_first_battle_and_boss_are_excluded_without_consuming_rng(self) -> None:
        for is_first_battle, is_boss in ((True, False), (False, True), (True, True)):
            with self.subTest(first=is_first_battle, boss=is_boss):
                self.assertIsNone(
                    choose_battle_modifier(
                        rng=_FailIfUsedRandom(),
                        is_first_battle=is_first_battle,
                        is_boss=is_boss,
                        modifier_chance=1.0,
                    )
                )

    def test_selection_returns_at_most_one_known_modifier(self) -> None:
        rng = random.Random(17)
        results = [
            choose_battle_modifier(
                rng=rng,
                is_first_battle=False,
                is_boss=False,
                modifier_chance=1.0,
            )
            for _ in range(100)
        ]
        self.assertTrue(all(isinstance(result, BattleModifier) for result in results))
        self.assertEqual(set(results), {BattleModifier.RAMPART, BattleModifier.GREED})

    def test_zero_chance_never_selects_a_modifier(self) -> None:
        rng = random.Random(5)
        self.assertTrue(
            all(
                choose_battle_modifier(
                    rng=rng,
                    is_first_battle=False,
                    is_boss=False,
                    modifier_chance=0.0,
                )
                is None
                for _ in range(20)
            )
        )

    def test_rampart_opening_shield_reuses_enemy_defense(self) -> None:
        self.assertEqual(
            opening_shield_for(BattleModifier.RAMPART, enemy_defense=23),
            23,
        )
        self.assertEqual(
            opening_shield_for(BattleModifier.RAMPART, enemy_defense=0),
            1,
        )
        self.assertEqual(
            opening_shield_for(BattleModifier.GREED, enemy_defense=23),
            0,
        )
        self.assertEqual(opening_shield_for(None, enemy_defense=23), 0)

    def test_greed_reward_and_attack_multipliers_are_explicit(self) -> None:
        greed = modifier_spec(BattleModifier.GREED)
        self.assertIsNotNone(greed)
        assert greed is not None
        self.assertEqual(greed.reward_multiplier, 2.0)
        self.assertEqual(greed.enemy_attack_multiplier, 1.15)
        self.assertEqual(reward_multiplier_for(BattleModifier.GREED), 2.0)
        self.assertEqual(reward_multiplier_for(BattleModifier.RAMPART), 1.0)
        self.assertEqual(reward_multiplier_for(None), 1.0)
        self.assertEqual(
            modified_enemy_stats(
                BattleModifier.GREED,
                max_hp=100,
                attack=20,
                defense=15,
            ),
            (100, 23, 15),
        )

    def test_unknown_or_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            choose_battle_modifier(
                rng=random.Random(1),
                is_first_battle=False,
                is_boss=False,
                modifier_chance=1.01,
            )
        with self.assertRaises(ValueError):
            modifier_spec("fog")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
