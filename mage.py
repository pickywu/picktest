import math
import random


JOB = "法師"
LEGACY_NAME = "命運改寫"
LEGACY_DESCRIPTION = "重抽目標怪物目前意圖。"

TALENTS = {
    "fire_mastery": {
        "tier": 1, "side": 0, "max": 3, "name": "火焰專精",
        "desc": "火球術傷害 +10% / +20% / +30%。",
        "details": ("1點：火球術傷害 +10%。", "2點：火球術傷害 +20%。", "3點：火球術傷害 +30%。"),
    },
    "frost_mastery": {
        "tier": 1, "side": 1, "max": 3, "name": "寒冰專精",
        "desc": "冰甲術護盾 +15% / +30% / +45%。",
        "details": ("1點：冰甲術護盾 +15%。", "2點：冰甲術護盾 +30%。", "3點：冰甲術護盾 +45%。"),
    },
    "pyroblast": {
        "tier": 2, "side": 0, "max": 3, "name": "炎爆術",
        "desc": "1點解鎖攻擊法術；2點提高傷害；3點冷卻 -1。",
        "details": ("1點：解鎖炎爆術，造成 180% 攻擊傷害，冷卻 3 回合。",
                    "2點：炎爆術提高為 220% 攻擊傷害。",
                    "3點：炎爆術冷卻降為 2 回合。"),
    },
    "ice_wall": {
        "tier": 2, "side": 1, "max": 3, "name": "冰牆術",
        "desc": "1點解鎖防禦法術；2點提高護盾；3點清除持續傷害。",
        "details": ("1點：解鎖冰牆術，獲得 160% 防禦的護盾，冷卻 3 回合。",
                    "2點：冰牆術提高為 200% 防禦的護盾。",
                    "3點：施放時清除身上的持續傷害。"),
    },
    "ice_barrier": {
        "tier": 3, "side": 0, "max": 3, "name": "寒冰屏障",
        "desc": "1點解鎖保命招式；2點附加護盾；3點冷卻 -1。",
        "details": ("1點：解鎖寒冰屏障，免疫下一次敵方攻擊，冷卻 4 回合。",
                    "2點：施放時額外獲得 30% 最大血量的護盾。",
                    "3點：寒冰屏障冷卻降為 3 回合。"),
    },
    "mana_shield": {
        "tier": 3, "side": 1, "max": 3, "name": "法力護盾",
        "desc": "致命傷保留 1 血；高階會給護盾並清除持續傷害。",
        "details": ("1點：每場戰鬥第一次致命傷保留 1 點血量。",
                    "2點：觸發時額外獲得 20% 最大血量的護盾。",
                    "3點：觸發時清除身上的持續傷害。"),
    },
    "meteor": {
        "tier": 4, "side": 0, "max": 1, "name": "隕石風暴",
        "desc": "解鎖大絕，造成 320% 攻擊傷害並壓制敵方攻擊意圖。",
        "details": ("1點：解鎖隕石風暴，造成 320% 攻擊傷害；本場戰鬥只能使用一次，並壓制敵方下一次攻擊或昏迷意圖。",),
    },
}


def legacy_ready(game) -> bool:
    return bool(game.enemy_intent)


def legacy_active(game) -> bool:
    return False


def activate_legacy(game) -> bool:
    if not game.enemy_intent:
        return False
    old_intent = game.enemy_intent
    choices = [intent for intent in game.enemy_intent_pool() if intent != old_intent]
    if not choices:
        return False
    game.enemy_intent = random.choice(choices)
    game.log(f"你施放命運改寫，目標意圖變成：{game.enemy_intent_label()}。")
    return True


def tooltip(game, action_id: str) -> str:
    if action_id == "fireball":
        multiplier = int((1.0 + game.class_talent_rank("fire_mastery") * .10) * 100)
        return f"造成 {multiplier}% 攻擊傷害。"
    if action_id == "ice_armor":
        multiplier = int((1.0 + game.class_talent_rank("frost_mastery") * .15) * 100)
        return f"獲得 {multiplier}% 防禦的護盾。"
    if action_id == "pyroblast":
        rank = game.class_talent_rank("pyroblast")
        multiplier = 180 if rank == 1 else 220
        cooldown = 2 if rank >= 3 else 3
        return f"造成 {multiplier}% 攻擊傷害，冷卻 {cooldown} 回合。"
    if action_id == "ice_wall":
        rank = game.class_talent_rank("ice_wall")
        multiplier = 200 if rank >= 2 else 160
        extra = "施放時清除持續傷害。" if rank >= 3 else ""
        return f"獲得 {multiplier}% 防禦的護盾，冷卻 3 回合。{extra}"
    if action_id == "ice_barrier":
        rank = game.class_talent_rank("ice_barrier")
        cooldown = 3 if rank >= 3 else 4
        extra = "施放時獲得 30% 最大血量的護盾。" if rank >= 2 else ""
        return f"免疫下一次敵方攻擊，冷卻 {cooldown} 回合。{extra}"
    if action_id == "meteor":
        return "造成 320% 攻擊傷害，本場戰鬥只能使用一次，並壓制敵方下一次攻擊或昏迷意圖。"
    return ""


def action_slots(game):
    slots = [
        ("火球術", "fireball", True, (147, 92, 54), tooltip(game, "fireball")),
        ("冰甲術", "ice_armor", True, (75, 104, 129), tooltip(game, "ice_armor")),
    ]
    unlocks = (
        ("pyroblast", "炎爆術", (170, 84, 48)),
        ("ice_wall", "冰牆術", (75, 104, 129)),
        ("ice_barrier", "寒冰屏障", (62, 100, 139)),
        ("meteor", "隕石風暴", (150, 80, 55)),
    )
    for action_id, name, accent in unlocks:
        if game.class_talent_rank(action_id) > 0:
            slots.append((
                game.class_action_label(action_id, name),
                action_id,
                game.class_action_ready(action_id),
                accent,
                tooltip(game, action_id),
            ))
    return slots


def execute(game, action_id: str) -> None:
    if action_id == "fireball":
        rank = game.class_talent_rank("fire_mastery")
        game.class_attack_skill(action_id, 1.0 + rank * .10)
    elif action_id == "ice_armor":
        if not game.enemy or game.battle_busy:
            return
        rank = game.class_talent_rank("frost_mastery")
        block = max(1, math.ceil(game.effective_player_defense() * (1.0 + rank * .15)))
        game.player_block += block
        game.log(f"你施放冰甲術，獲得 {block} 點護盾。")
        game.finish_class_action(action_id)
    elif action_id == "pyroblast":
        rank = game.class_talent_rank("pyroblast")
        if rank < 1:
            return
        multiplier = 1.8 if rank == 1 else 2.2
        cooldown = 2 if rank >= 3 else 3
        game.class_attack_skill(action_id, multiplier, cooldown)
    elif action_id == "ice_wall":
        rank = game.class_talent_rank("ice_wall")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        multiplier = 2.0 if rank >= 2 else 1.6
        block = max(1, math.ceil(game.effective_player_defense() * multiplier))
        game.player_block += block
        if rank >= 3 and game.player_dot_damage > 0:
            game.clear_player_dot()
            game.log("冰牆術驅散了持續傷害。")
        game.log(f"你施放冰牆術，獲得 {block} 點護盾。")
        game.class_skill_cooldowns[action_id] = 3
        game.finish_class_action(action_id)
    elif action_id == "ice_barrier":
        rank = game.class_talent_rank("ice_barrier")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        game.mage_ice_barrier_turns = 1
        if rank >= 2:
            block = max(1, math.ceil(game.player.max_hp * .30))
            game.player_block += block
            game.log(f"你施放寒冰屏障，免疫下一次攻擊並獲得 {block} 點護盾。")
        else:
            game.log("你施放寒冰屏障，免疫下一次敵方攻擊。")
        game.class_skill_cooldowns[action_id] = 3 if rank >= 3 else 4
        game.finish_class_action(action_id)
    elif action_id == "meteor":
        if game.class_talent_rank("meteor") < 1:
            return
        game.log("你召喚隕石風暴，壓制敵方下一次攻擊意圖。")
        game.class_attack_skill(action_id, 3.2, suppress_next_attack=True)


def prevent_death(game) -> bool:
    rank = game.class_talent_rank("mana_shield")
    if rank < 1 or game.mage_mana_shield_used or game.player.hp > 0:
        return False
    game.mage_mana_shield_used = True
    game.player.hp = 1
    if rank >= 2:
        block = max(1, math.ceil(game.player.max_hp * .20))
        game.player_block += block
        game.log(f"法力護盾保住了你，並獲得 {block} 點護盾。")
    else:
        game.log("法力護盾保住了你，生命保留 1 點。")
    if rank >= 3 and game.player_dot_damage > 0:
        game.clear_player_dot()
        game.log("法力護盾清除了持續傷害。")
    return True
