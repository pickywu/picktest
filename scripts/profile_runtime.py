"""Repeatable hidden-window frame-time smoke test for release builds.

This deliberately measures the cold startup and first combat impact that are
easy to miss in average-FPS counters.  It does not alter saves or game state.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rpg import RPGWindow  # noqa: E402


def timed(action):
    started = perf_counter()
    result = action()
    return perf_counter() - started, result


def main() -> int:
    metrics: dict[str, float | int | str] = {}
    duration, window = timed(lambda: RPGWindow(visible=False))
    metrics["window_constructor_ms"] = duration * 1_000
    try:
        loading = window.current_view
        duration, _ = timed(loading.on_draw)
        metrics["loading_first_draw_ms"] = duration * 1_000

        # The first update creates persistent text objects after the dark
        # texture-free frame has already been presented.
        duration, _ = timed(lambda: loading.on_update(1 / 60))
        metrics["loading_label_build_ms"] = duration * 1_000
        duration, _ = timed(loading.on_draw)
        metrics["loading_second_draw_ms"] = duration * 1_000

        bootstrap_started = perf_counter()
        bootstrap_steps = 0
        while window.current_view is loading and bootstrap_steps < 2_000:
            loading.on_update(1 / 60)
            bootstrap_steps += 1
        metrics["bootstrap_ms"] = (perf_counter() - bootstrap_started) * 1_000
        metrics["bootstrap_steps"] = bootstrap_steps
        metrics["view_after_bootstrap"] = type(window.current_view).__name__

        duration, _ = timed(window.on_draw)
        metrics["title_first_draw_ms"] = duration * 1_000
        duration, _ = timed(window.on_draw)
        metrics["title_warm_draw_ms"] = duration * 1_000

        warmup_started = perf_counter()
        warmup_steps = 0
        warmup_draws: list[float] = []
        while not window.asset_warmup.idle and warmup_steps < 2_000:
            window.asset_warmup.step(12.0)
            duration, _ = timed(window.on_draw)
            warmup_draws.append(duration * 1_000)
            warmup_steps += 1
        metrics["idle_warmup_ms"] = (perf_counter() - warmup_started) * 1_000
        metrics["idle_warmup_steps"] = warmup_steps
        metrics["idle_warmup_max_draw_ms"] = max(warmup_draws, default=0.0)

        window.name_input = "Profiler"
        window.selected_race = "人類"
        window.selected_job = "戰士"
        window.tutorial_seen.add(window.FIRST_BATTLE_TUTORIAL_KEY)
        duration, _ = timed(lambda: window.choose_difficulty(1))
        metrics["character_assets_ms"] = duration * 1_000
        duration, _ = timed(window.start_battle)
        metrics["battle_setup_ms"] = duration * 1_000
        duration, _ = timed(window.on_draw)
        metrics["battle_first_draw_ms"] = duration * 1_000
        duration, _ = timed(window.on_draw)
        metrics["battle_warm_draw_ms"] = duration * 1_000

        duration, _ = timed(window.normal_attack)
        metrics["attack_input_ms"] = duration * 1_000
        windup_draws: list[float] = []
        for _ in range(9):
            window.on_update(1 / 60)
            duration, _ = timed(window.on_draw)
            windup_draws.append(duration * 1_000)
        metrics["attack_windup_max_draw_ms"] = max(windup_draws)
        duration, _ = timed(lambda: window.on_update(1 / 30))
        metrics["attack_impact_update_ms"] = duration * 1_000
        duration, _ = timed(window.on_draw)
        metrics["attack_impact_draw_ms"] = duration * 1_000
        metrics["hit_stop_ms"] = window.hit_stop_remaining * 1_000
        metrics["floating_labels"] = len(window.floating_damage)
        metrics["floating_pool_slots"] = len(window._floating_label_pool)
    finally:
        window.close()

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
