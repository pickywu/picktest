from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

import mage
import paladin
import rogue
import warlock
import warrior
from localization import LOCALIZATION_DIR, translate

# The authored English source strings now live in the editable localization
# folder; load them straight from the JSON catalog the game ships.
EN_CATALOG = json.loads((LOCALIZATION_DIR / "en.json").read_text(encoding="utf-8"))


_CJK = re.compile(r"[\u3400-\u9fff]")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_CLASS_MODULES = (mage, warrior, paladin, rogue, warlock)

# Use real Traditional-Chinese game terms for semantic placeholders.  Numeric
# stand-ins would hide the exact regression this test is intended to catch:
# a translated English sentence retaining a Chinese enemy, class, skill, stage,
# status, or event-choice name after an f-string has been rendered.
_SAMPLE_VALUES = {
    "after": "2",
    "amount": "17",
    "block": "23",
    "bonus": "攻擊 +5",
    "choice": "搬開貨箱",
    "cooldown": "3",
    "count": "4",
    "critical": "41",
    "damage": "27",
    "description": "消耗目前血量換取追加傷害。",
    "dwarf_bonus": "；尋金本能已將金幣加倍。",
    "effects": "腐蝕、痛苦",
    "enemy": "赤囊沼澤蛙",
    "first": "赤囊沼澤蛙",
    "gold": "90",
    "heal": "12",
    "healing": "8",
    "job": "戰士",
    "label": "腐蝕",
    "level": "第12關",
    "name": "Aster",
    "points": "2",
    "prefix": "暴擊！",
    "price": "70",
    "race": "矮人",
    "second": "黑鐵石像鬼",
    "skill": "血祭強襲",
    "slot": "2",
    "source": "痛苦詛咒",
    "stacks": "2",
    "stage": "灰霧荒野",
    "state": "開",
    "status": "腐蝕",
    "target": "黑鐵石像鬼",
    "talent": "尋金本能",
    "turns": "3",
    "type": "血量",
}


def _assert_english(source: str, context: str) -> None:
    translated = translate(source, "EN")
    assert not _CJK.search(translated), (
        f"{context} retained Traditional Chinese after EN translation:\n"
        f"source={source!r}\ntranslated={translated!r}"
    )


def _render_template(source: str) -> str:
    return _PLACEHOLDER.sub(
        lambda match: _SAMPLE_VALUES.get(match.group(1), "7"), source
    )


def test_all_authored_dynamic_templates_render_without_chinese() -> None:
    for source in EN_CATALOG:
        if _PLACEHOLDER.search(source):
            _assert_english(
                _render_template(source), f"en template {source!r}"
            )


def test_all_class_profile_copy_translates_without_chinese() -> None:
    for module in _CLASS_MODULES:
        for field in ("JOB", "LEGACY_NAME", "LEGACY_DESCRIPTION"):
            _assert_english(getattr(module, field), f"{module.__name__}.{field}")
        for talent_id, talent in module.TALENTS.items():
            for field in ("name", "desc"):
                _assert_english(
                    str(talent[field]), f"{module.__name__}.{talent_id}.{field}"
                )
            for rank, detail in enumerate(talent.get("details", ()), start=1):
                _assert_english(
                    str(detail),
                    f"{module.__name__}.{talent_id}.details[{rank}]",
                )


class _TooltipGame:
    def __init__(self, rank: int, *, enemy_block: int = 0) -> None:
        self._rank = rank
        self.enemy_block = enemy_block
        self.player = SimpleNamespace(job="術士", lv=12, hp=80, max_hp=100)

    def class_talent_rank(self, _talent_id: str) -> int:
        return self._rank

    @staticmethod
    def preview_skill_damage_text(_multiplier: float, critical: bool = False) -> str:
        return "造成 27 點傷害（必定暴擊）" if critical else "造成 27 點傷害"

    @staticmethod
    def preview_skill_block(_multiplier: float) -> int:
        return 19

    @staticmethod
    def preview_max_hp_amount(rate: float) -> int:
        return max(1, round(100 * rate))

    @staticmethod
    def effective_player_attack() -> int:
        return 24


def test_every_class_tooltip_variant_translates_without_chinese() -> None:
    action_ids = {
        mage: ("fireball", "ice_armor", "pyroblast", "ice_wall", "ice_barrier", "meteor"),
        warrior: ("slash", "guard", "cleave", "fortify", "counter", "bladestorm"),
        paladin: ("smite", "blessing", "judgment", "sanctuary", "purify", "divine_wrath"),
        rogue: ("stab", "smokescreen", "backstab", "smoke_bomb", "vanish", "shadowstep", "assassinate"),
        warlock: ("corruption_bolt", "dark_charm", "agony", "life_tap", "hex", "doom"),
    }
    for module, module_actions in action_ids.items():
        for rank in range(4):
            for enemy_block in (0, 10):
                game = _TooltipGame(rank, enemy_block=enemy_block)
                for action_id in module_actions:
                    source = module.tooltip(game, action_id)
                    _assert_english(
                        source,
                        f"{module.__name__}.tooltip({action_id!r}, rank={rank}, "
                        f"enemy_block={enemy_block})",
                    )


def test_dynamic_legacy_descriptions_translate_without_chinese() -> None:
    game = _TooltipGame(3)
    _assert_english(warrior.legacy_description(game), "warrior.legacy_description")
    _assert_english(warlock.legacy_description(game), "warlock.legacy_description")


def test_class_combat_log_variants_translate_without_chinese() -> None:
    messages = (
        "你施放命運改寫，目標意圖變成：巨獸撕咬｜造成 17 傷害。",
        "你施放冰甲術，獲得 19 點護盾。",
        "冰牆術驅散了持續傷害。",
        "你施放寒冰屏障，免疫下一次敵方攻擊。",
        "法力護盾保住了你，生命保留 1 點。",
        "你發動血祭強襲，犧牲 20 點血量；下一次攻擊追加 20 傷害。",
        "祭出的鮮血將在接下來 2 回合，每回合回流 6 點血量。",
        "你架起鋼鐵壁壘，獲得 31 點護盾。",
        "最後防線保住了你，生命保留 1 點。",
        "你的反擊意志凝聚，下次攻擊追加 25 傷害。",
        "你展開神聖庇護，將免疫怪物下一次攻擊。",
        "聖域展開，獲得 28 點護盾並恢復 10 點血量。",
        "守護天使保住了你，恢復 20 點血量。",
        "你使出悶棍擊暈怪物，它下一回合無法行動。",
        "煙霧彈遮蔽戰場，獲得 24 點護盾並進入隱身。",
        "你消失在陰影中，清除持續傷害並獲得 20 點護盾。",
        "你汲取靈魂，恢復 15 點血量。",
        "暗影護符張開，獲得 18 點護盾。",
        "生命轉化消耗 8 血量，獲得 25 點護盾。",
        "靈魂連結保住了你，生命保留 1 點。",
    )
    for message in messages:
        _assert_english(message, "class combat log")


def test_composite_character_headers_translate_nested_level_labels() -> None:
    # These strings are assembled by drawing paths after level_label() has
    # already rendered "第N關".  A template must translate the entire nested
    # level value; translating only race/class terms leaves a mixed-language
    # English HUD.
    headers = (
        "Aster　獸人・戰士　第12關",
        "獸人・戰士　第12關",
        "Aster｜獸人・戰士｜第12關",
    )
    for header in headers:
        _assert_english(header, "composite character header")


class DynamicEnglishTextTests(unittest.TestCase):
    """Expose the audit through the project's unittest discovery runner."""

    def test_authored_dynamic_templates(self) -> None:
        test_all_authored_dynamic_templates_render_without_chinese()

    def test_class_profile_copy(self) -> None:
        test_all_class_profile_copy_translates_without_chinese()

    def test_class_tooltip_variants(self) -> None:
        test_every_class_tooltip_variant_translates_without_chinese()

    def test_dynamic_legacy_descriptions(self) -> None:
        test_dynamic_legacy_descriptions_translate_without_chinese()

    def test_class_combat_log_variants(self) -> None:
        test_class_combat_log_variants_translate_without_chinese()

    def test_composite_character_headers(self) -> None:
        test_composite_character_headers_translate_nested_level_labels()

    def test_final_stage_label_is_not_duplicated(self) -> None:
        source = "最終關卡 第12關｜攻擊 10｜防禦 10｜暴擊 1%"
        translated = translate(source, "EN")
        self.assertNotIn("STAGE STAGE", translated)
        self.assertEqual(
            translated,
            "FINAL STAGE 12 | ATTACK 10 | DEFENSE 10 | CRITICAL 1%",
        )

    def test_single_rank_talent_tooltip_uses_authored_spacing(self) -> None:
        source = (
            "解鎖神聖怒火，造成 300% 攻擊傷害並恢復 30% 最大血量，"
            "本場戰鬥只能使用一次。"
        )
        translated = translate(source, "EN")
        self.assertNotIn("ATTACKdamage", translated)
        self.assertEqual(
            translated,
            "Unlock Divine Wrath. Deal 300% Attack damage and restore 30% "
            "Max HP. Usable once per battle.",
        )


if __name__ == "__main__":
    unittest.main()
