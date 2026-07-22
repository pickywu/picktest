from pathlib import Path
from types import SimpleNamespace

import pytest

from combat_intents import INTENT_SPECS
from ui.combat_icons import (
    ENEMY_STATUS_ICONS,
    INTENT_ICONS,
    PLAYER_STATUS_ICONS,
    collect_enemy_status_badges,
    collect_player_status_badges,
    enemy_status_icon,
    intent_icon,
    missing_primary_assets,
    player_status_icon,
)


def test_every_gameplay_intent_has_an_explicit_icon_contract() -> None:
    assert set(INTENT_ICONS) == set(INTENT_SPECS)
    assert all(spec.semantic_key for spec in INTENT_ICONS.values())
    assert all(spec.asset_path.startswith("icons/intents/")
               for spec in INTENT_ICONS.values())


def test_mechanically_different_high_risk_intents_have_unique_primary_art() -> None:
    keys = ("attack", "strong_attack", "heavy_blow", "lifedrain", "strong_dot")
    primary_paths = [INTENT_ICONS[key].asset_path for key in keys]
    semantic_keys = [INTENT_ICONS[key].semantic_key for key in keys]
    assert len(primary_paths) == len(set(primary_paths))
    assert len(semantic_keys) == len(set(semantic_keys))


def test_all_current_player_overhead_mechanics_are_registered() -> None:
    assert {
        "block",
        "dark_mist",
        "curse",
        "stunned",
        "attack_immunity",
        "stun_immunity",
        "ice_barrier",
        "blood_sacrifice",
        "blood_regeneration",
        "stealth",
        "guaranteed_critical",
        "attack_boost",
        "defense_boost",
        "iron_skin",
    } <= set(PLAYER_STATUS_ICONS)


def test_all_enemy_portrait_status_mechanics_are_registered() -> None:
    assert {
        "block",
        "corrosion",
        "agony",
        "doom",
        "weak",
        "immune",
        "reflect",
        "stealth",
        "stunned",
        "heavy_blow_charged",
        "berserk",
        "bulwark",
    } <= set(ENEMY_STATUS_ICONS)


def test_best_asset_path_uses_only_the_declared_fallback(tmp_path: Path) -> None:
    spec = INTENT_ICONS["heavy_blow"]
    fallback = tmp_path / str(spec.fallback_asset_path)
    fallback.parent.mkdir(parents=True)
    fallback.touch()
    assert spec.best_asset_path(tmp_path) == spec.fallback_asset_path

    primary = tmp_path / spec.asset_path
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.touch()
    assert spec.best_asset_path(tmp_path) == spec.asset_path


def test_missing_primary_assets_is_deduplicated_and_sorted(tmp_path: Path) -> None:
    attack = tmp_path / INTENT_ICONS["attack"].asset_path
    attack.parent.mkdir(parents=True)
    attack.touch()
    missing = missing_primary_assets(tmp_path, INTENT_ICONS)
    assert INTENT_ICONS["attack"].asset_path not in missing
    assert INTENT_ICONS["heavy_blow"].asset_path in missing
    assert missing == tuple(sorted(set(missing)))


def test_lookup_helpers_reject_unknown_mechanics() -> None:
    assert intent_icon("attack") is INTENT_ICONS["attack"]
    assert player_status_icon("stealth") is PLAYER_STATUS_ICONS["stealth"]
    assert enemy_status_icon("doom") is ENEMY_STATUS_ICONS["doom"]
    with pytest.raises(KeyError):
        intent_icon("surprise_party")
    with pytest.raises(KeyError):
        player_status_icon("surprise_party")
    with pytest.raises(KeyError):
        enemy_status_icon("surprise_party")


def test_player_status_collector_emits_localized_labels_values_and_icons() -> None:
    state = SimpleNamespace(
        player_stun_turns=0,
        player_dot_damage=3,
        player_dot_turns=2,
        player_dot_stacks=2,
        player_curse_turns=1,
        player_block=17,
        player_attack_immunity_turns=1,
        mage_ice_barrier_turns=0,
        player_stun_immunity_turns=0,
        potion_iron_skin_turns=1,
        stealth_turns=1,
        potion_attack_boost=True,
        potion_defense_boost=False,
        warrior_attack_bonus=4,
        warrior_blood_regen_turns=2,
        warrior_blood_regen=3,
        forced_critical=True,
    )
    badges = collect_player_status_badges(state)
    by_key = {badge.key: badge for badge in badges}
    assert by_key["dark_mist"].value == "6×2 ·2"
    assert by_key["dark_mist"].label("zh-TW") == "黑霧"
    assert by_key["dark_mist"].label("EN") == "BLACK MIST"
    assert by_key["block"].value == "17"
    assert by_key["attack_boost"].value == "+50%"
    assert by_key["blood_sacrifice"].value == "+4"
    assert by_key["blood_regeneration"].value == "3×2"
    assert by_key["guaranteed_critical"].value == "100%"
    assert all(badge.icon is PLAYER_STATUS_ICONS[badge.key] for badge in badges)


def test_enemy_status_collector_covers_current_portrait_mechanics() -> None:
    enemy = SimpleNamespace(
        block=8,
        corrosion_turns=2,
        corrosion_damage=4,
        agony_turns=3,
        agony_damage=2,
        agony_stacks=2,
        doom_turns=1,
        doom_damage=15,
        weak_turns=2,
        immune_turns=1,
        reflect_turns=1,
        stealth_turns=1,
        skip_turns=1,
        heavy_blow_charged=True,
        berserk_stacks=2,
        bulwark_stacks=3,
    )
    badges = collect_enemy_status_badges(enemy)
    assert set(badge.key for badge in badges) == set(ENEMY_STATUS_ICONS)
    assert next(b for b in badges if b.key == "doom").value == "15@1"
    assert next(b for b in badges if b.key == "agony").value == "4×3 ·2"
