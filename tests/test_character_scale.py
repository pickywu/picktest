from __future__ import annotations

import math

from character_scale import (
    MONSTER_IDLE_WIDTH_ALLOWANCE,
    PLAYER_RACE_HEIGHT_FACTORS,
    REACTION_REFERENCE_HEIGHT,
    load_character_scale_manifest,
    monster_pose_anchor_x,
    monster_pose_scale,
    monster_uniform_scale,
    player_pose_anchor_x,
    player_uniform_scale,
)


def test_manifest_covers_all_player_and_monster_identities() -> None:
    manifest = load_character_scale_manifest()
    assert len(manifest["players"]) == 40
    assert len(manifest["monsters"]) == 18
    assert manifest["policy"]["source_pngs_are_immutable"] is True
    assert manifest["policy"]["scale_source_pose"] == "idle"
    for category in ("players", "monsters"):
        for record in manifest[category].values():
            assert set(record["poses"]) == {"idle", "attack", "hurt", "block"}
            for pose in ("hurt", "block"):
                assert record["poses"][pose]["canvas"] == [1024, 1024]
                assert record["poses"][pose]["mode"] == "RGBA"


def test_player_scale_uses_only_reviewed_idle_body_height() -> None:
    manifest = load_character_scale_manifest()
    elf_target_height = 270.0
    for identity, record in manifest["players"].items():
        sex, race, job = identity.split("/")
        body_height = float(record["idle_body"]["body_height"])
        narrow = player_uniform_scale(sex, race, job, elf_target_height, 80.0)
        wide = player_uniform_scale(sex, race, job, elf_target_height, 800.0)
        expected = elf_target_height * PLAYER_RACE_HEIGHT_FACTORS[race]
        assert math.isclose(narrow, wide, rel_tol=0.0, abs_tol=1e-12)
        assert math.isclose(body_height * narrow, expected, rel_tol=0.0,
                            abs_tol=1e-9)


def test_every_player_pose_has_a_manifest_anchor() -> None:
    manifest = load_character_scale_manifest()
    for identity, record in manifest["players"].items():
        sex, race, job = identity.split("/")
        for pose, metrics in record["poses"].items():
            assert player_pose_anchor_x(sex, race, job, pose) == metrics["anchor_x"]


def test_standardized_player_reactions_do_not_inherit_mixed_source_canvas_scale() -> None:
    expected = 270.0 * PLAYER_RACE_HEIGHT_FACTORS["dwarf"] / REACTION_REFERENCE_HEIGHT
    assert math.isclose(
        player_uniform_scale(
            "female", "dwarf", "mage", 270.0, 230.0, "hurt"
        ),
        expected,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_monsters_use_paired_idle_scale_with_only_a_loose_width_guard() -> None:
    manifest = load_character_scale_manifest()
    for identity, record in manifest["monsters"].items():
        rank_name, kind = identity.split("/")
        rank = int(rank_name.removeprefix("rank_"))
        idle = record["idle_body"]
        expected = min(
            285.0 / float(idle["body_height"]),
            250.0 * MONSTER_IDLE_WIDTH_ALLOWANCE
            / float(record["poses"]["idle"]["visible_width"]),
        )
        assert math.isclose(
            monster_uniform_scale(rank, kind, 285.0, 250.0), expected,
            rel_tol=0.0, abs_tol=1e-12,
        )
        for pose, metrics in record["poses"].items():
            assert monster_pose_anchor_x(rank, kind, pose) == metrics["anchor_x"]


def test_standardized_monster_reactions_preserve_idle_display_height() -> None:
    manifest = load_character_scale_manifest()
    identity = "rank_01/attack"
    record = manifest["monsters"][identity]
    rank_name, kind = identity.split("/")
    rank = int(rank_name.removeprefix("rank_"))
    idle_scale = monster_pose_scale(rank, kind, "idle", 285.0, 250.0)
    hurt_scale = monster_pose_scale(rank, kind, "hurt", 285.0, 250.0)
    idle_height = float(record["poses"]["idle"]["visible_height"])
    assert math.isclose(
        hurt_scale * REACTION_REFERENCE_HEIGHT,
        idle_scale * idle_height,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
