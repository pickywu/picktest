"""SoundManager lifecycle tests using a pure-Python Arcade audio stub."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
import warnings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeSound:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)


class FakePlayer:
    def __init__(self) -> None:
        self.playing = True


class FakeArcade(types.ModuleType):
    Sound = FakeSound

    def __init__(self) -> None:
        super().__init__("arcade")
        self.reset()

    def reset(self) -> None:
        self.load_calls: list[Path] = []
        self.play_calls: list[dict[str, object]] = []
        self.stop_calls: list[FakePlayer] = []
        self.failed_filenames: set[str] = set()

    def load_sound(self, path: str | Path, *, streaming: bool) -> FakeSound:
        selected = Path(path)
        self.load_calls.append(selected)
        if selected.name in self.failed_filenames:
            raise RuntimeError("stub decoder failure")
        return FakeSound(selected)

    def play_sound(self, sound: FakeSound, **options: object) -> FakePlayer:
        player = FakePlayer()
        self.play_calls.append({"sound": sound, "player": player, **options})
        return player

    def stop_sound(self, player: FakePlayer) -> None:
        player.playing = False
        self.stop_calls.append(player)

    @staticmethod
    def is_sound_playing(player: FakePlayer) -> bool:
        return player.playing


_ORIGINAL_ARCADE = sys.modules.get("arcade")
_ORIGINAL_SOUND_MANAGER = sys.modules.get("sound_manager")

FAKE_ARCADE = FakeArcade()
sound_manager = None


def setUpModule() -> None:
    global sound_manager
    sys.modules["arcade"] = FAKE_ARCADE
    sys.modules.pop("sound_manager", None)
    sound_manager = importlib.import_module("sound_manager")


def tearDownModule() -> None:
    if _ORIGINAL_ARCADE is None:
        sys.modules.pop("arcade", None)
    else:
        sys.modules["arcade"] = _ORIGINAL_ARCADE

    if _ORIGINAL_SOUND_MANAGER is None:
        sys.modules.pop("sound_manager", None)
    else:
        sys.modules["sound_manager"] = _ORIGINAL_SOUND_MANAGER


class SoundManagerLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        FAKE_ARCADE.reset()
        self.temporary = tempfile.TemporaryDirectory()
        self.sound_dir = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_files(self, *names: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for name in names:
            filename = f"{name}.wav"
            (self.sound_dir / filename).write_bytes(b"stub")
            files[name] = filename
        return files

    def manager(self, *names: str, **options: object) -> sound_manager.SoundManager:
        return sound_manager.SoundManager(
            sound_dir=self.sound_dir,
            sound_files=self.create_files(*names),
            sound_aliases={},
            sound_groups={},
            warmup_groups={},
            **options,
        )

    def test_iter_warmup_is_lazy_and_group_preload_is_explicit(self) -> None:
        manager = self.manager("sword_swing", "sword_hit", preload=False)
        manager.warmup_groups["combat"] = ("sword_swing", "sword_hit")

        warmup = manager.iter_warmup("combat")
        self.assertEqual(FAKE_ARCADE.load_calls, [])
        self.assertEqual(next(warmup), ("sword_swing", True))
        self.assertEqual(len(FAKE_ARCADE.load_calls), 1)
        self.assertEqual(next(warmup), ("sword_hit", True))
        self.assertEqual(manager.loaded_names, ("sword_swing", "sword_hit"))

        # Already-warm cues do not decode twice.
        self.assertEqual(manager.preload_group("combat"), ("sword_swing", "sword_hit"))
        self.assertEqual(len(FAKE_ARCADE.load_calls), 2)

    def test_failed_load_is_negative_cached_until_explicit_retry(self) -> None:
        manager = self.manager("sword_hit", preload=False)
        FAKE_ARCADE.failed_filenames.add("sword_hit.wav")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertIsNone(manager.play("sword_hit"))
            self.assertIsNone(manager.play("sword_hit"))
        self.assertEqual(len(FAKE_ARCADE.load_calls), 1)
        self.assertEqual(manager.failed_names, ("sword_hit",))
        self.assertEqual(FAKE_ARCADE.play_calls, [])

        FAKE_ARCADE.failed_filenames.clear()
        self.assertEqual(manager.retry_failed(), ("sword_hit",))
        self.assertEqual(len(FAKE_ARCADE.load_calls), 2)
        self.assertIsNotNone(manager.play("sword_hit", vary=False))

    def test_reload_all_retries_failed_preloads(self) -> None:
        FAKE_ARCADE.failed_filenames.add("curse.wav")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            manager = self.manager("curse", preload=True)
        self.assertEqual(manager.failed_names, ("curse",))

        FAKE_ARCADE.failed_filenames.clear()
        manager.reload_all()
        self.assertEqual(manager.failed_names, ())
        self.assertEqual(manager.loaded_names, ("curse",))

    def test_prune_forgets_finished_player_without_stopping_live_audio(self) -> None:
        manager = self.manager("ui_click", preload=True)
        first = manager.play("ui_click", vary=False)
        second = manager.play("ui_click", vary=False)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        first.playing = False

        self.assertEqual(manager.prune_finished_players(), 1)
        self.assertEqual(manager.active_player_count, 1)
        self.assertEqual(FAKE_ARCADE.stop_calls, [])
        self.assertTrue(second.playing)

    def test_soft_voice_limits_never_interrupt_critical_cues(self) -> None:
        manager = self.manager(
            "ui_click", "critical", preload=True,
            max_active_players=1, max_players_per_sound=1,
        )
        first = manager.play("ui_click", vary=False)
        self.assertIsNotNone(first)
        self.assertIsNone(manager.play("ui_click", vary=False))
        self.assertEqual(manager.dropped_voice_count, 1)

        critical = manager.play("critical", vary=False)
        self.assertIsNotNone(critical)
        self.assertEqual(manager.active_player_count, 2)
        self.assertEqual(FAKE_ARCADE.stop_calls, [])
        self.assertTrue(first.playing)
        self.assertTrue(critical.playing)

    def test_play_keeps_existing_pitch_variation_contract(self) -> None:
        manager = self.manager("sword_swing", preload=True, random_seed=7)
        manager.play("sword_swing", speed=1.2, vary=True)
        varied_speed = float(FAKE_ARCADE.play_calls[-1]["speed"])
        self.assertGreaterEqual(varied_speed, 1.2 * .94)
        self.assertLessEqual(varied_speed, 1.2 * 1.055)

        manager.play("sword_swing", speed=1.2, vary=False)
        self.assertEqual(FAKE_ARCADE.play_calls[-1]["speed"], 1.2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
