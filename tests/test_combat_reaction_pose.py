from types import SimpleNamespace

from rpg_drawing import combat_reaction_pose


def animation(attacker: str, damage: int, *, impacted: bool = True,
              enemy_index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        attacker=attacker,
        damage=damage,
        impacted=impacted,
        enemy_index=enemy_index,
    )


def test_reaction_waits_until_impact() -> None:
    pending = animation("enemy", 7, impacted=False)
    assert combat_reaction_pose(pending, "player") == "idle"


def test_hp_loss_uses_hurt_and_zero_loss_uses_block() -> None:
    assert combat_reaction_pose(animation("enemy", 7), "player") == "hurt"
    assert combat_reaction_pose(animation("enemy", 0), "player") == "block"
    assert combat_reaction_pose(animation("player", 7), "enemy") == "hurt"
    assert combat_reaction_pose(animation("player", 0), "enemy") == "block"


def test_only_the_attacked_enemy_reacts() -> None:
    hit_second = animation("player", 5, enemy_index=1)
    assert combat_reaction_pose(hit_second, "enemy", 0) == "idle"
    assert combat_reaction_pose(hit_second, "enemy", 1) == "hurt"


def test_attacker_is_not_misclassified_as_target() -> None:
    player_attack = animation("player", 4)
    enemy_attack = animation("enemy", 4)
    assert combat_reaction_pose(player_attack, "player") == "idle"
    assert combat_reaction_pose(enemy_attack, "enemy") == "idle"
