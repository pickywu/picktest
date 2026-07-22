import math


JOB = "聖騎士"
LEGACY_NAME = "神聖庇護"
LEGACY_DESCRIPTION = "免疫怪物下一次攻擊。"

TALENTS = {
    "holy_might": {
        "tier": 1, "side": 0, "max": 3, "name": "聖裁專精",
        "desc": "聖裁傷害提升。",
        "details": ("1點：聖裁傷害提高為 120%。", "2點：聖裁傷害提高為 128%。", "3點：聖裁傷害提高為 136%。"),
    },
    "devotion": {
        "tier": 1, "side": 1, "max": 3, "name": "虔誠守護",
        "desc": "祝福護盾提升。",
        "details": ("1點：祝福護盾 +15%。", "2點：祝福護盾 +30%。", "3點：祝福護盾 +45%。"),
    },
    "judgment": {
        "tier": 2, "side": 0, "max": 3, "name": "審判",
        "desc": "解鎖強力攻擊招式。",
        "details": ("1點：解鎖審判，造成 180% 攻擊傷害並恢復 10% 最大血量，冷卻 3 回合。",
                    "2點：審判傷害提高為 230%。",
                    "3點：恢復提高為 15% 最大血量。"),
    },
    "sanctuary": {
        "tier": 2, "side": 1, "max": 3, "name": "聖域",
        "desc": "解鎖強力防禦招式。",
        "details": ("1點：解鎖聖域，獲得 160% 防禦的護盾並恢復 10% 最大血量，冷卻 3 回合。",
                    "2點：護盾提高為 210% 防禦。",
                    "3點：清除持續傷害。"),
    },
    "guardian_angel": {
        "tier": 3, "side": 0, "max": 3, "name": "守護天使",
        "desc": "解鎖保命效果。",
        "details": ("1點：每場戰鬥第一次致命傷保留 1 血。",
                    "2點：觸發時恢復 20% 最大血量。",
                    "3點：觸發時獲得 20% 最大血量的護盾。"),
    },
    "purify": {
        "tier": 3, "side": 1, "max": 3, "name": "淨化祈禱",
        "desc": "解鎖恢復招式。",
        "details": ("1點：解鎖淨化祈禱，恢復 25% 最大血量，冷卻 4 回合。",
                    "2點：同時清除持續傷害。",
                    "3點：冷卻降為 3 回合。"),
    },
    "divine_wrath": {
        "tier": 4, "side": 0, "max": 1, "name": "神聖怒火",
        "desc": "解鎖大絕招。",
        "details": ("1點：解鎖神聖怒火，造成 300% 攻擊傷害並恢復 30% 最大血量，本場戰鬥只能使用一次。",),
    },
}


def legacy_ready(game) -> bool:
    return game.player_attack_immunity_turns < 1


def legacy_active(game) -> bool:
    return game.player_attack_immunity_turns > 0


def activate_legacy(game) -> bool:
    if game.player_attack_immunity_turns > 0:
        return False
    game.player_attack_immunity_turns = 1
    game.log("你展開神聖庇護，將免疫怪物下一次攻擊。")
    return True


def smite_multiplier(game) -> float:
    """Front-load Smite's power while preserving its previous 136% cap."""
    return 1.12 + game.class_talent_rank("holy_might") * .08


def tooltip(game, action_id: str) -> str:
    if action_id == "smite":
        return f"{game.preview_skill_damage_text(smite_multiplier(game))}。"
    if action_id == "blessing":
        multiplier = 1.0 + game.class_talent_rank("devotion") * .15
        return f"獲得 {game.preview_skill_block(multiplier)} 點護盾。"
    if action_id == "judgment":
        rank = game.class_talent_rank("judgment")
        damage = 2.3 if rank >= 2 else 1.8
        heal = game.preview_max_hp_amount(.15 if rank >= 3 else .10)
        return f"{game.preview_skill_damage_text(damage)}並恢復 {heal} 點血量，冷卻 3 回合。"
    if action_id == "sanctuary":
        rank = game.class_talent_rank("sanctuary")
        block = game.preview_skill_block(2.1 if rank >= 2 else 1.6)
        heal = game.preview_max_hp_amount(.10)
        extra = "清除持續傷害。" if rank >= 3 else ""
        return f"獲得 {block} 點護盾並恢復 {heal} 點血量，冷卻 3 回合。{extra}"
    if action_id == "purify":
        cooldown = 3 if game.class_talent_rank("purify") >= 3 else 4
        extra = "清除持續傷害。" if game.class_talent_rank("purify") >= 2 else ""
        return f"恢復 {game.preview_max_hp_amount(.25)} 點血量，冷卻 {cooldown} 回合。{extra}"
    if action_id == "divine_wrath":
        return (f"{game.preview_skill_damage_text(3.0)}並恢復 "
                f"{game.preview_max_hp_amount(.30)} 點血量，本場戰鬥只能使用一次。")
    return ""


def action_slots(game):
    slots = [
        ("聖裁", "smite", True, (147, 92, 54), tooltip(game, "smite")),
        ("祝福", "blessing", True, (75, 104, 129), tooltip(game, "blessing")),
    ]
    for action_id, name, accent in (
        ("judgment", "審判", (170, 84, 48)),
        ("sanctuary", "聖域", (75, 104, 129)),
        ("purify", "淨化祈禱", (71, 127, 85)),
        ("divine_wrath", "神聖怒火", (150, 80, 55)),
    ):
        if game.class_talent_rank(action_id) > 0:
            slots.append((game.class_action_label(action_id, name), action_id,
                          game.class_action_ready(action_id), accent, tooltip(game, action_id)))
    return slots


def execute(game, action_id: str) -> None:
    if action_id == "smite":
        game.class_attack_skill(action_id, smite_multiplier(game))
    elif action_id == "blessing":
        if not game.enemy or game.battle_busy:
            return
        block = max(1, math.ceil(game.effective_player_defense() * (1.0 + game.class_talent_rank("devotion") * .15)))
        game.player_block += block
        game.log(f"祝福守護你，獲得 {block} 點護盾。")
        game.finish_class_action(action_id)
    elif action_id == "judgment":
        rank = game.class_talent_rank("judgment")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        game.heal_player(max(1, math.ceil(game.player.max_hp * (.15 if rank >= 3 else .10))))
        game.class_attack_skill(action_id, 2.3 if rank >= 2 else 1.8, 3)
    elif action_id == "sanctuary":
        rank = game.class_talent_rank("sanctuary")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        block = max(1, math.ceil(game.effective_player_defense() * (2.1 if rank >= 2 else 1.6)))
        game.player_block += block
        restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .10)))
        if rank >= 3:
            game.clear_player_dot()
        game.log(f"聖域展開，獲得 {block} 點護盾並恢復 {restored} 點血量。")
        game.class_skill_cooldowns[action_id] = 3
        game.finish_class_action(action_id)
    elif action_id == "purify":
        rank = game.class_talent_rank("purify")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .25)))
        if rank >= 2:
            game.clear_player_dot()
            game.clear_player_curse()
        game.log(f"淨化祈禱恢復 {restored} 點血量。")
        game.class_skill_cooldowns[action_id] = 3 if rank >= 3 else 4
        game.finish_class_action(action_id)
    elif action_id == "divine_wrath":
        if game.class_talent_rank("divine_wrath") < 1 or not game.enemy or game.battle_busy:
            return
        restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .30)))
        game.log(f"神聖怒火燃起，先恢復 {restored} 點血量。")
        game.class_attack_skill(action_id, 3.0, once=True)


def prevent_death(game) -> bool:
    rank = game.class_talent_rank("guardian_angel")
    if rank < 1 or getattr(game, "paladin_guardian_used", False) or game.player.hp > 0:
        return False
    game.paladin_guardian_used = True
    game.player.hp = 1
    if rank >= 2:
        restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .20)))
        game.log(f"守護天使保住了你，恢復 {restored} 點血量。")
    else:
        game.log("守護天使保住了你，生命保留 1 點。")
    if rank >= 3:
        block = max(1, math.ceil(game.player.max_hp * .20))
        game.player_block += block
        game.log(f"守護天使賜予 {block} 點護盾。")
    return True
