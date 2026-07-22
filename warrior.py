import math


JOB = "戰士"
LEGACY_NAME = "血祭強襲"
LEGACY_DESCRIPTION = "消耗 35% 目前血量換取追加傷害，之後回流部分生命。"

TALENTS = {
    "weapon_mastery": {
        "tier": 1, "side": 0, "max": 3, "name": "武器專精",
        "desc": "斬擊傷害提升。",
        "details": ("1點：斬擊傷害 +10%。", "2點：斬擊傷害 +20%。", "3點：斬擊傷害 +30%。"),
    },
    "shield_mastery": {
        "tier": 1, "side": 1, "max": 3, "name": "盾牌專精",
        "desc": "格擋護盾提升。",
        "details": ("1點：格擋護盾 +15%。", "2點：格擋護盾 +30%。", "3點：格擋護盾 +45%。"),
    },
    "cleave": {
        "tier": 2, "side": 0, "max": 3, "name": "順劈斬",
        "desc": "解鎖強力攻擊招式。",
        "details": ("1點：解鎖順劈斬，造成 170% 攻擊傷害，冷卻 3 回合。",
                    "2點：順劈斬提高為 210% 攻擊傷害。",
                    "3點：順劈斬冷卻降為 2 回合。"),
    },
    "fortify": {
        "tier": 2, "side": 1, "max": 3, "name": "鋼鐵壁壘",
        "desc": "解鎖強力防禦招式。",
        "details": ("1點：解鎖鋼鐵壁壘，獲得 180% 防禦的護盾，冷卻 3 回合。",
                    "2點：護盾提高為 230% 防禦。",
                    "3點：同時清除持續傷害。"),
    },
    "last_stand": {
        "tier": 3, "side": 0, "max": 3, "name": "最後防線",
        "desc": "解鎖保命招式。",
        "details": ("1點：解鎖最後防線，本場戰鬥第一次致命傷保留 1 血。",
                    "2點：觸發時獲得 25% 最大血量的護盾。",
                    "3點：觸發後下一次攻擊追加 25% 最大血量傷害。"),
    },
    "counter": {
        "tier": 3, "side": 1, "max": 3, "name": "盾擊反制",
        "desc": "解鎖攻防一體招式。",
        "details": ("1點：解鎖盾擊反制，獲得 120% 防禦護盾並造成 80% 攻擊傷害，冷卻 4 回合。",
                    "2點：傷害提高為 120% 攻擊。",
                    "3點：冷卻降為 3 回合。"),
    },
    "bladestorm": {
        "tier": 4, "side": 0, "max": 1, "name": "劍刃風暴",
        "desc": "解鎖大絕招。",
        "details": ("1點：解鎖劍刃風暴，造成 320% 攻擊傷害，本場戰鬥只能使用一次。",),
    },
}


def legacy_ready(game) -> bool:
    return game.warrior_attack_bonus < 1 and game.player.hp > 1


def legacy_active(game) -> bool:
    return game.warrior_attack_bonus > 0


def legacy_description(game) -> str:
    cost = min(max(1, math.ceil(game.player.hp * .35)), max(0, game.player.hp - 1))
    bonus = min(cost, max(1, math.ceil(game.effective_player_attack() * 1.25)))
    healing = max(1, math.ceil(cost * .30))
    return (f"消耗 {cost} 點血量，使下一次攻擊追加 {bonus} 點傷害；"
            f"之後 2 回合每回合恢復 {healing} 點血量。")


def activate_legacy(game) -> bool:
    if game.warrior_attack_bonus > 0 or game.player.hp <= 1:
        return False
    cost = min(max(1, math.ceil(game.player.hp * .35)), game.player.hp - 1)
    game.player.hp -= cost
    # 免費專屬技能的追加傷害限制為攻擊 1.25 倍，並保留實際血量代價。
    bonus = min(cost, max(1, math.ceil(game.effective_player_attack() * 1.25)))
    game.warrior_attack_bonus = bonus
    game.warrior_blood_regen = max(1, math.ceil(cost * .30))
    game.warrior_blood_regen_turns = 2
    game.log(f"你發動血祭強襲，犧牲 {cost} 點血量；下一次攻擊追加 {bonus} 傷害。")
    game.log(f"祭出的鮮血將在接下來 2 回合，每回合回流 {game.warrior_blood_regen} 點血量。")
    return True


def tooltip(game, action_id: str) -> str:
    if action_id == "slash":
        multiplier = 1.0 + game.class_talent_rank("weapon_mastery") * .10
        return f"{game.preview_skill_damage_text(multiplier)}。"
    if action_id == "guard":
        multiplier = 1.0 + game.class_talent_rank("shield_mastery") * .15
        return f"獲得 {game.preview_skill_block(multiplier)} 點護盾。"
    if action_id == "cleave":
        rank = game.class_talent_rank("cleave")
        multiplier = 1.7 if rank == 1 else 2.1
        cooldown = 2 if rank >= 3 else 3
        return f"{game.preview_skill_damage_text(multiplier)}，冷卻 {cooldown} 回合。"
    if action_id == "fortify":
        rank = game.class_talent_rank("fortify")
        multiplier = 2.3 if rank >= 2 else 1.8
        extra = "施放時清除持續傷害。" if rank >= 3 else ""
        return f"獲得 {game.preview_skill_block(multiplier)} 點護盾，冷卻 3 回合。{extra}"
    if action_id == "counter":
        rank = game.class_talent_rank("counter")
        damage = 1.2 if rank >= 2 else .8
        cooldown = 3 if rank >= 3 else 4
        return (f"獲得 {game.preview_skill_block(1.2)} 點護盾，並"
                f"{game.preview_skill_damage_text(damage)}，冷卻 {cooldown} 回合。")
    if action_id == "bladestorm":
        return f"{game.preview_skill_damage_text(3.2)}，本場戰鬥只能使用一次。"
    return ""


def action_slots(game):
    slots = [
        ("斬擊", "slash", True, (147, 92, 54), tooltip(game, "slash")),
        ("格擋", "guard", True, (75, 104, 129), tooltip(game, "guard")),
    ]
    for action_id, name, accent in (
        ("cleave", "順劈斬", (170, 84, 48)),
        ("fortify", "鋼鐵壁壘", (75, 104, 129)),
        ("counter", "盾擊反制", (112, 82, 48)),
        ("bladestorm", "劍刃風暴", (150, 80, 55)),
    ):
        if game.class_talent_rank(action_id) > 0:
            slots.append((game.class_action_label(action_id, name), action_id,
                          game.class_action_ready(action_id), accent, tooltip(game, action_id)))
    return slots


def execute(game, action_id: str) -> None:
    if action_id == "slash":
        game.class_attack_skill(action_id, 1.0 + game.class_talent_rank("weapon_mastery") * .10)
    elif action_id == "guard":
        if not game.enemy or game.battle_busy:
            return
        block = max(1, math.ceil(game.effective_player_defense() * (1.0 + game.class_talent_rank("shield_mastery") * .15)))
        game.player_block += block
        game.log(f"你舉盾格擋，獲得 {block} 點護盾。")
        game.finish_class_action(action_id)
    elif action_id == "cleave":
        rank = game.class_talent_rank("cleave")
        if rank < 1:
            return
        game.class_attack_skill(action_id, 2.1 if rank >= 2 else 1.7, 2 if rank >= 3 else 3)
    elif action_id == "fortify":
        rank = game.class_talent_rank("fortify")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        block = max(1, math.ceil(game.effective_player_defense() * (2.3 if rank >= 2 else 1.8)))
        game.player_block += block
        if rank >= 3 and game.player_dot_damage > 0:
            game.clear_player_dot()
            game.log("鋼鐵壁壘清除了持續傷害。")
        game.log(f"你架起鋼鐵壁壘，獲得 {block} 點護盾。")
        game.class_skill_cooldowns[action_id] = 3
        game.finish_class_action(action_id)
    elif action_id == "counter":
        rank = game.class_talent_rank("counter")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        block = max(1, math.ceil(game.effective_player_defense() * 1.2))
        game.player_block += block
        game.log(f"你準備盾擊反制，獲得 {block} 點護盾。")
        game.class_attack_skill(action_id, 1.2 if rank >= 2 else .8, 3 if rank >= 3 else 4)
    elif action_id == "bladestorm":
        if game.class_talent_rank("bladestorm") < 1:
            return
        game.class_attack_skill(action_id, 3.2, once=True)


def prevent_death(game) -> bool:
    rank = game.class_talent_rank("last_stand")
    if rank < 1 or getattr(game, "warrior_last_stand_used", False) or game.player.hp > 0:
        return False
    game.warrior_last_stand_used = True
    game.player.hp = 1
    if rank >= 2:
        block = max(1, math.ceil(game.player.max_hp * .25))
        game.player_block += block
        game.log(f"最後防線保住了你，並獲得 {block} 點護盾。")
    else:
        game.log("最後防線保住了你，生命保留 1 點。")
    if rank >= 3:
        bonus = max(1, math.ceil(game.player.max_hp * .25))
        game.warrior_attack_bonus += bonus
        game.log(f"你的反擊意志凝聚，下次攻擊追加 {bonus} 傷害。")
    return True
