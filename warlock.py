import math


JOB = "術士"
LEGACY_NAME = "靈魂汲取"
LEGACY_DESCRIPTION = "施加腐蝕並恢復生命。"

TALENTS = {
    "corruption_mastery": {
        "tier": 1, "side": 0, "max": 3, "name": "腐蝕專精",
        "desc": "腐蝕箭的持續傷害提升。",
        "details": ("1點：腐蝕每回合傷害提高為 35% 攻擊。",
                    "2點：腐蝕每回合傷害提高為 40% 攻擊。",
                    "3點：腐蝕持續時間 +1 回合。"),
    },
    "dark_ward": {
        "tier": 1, "side": 1, "max": 3, "name": "暗影護盾",
        "desc": "暗影護符護盾提升。",
        "details": ("1點：暗影護符護盾 +15%。",
                    "2點：暗影護符護盾 +30%。",
                    "3點：暗影護符護盾 +45%。"),
    },
    "agony": {
        "tier": 2, "side": 0, "max": 3, "name": "痛苦詛咒",
        "desc": "解鎖可疊層的痛苦詛咒。",
        "details": ("1點：施加 3 回合痛苦，每層每回合 22% 攻擊傷害，最多 3 層，冷卻 3 回合。",
                    "2點：每層傷害提高為 26% 攻擊。",
                    "3點：冷卻降為 2 回合。"),
    },
    "life_tap": {
        "tier": 2, "side": 1, "max": 3, "name": "生命轉化",
        "desc": "犧牲血量換取護盾與詛咒強化。",
        "details": ("1點：消耗 10% 目前血量，獲得 160% 防禦護盾，冷卻 3 回合。",
                    "2點：若敵人有持續傷害，額外恢復 10% 最大血量。",
                    "3點：同時延長敵人的腐蝕與痛苦 1 回合。"),
    },
    "soul_link": {
        "tier": 3, "side": 0, "max": 3, "name": "靈魂連結",
        "desc": "持續傷害會回復生命。",
        "details": ("1點：持續傷害造成傷害時，恢復該傷害 20% 的血量。",
                    "2點：恢復提高為 30%。",
                    "3點：每場戰鬥第一次致命傷保留 1 血。"),
    },
    "hex": {
        "tier": 3, "side": 1, "max": 3, "name": "衰弱咒印",
        "desc": "降低敵方攻勢。",
        "details": ("1點：使敵人下一次攻擊傷害降低 35%，冷卻 4 回合。",
                    "2點：降低提高為 50%。",
                    "3點：冷卻降為 3 回合。"),
    },
    "doom": {
        "tier": 4, "side": 0, "max": 1, "name": "末日降臨",
        "desc": "解鎖大絕招。",
        "details": ("1點：造成 200% 攻擊傷害，並施加 2 回合末日印記，倒數結束造成 250% 攻擊傷害；本場戰鬥只能使用一次。",),
    },
}


def legacy_ready(game) -> bool:
    return bool(game.enemy)


def legacy_active(game) -> bool:
    return False


def activate_legacy(game) -> bool:
    if not game.enemy:
        return False
    damage = max(1, math.ceil(game.effective_player_attack() * .40))
    game.apply_enemy_corrosion(game.enemy, damage, 2)
    restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .15)))
    game.show_player_heal(restored)
    game.log(f"你汲取靈魂，恢復 {restored} 點血量。")
    return True


def tooltip(game, action_id: str) -> str:
    if action_id == "corruption_bolt":
        rank = game.class_talent_rank("corruption_mastery")
        dot = 40 if rank >= 2 else (35 if rank >= 1 else 30)
        turns = 3 if rank >= 3 else 2
        return f"造成 100% 攻擊傷害，並施加 {turns} 回合腐蝕，每回合 {dot}% 攻擊傷害。"
    if action_id == "dark_charm":
        multiplier = int((1.0 + game.class_talent_rank("dark_ward") * .15) * 100)
        return f"獲得 {multiplier}% 防禦護盾；若敵人有持續傷害，恢復 8% 最大血量。"
    if action_id == "agony":
        rank = game.class_talent_rank("agony")
        dot = 26 if rank >= 2 else 22
        cooldown = 2 if rank >= 3 else 3
        return f"施加 3 回合痛苦，每層每回合 {dot}% 攻擊傷害，最多 3 層，冷卻 {cooldown} 回合。"
    if action_id == "life_tap":
        rank = game.class_talent_rank("life_tap")
        extra = "若敵人有持續傷害，恢復 10% 最大血量。" if rank >= 2 else ""
        extend = "並延長腐蝕與痛苦 1 回合。" if rank >= 3 else ""
        return f"消耗 10% 目前血量，獲得 160% 防禦護盾，冷卻 3 回合。{extra}{extend}"
    if action_id == "hex":
        rank = game.class_talent_rank("hex")
        reduction = 50 if rank >= 2 else 35
        cooldown = 3 if rank >= 3 else 4
        return f"敵人下一次攻擊傷害降低 {reduction}%，冷卻 {cooldown} 回合。"
    if action_id == "doom":
        return "造成 200% 攻擊傷害，施加 2 回合末日印記；倒數結束造成 250% 攻擊傷害，本場戰鬥只能使用一次。"
    return ""


def action_slots(game):
    slots = [
        ("腐蝕箭", "corruption_bolt", True, (112, 82, 48), tooltip(game, "corruption_bolt")),
        ("暗影護符", "dark_charm", True, (75, 104, 129), tooltip(game, "dark_charm")),
    ]
    for action_id, name, accent in (
        ("agony", "痛苦詛咒", (123, 74, 128)),
        ("life_tap", "生命轉化", (132, 50, 55)),
        ("hex", "衰弱咒印", (102, 86, 151)),
        ("doom", "末日降臨", (150, 80, 55)),
    ):
        if game.class_talent_rank(action_id) > 0:
            slots.append((game.class_action_label(action_id, name), action_id,
                          game.class_action_ready(action_id), accent, tooltip(game, action_id)))
    return slots


def _target_hidden(game, action_id: str | None = None) -> bool:
    if game.enemy_stealth_turns <= 0:
        return False
    game.enemy_stealth_turns -= 1
    game.log(f"{game.enemy.name}處於隱身，這次法術落空。")
    if action_id:
        game.finish_class_action(action_id)
    else:
        game.queue_turn("enemy")
    return True


def execute(game, action_id: str) -> None:
    if action_id == "corruption_bolt":
        if not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        if _target_hidden(game, action_id):
            return
        rank = game.class_talent_rank("corruption_mastery")
        dot_rate = .40 if rank >= 2 else (.35 if rank >= 1 else .30)
        turns = 3 if rank >= 3 else 2
        game.apply_enemy_corrosion(game.enemy, max(1, math.ceil(game.effective_player_attack() * dot_rate)), turns)
        game.class_attack_skill(action_id, 1.0)
    elif action_id == "dark_charm":
        if not game.enemy or game.battle_busy:
            return
        rank = game.class_talent_rank("dark_ward")
        block = max(1, math.ceil(game.effective_player_defense() * (1.0 + rank * .15)))
        game.player_block += block
        if game.enemy_has_dot():
            restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .08)))
            game.show_player_heal(restored)
        game.log(f"暗影護符張開，獲得 {block} 點護盾。")
        game.finish_class_action(action_id)
    elif action_id == "agony":
        rank = game.class_talent_rank("agony")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        if _target_hidden(game, action_id):
            return
        dot_rate = .26 if rank >= 2 else .22
        game.apply_enemy_agony(game.enemy, max(1, math.ceil(game.effective_player_attack() * dot_rate)), 3)
        game.class_skill_cooldowns[action_id] = 2 if rank >= 3 else 3
        game.finish_class_action(action_id)
    elif action_id == "life_tap":
        rank = game.class_talent_rank("life_tap")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        cost = min(max(1, math.ceil(game.player.hp * .10)), max(0, game.player.hp - 1))
        game.player.hp -= cost
        block = max(1, math.ceil(game.effective_player_defense() * 1.6))
        game.player_block += block
        if rank >= 2 and game.enemy_has_dot():
            restored = game.heal_player(max(1, math.ceil(game.player.max_hp * .10)))
            game.show_player_heal(restored)
        if rank >= 3:
            game.extend_enemy_dots(game.enemy, 1)
        game.log(f"生命轉化消耗 {cost} 血量，獲得 {block} 點護盾。")
        game.class_skill_cooldowns[action_id] = 3
        game.finish_class_action(action_id)
    elif action_id == "hex":
        rank = game.class_talent_rank("hex")
        if rank < 1 or not game.enemy or game.battle_busy or not game.class_action_ready(action_id):
            return
        if _target_hidden(game, action_id):
            return
        game.weaken_enemy_attack(game.enemy, .50 if rank >= 2 else .35)
        game.class_skill_cooldowns[action_id] = 3 if rank >= 3 else 4
        game.finish_class_action(action_id)
    elif action_id == "doom":
        if (game.class_talent_rank("doom") < 1 or not game.enemy or game.battle_busy
                or not game.class_action_ready(action_id)):
            return
        if _target_hidden(game, action_id):
            return
        game.apply_enemy_doom(game.enemy, max(1, math.ceil(game.effective_player_attack() * 2.5)), 2)
        game.class_attack_skill(action_id, 2.0, once=True)


def prevent_death(game) -> bool:
    rank = game.class_talent_rank("soul_link")
    if rank < 3 or getattr(game, "warlock_soul_link_used", False) or game.player.hp > 0:
        return False
    game.warlock_soul_link_used = True
    game.player.hp = 1
    game.log("靈魂連結保住了你，生命保留 1 點。")
    return True
