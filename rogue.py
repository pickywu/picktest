import math


JOB = "盜賊"
LEGACY_NAME = "悶棍"
LEGACY_DESCRIPTION = "擊暈怪物一回合。"

TALENTS = {
    "dagger_mastery": {
        "tier": 1, "side": 0, "max": 3, "name": "匕首專精",
        "desc": "刺擊傷害提升。",
        "details": ("1點：刺擊傷害提高為 117%。", "2點：刺擊傷害提高為 124%。", "3點：刺擊傷害提高為 130%。"),
    },
    "evasion": {
        "tier": 1, "side": 1, "max": 3, "name": "閃避專精",
        "desc": "煙霧護盾提升。",
        "details": ("1點：煙霧護盾 +15%。", "2點：煙霧護盾 +30%。", "3點：煙霧護盾 +45%。"),
    },
    "backstab": {
        "tier": 2, "side": 0, "max": 3, "name": "背刺",
        "desc": "解鎖強力攻擊招式。",
        "details": ("1點：解鎖背刺，造成 175% 攻擊傷害，冷卻 3 回合。",
                    "2點：若敵方沒有護盾，背刺提高為 240% 攻擊傷害。",
                    "3點：背刺冷卻降為 2 回合。"),
    },
    "smoke_bomb": {
        "tier": 2, "side": 1, "max": 3, "name": "煙霧彈",
        "desc": "解鎖防禦控制招式。",
        "details": ("1點：解鎖煙霧彈，獲得 150% 防禦的護盾並隱身 1 回合，冷卻 4 回合。",
                    "2點：護盾提高為 200% 防禦。",
                    "3點：冷卻降為 3 回合。"),
    },
    "vanish": {
        "tier": 3, "side": 0, "max": 3, "name": "消失",
        "desc": "解鎖保命招式。",
        "details": ("1點：解鎖消失，隱身 1 回合並清除持續傷害，冷卻 4 回合。",
                    "2點：同時獲得 20% 最大血量的護盾。",
                    "3點：冷卻降為 3 回合。"),
    },
    "shadowstep": {
        "tier": 3, "side": 1, "max": 3, "name": "暗影步",
        "desc": "解鎖爆發招式。",
        "details": ("1點：解鎖暗影步，造成 120% 攻擊傷害，這一擊必定造成盜賊的 175% 暴擊傷害，冷卻 4 回合。",
                    "2點：傷害提高為 160%。",
                    "3點：冷卻降為 3 回合。"),
    },
    "assassinate": {
        "tier": 4, "side": 0, "max": 1, "name": "暗殺",
        "desc": "解鎖大絕招。",
        "details": ("1點：解鎖暗殺，造成 300% 攻擊傷害；若敵方沒有護盾，改為 380%，本場戰鬥只能使用一次。",),
    },
}


def legacy_ready(game) -> bool:
    return game.enemy_skip_turns < 1


def legacy_active(game) -> bool:
    return game.enemy_skip_turns > 0


def activate_legacy(game) -> bool:
    if not game.enemy or game.enemy_skip_turns > 0:
        return False
    blocked_by = game.consume_enemy_attack_protection(game.enemy)
    if blocked_by:
        game.log_enemy_attack_block(game.enemy, blocked_by, "悶棍")
        return True
    game.enemy_skip_turns = 1
    game.log("你使出悶棍擊暈怪物，它下一回合無法行動。")
    return True


def stab_multiplier(game) -> float:
    """Improve the rogue's first levels without raising the old 130% cap."""
    return (1.10, 1.17, 1.24, 1.30)[game.class_talent_rank("dagger_mastery")]


def tooltip(game, action_id: str) -> str:
    if action_id == "stab":
        return f"{game.preview_skill_damage_text(stab_multiplier(game))}。"
    if action_id == "smokescreen":
        multiplier = 1.0 + game.class_talent_rank("evasion") * .15
        return f"獲得 {game.preview_skill_block(multiplier)} 點護盾。"
    if action_id == "backstab":
        rank = game.class_talent_rank("backstab")
        cooldown = 2 if rank >= 3 else 3
        multiplier = 2.4 if rank >= 2 and game.enemy_block < 1 else 1.75
        condition = "（敵方無護盾加成）" if multiplier == 2.4 else ""
        return f"{game.preview_skill_damage_text(multiplier)}{condition}，冷卻 {cooldown} 回合。"
    if action_id == "smoke_bomb":
        rank = game.class_talent_rank("smoke_bomb")
        block = game.preview_skill_block(2.0 if rank >= 2 else 1.5)
        cooldown = 3 if rank >= 3 else 4
        return f"獲得 {block} 點護盾並隱身 1 回合，冷卻 {cooldown} 回合。"
    if action_id == "vanish":
        rank = game.class_talent_rank("vanish")
        cooldown = 3 if rank >= 3 else 4
        extra = f"並獲得 {game.preview_max_hp_amount(.20)} 點護盾。" if rank >= 2 else ""
        return f"隱身 1 回合並清除持續傷害，冷卻 {cooldown} 回合。{extra}"
    if action_id == "shadowstep":
        rank = game.class_talent_rank("shadowstep")
        damage = 1.6 if rank >= 2 else 1.2
        cooldown = 3 if rank >= 3 else 4
        return f"{game.preview_skill_damage_text(damage, True)}，冷卻 {cooldown} 回合。"
    if action_id == "assassinate":
        multiplier = 3.8 if game.enemy_block < 1 else 3.0
        condition = "（敵方無護盾加成）" if multiplier == 3.8 else ""
        return (f"{game.preview_skill_damage_text(multiplier)}{condition}，"
                "本場戰鬥只能使用一次。")
    return ""


def action_slots(game):
    slots = [
        ("刺擊", "stab", True, (147, 92, 54), tooltip(game, "stab")),
        ("煙幕", "smokescreen", True, (75, 104, 129), tooltip(game, "smokescreen")),
    ]
    for action_id, name, accent in (
        ("backstab", "背刺", (170, 84, 48)),
        ("smoke_bomb", "煙霧彈", (75, 104, 129)),
        ("vanish", "消失", (62, 100, 139)),
        ("shadowstep", "暗影步", (123, 74, 128)),
        ("assassinate", "暗殺", (150, 80, 55)),
    ):
        if game.class_talent_rank(action_id) > 0:
            slots.append((game.class_action_label(action_id, name), action_id,
                          game.class_action_ready(action_id), accent, tooltip(game, action_id)))
    return slots


def execute(game, action_id: str) -> None:
    if action_id == "stab":
        game.class_attack_skill(action_id, stab_multiplier(game))
    elif action_id == "smokescreen":
        if not game.enemy or game.battle_busy:
            return
        block = max(1, math.ceil(game.effective_player_defense() * (1.0 + game.class_talent_rank("evasion") * .15)))
        game.player_block += block
        game.log(f"你展開煙幕，獲得 {block} 點護盾。")
        game.finish_class_action(action_id)
    elif action_id == "backstab":
        rank = game.class_talent_rank("backstab")
        if rank < 1:
            return
        multiplier = 2.4 if rank >= 2 and game.enemy_block < 1 else 1.75
        game.class_attack_skill(action_id, multiplier, 2 if rank >= 3 else 3)
    elif action_id == "smoke_bomb":
        rank = game.class_talent_rank("smoke_bomb")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        block = max(1, math.ceil(game.effective_player_defense() * (2.0 if rank >= 2 else 1.5)))
        game.player_block += block
        game.stealth_turns = 1
        game.log(f"煙霧彈遮蔽戰場，獲得 {block} 點護盾並進入隱身。")
        game.class_skill_cooldowns[action_id] = 3 if rank >= 3 else 4
        game.finish_class_action(action_id)
    elif action_id == "vanish":
        rank = game.class_talent_rank("vanish")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        game.stealth_turns = 1
        game.clear_player_dot()
        if rank >= 2:
            block = max(1, math.ceil(game.player.max_hp * .20))
            game.player_block += block
            game.log(f"你消失在陰影中，清除持續傷害並獲得 {block} 點護盾。")
        else:
            game.log("你消失在陰影中，清除持續傷害。")
        game.class_skill_cooldowns[action_id] = 3 if rank >= 3 else 4
        game.finish_class_action(action_id)
    elif action_id == "shadowstep":
        rank = game.class_talent_rank("shadowstep")
        if rank < 1 or not game.class_action_ready(action_id):
            return
        game.forced_critical = True
        game.class_attack_skill(action_id, 1.6 if rank >= 2 else 1.2, 3 if rank >= 3 else 4)
    elif action_id == "assassinate":
        if game.class_talent_rank("assassinate") < 1:
            return
        multiplier = 3.8 if game.enemy_block < 1 else 3.0
        game.class_attack_skill(action_id, multiplier, once=True)
