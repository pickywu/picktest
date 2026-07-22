"""Render representative English scenes and fail on CJK or bounded-text overflow.

This is a development audit, not part of the packaged game.  It deliberately
uses a hidden Arcade window, records every string sent through the shared text
boundary, and saves screenshots for human inspection.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import arcade  # noqa: E402

from localization import set_locale  # noqa: E402
from rpg import RPGWindow, Scene, make_player_portrait  # noqa: E402


CJK = re.compile(r"[\u3400-\u9fff]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build" / "ui-audit-en"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    set_locale("EN")
    game = RPGWindow(visible=False)
    game.locale = "EN"
    set_locale("EN")
    game._load_title_background()
    game.show_view(game.game_view)
    game.scene_transition_elapsed = game.scene_transition_duration

    captured: list[str] = []
    original_text = game.text

    def traced_text(value: str, *text_args: Any, **text_kwargs: Any) -> None:
        captured.append(game.display_text(value))
        original_text(value, *text_args, **text_kwargs)

    game.text = traced_text  # type: ignore[method-assign]
    failures: list[str] = []
    summaries: list[str] = []

    def render(
        name: str,
        setup: Callable[[], None] | None = None,
        *,
        screenshot: bool = True,
        hover_match: Callable[[Any], bool] | None = None,
    ) -> None:
        captured.clear()
        if setup is not None:
            setup()
        game.scene_transition_elapsed = game.scene_transition_duration
        game.configure_buttons()
        game.hovered = (
            next((button for button in game.buttons if hover_match(button)), None)
            if hover_match is not None else None
        )
        game.switch_to()
        game.on_draw()
        residual = sorted({text for text in captured if CJK.search(text)})
        warnings = list(game.ui_layout_warnings)
        truncations = list(game.ui_truncations)
        summaries.append(
            f"{name}: strings={len(captured)} residual={len(residual)} "
            f"overflow={len(warnings)} truncation={len(truncations)}"
        )
        failures.extend(f"{name}: CJK: {text}" for text in residual)
        failures.extend(
            f"{name}: overflow: {text} ({width:.1f}x{height:.1f})"
            for text, width, height in warnings
        )
        failures.extend(
            f"{name}: truncation: {text} ({reason})"
            for text, reason in truncations
        )
        if screenshot:
            arcade.get_image(0, 0, game.width, game.height).save(
                args.output / f"{name}.png"
            )
        game.flip()

    try:
        render("title", lambda: setattr(game, "scene", Scene.TITLE))
        render("settings", lambda: setattr(game, "scene", Scene.SETTINGS))
        for step in range(4):
            def setup_creation(current_step: int = step) -> None:
                game.scene = Scene.CREATION
                game.creation_step = current_step
                game.name_input = "Alexandria Stormwarden"

            render(f"creation_{step + 1}", setup_creation)

        def setup_adventure() -> None:
            game.scene = Scene.ADVENTURE
            game.player.name = "Alexandria Stormwarden"
            game.player.lv = 12
            game.player.gold = 99999
            game.messages = list(game.JOURNEY_LORE[2])[-6:]

        render("adventure", setup_adventure)

        for job in game.CLASS_PROFILES:
            def setup_talent(current_job: str = job) -> None:
                setup_adventure()
                game.player.job = current_job
                game.player.talent_points = 10
                game.scene = Scene.TALENT

            render(f"talent_{job}", setup_talent)
            # CLASS_PROFILES stores class modules; ask the game for the
            # normalized talent definitions after setup_talent selected the
            # current job.
            for talent_id in game.class_talent_defs():
                render(
                    f"talent_{job}_{talent_id}_tooltip",
                    setup_talent,
                    screenshot=talent_id in {
                        "weapon_mastery", "meteor", "divine_wrath",
                        "assassinate", "doom",
                    },
                    hover_match=lambda button, current=talent_id: (
                        button.talent_id == current
                    ),
                )

        def setup_subclass() -> None:
            setup_adventure()
            game.player.job = "戰士"
            game.player.lv = 10
            game.scene = Scene.SUBCLASS

        render("subclass", setup_subclass)

        def setup_campfire() -> None:
            setup_adventure()
            game.open_campfire()

        render("campfire", setup_campfire)

        def setup_shop() -> None:
            setup_adventure()
            game.open_black_market()

        render("shop", setup_shop)

        for event_number, event in enumerate(game.EVENT_DECK, start=1):
            event_copy = [event["intro"], *event["positive"], *event["negative"]]
            for message_index, message in enumerate(event_copy):
                def setup_event(
                    number: int = event_number,
                    current_message: str = message,
                    resolved: bool = message_index > 0,
                ) -> None:
                    setup_adventure()
                    game.scene = Scene.EVENT
                    game.event_number = number
                    game.event_title = "隨機事件"
                    game.event_options = ("靠近查看", "保持距離")
                    game.event_messages = [current_message]
                    game.event_resolved = resolved

                render(
                    f"event_{event_number:02d}_{message_index + 1}",
                    setup_event,
                    screenshot=(event_number in {1, 5, 10, 15, 20}
                                and message_index == 0),
                )

        def setup_battle() -> None:
            setup_adventure()
            game.player.lv = 12
            game.difficulty = 3
            game.hero_portrait = make_player_portrait(
                game.player.sex, game.player.race, game.player.job,
                game.player.lv, "idle",
            )
            game.hero_attack_portrait = make_player_portrait(
                game.player.sex, game.player.race, game.player.job,
                game.player.lv, "attack",
            )
            game.start_battle()
            game.tutorial_tip = ""

        setup_battle()
        for intent in game.enemy_intent_pool(game.enemy):
            game.enemy.intent = intent
            game.hovered_enemy_intent_index = 0
            render(f"battle_{intent}", screenshot=intent in {
                "attack", "heavy_blow", "lifedrain", "curse"
            })
        game.hovered_enemy_intent_index = None
        game.player_dot_damage = 3
        game.player_dot_turns = 3
        game.player_dot_stacks = 2
        game.player_curse_turns = 2
        game.player_attack_immunity_turns = 1
        game.player_stun_immunity_turns = 1
        game.potion_iron_skin_turns = 1
        game.stealth_turns = 1
        game.warrior_attack_bonus = 4
        game.warrior_blood_regen = 3
        game.warrior_blood_regen_turns = 2
        game.forced_critical = True
        render("battle_player_statuses")

        game.player_dot_damage = 0
        game.player_dot_turns = 0
        game.player_dot_stacks = 0
        game.player_curse_turns = 0
        game.player_attack_immunity_turns = 0
        game.player_stun_immunity_turns = 0
        game.potion_iron_skin_turns = 0
        game.stealth_turns = 0
        game.warrior_attack_bonus = 0
        game.warrior_blood_regen = 0
        game.warrior_blood_regen_turns = 0
        game.forced_critical = False
        audited_enemy = game.enemies[0]
        audited_enemy.corrosion_damage = 3
        audited_enemy.corrosion_turns = 2
        audited_enemy.agony_damage = 2
        audited_enemy.agony_turns = 3
        audited_enemy.agony_stacks = 2
        audited_enemy.doom_damage = 18
        audited_enemy.doom_turns = 2
        audited_enemy.weak_turns = 2
        audited_enemy.immune_turns = 1
        audited_enemy.reflect_turns = 1
        audited_enemy.heavy_blow_charged = True
        audited_enemy.berserk_stacks = 2
        audited_enemy.bulwark_stacks = 2
        render("battle_enemy_statuses")
        game.hovered_enemy_intent_index = None
        game.battle_log_expanded = True
        game.combat_messages = [
            "你掌握先機，先取得行動機會。",
            "戰局變體「貪婪」：敵人攻擊提高 15%，擊敗後金幣加倍。",
            f"{game.enemy.name}開始蓄力，下一次行動將施放重擊。",
            f"{game.enemy.name}汲取生命，回復 18 點生命。",
        ]
        render("battle_log")
        game.battle_log_expanded = False

        def setup_reward() -> None:
            setup_adventure()
            game.pending_reward_gold = 12345
            game.reward_level_before = 11
            game.reward_level_after = 12
            game.scene = Scene.REWARD

        render("reward", setup_reward)

        def setup_save() -> None:
            game.scene = Scene.SAVE_MENU
            game.save_menu_mode = "load"

        render("save_menu", setup_save)

        for victory in (False, True):
            def setup_end(won: bool = victory) -> None:
                setup_adventure()
                game.victory = won
                game.final_enemy_name = "終焉之主"
                game.scene = Scene.END
                game.end_record_open = True

            render("victory" if victory else "death", setup_end)
    finally:
        game.close()

    report = "\n".join([*summaries, "", *failures]) + "\n"
    (args.output / "report.txt").write_text(report, encoding="utf-8")
    print("\n".join(summaries))
    if failures:
        print(f"FAILED: {len(failures)} issue(s); see {args.output / 'report.txt'}")
        raise SystemExit(1)
    print(f"PASS: screenshots and report written to {args.output}")


if __name__ == "__main__":
    main()
