"""Arcade 短音效管理器。

整合到現有 ``arcade.Window`` 或 ``arcade.View`` 的最小範例::

    class GameWindow(arcade.Window):
        def __init__(self) -> None:
            super().__init__(1180, 720, "遊戲")
            self.sounds = SoundManager(master_volume=0.8)

        def on_key_press(self, symbol: int, modifiers: int) -> None:
            if symbol == arcade.key.SPACE:
                self.sounds.play("sword_swing", volume=0.9)
            elif symbol == arcade.key.M:
                self.sounds.toggle_mute()

``SoundManager`` 啟動時會預載所有短音效；播放時不會重新讀取檔案。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
import random
from typing import Any, Mapping
import warnings

import arcade


DEFAULT_SOUND_DIR = Path(__file__).resolve().parent / "assets" / "audio"
DEFAULT_SOUND_NAMES = (
    "ui_click", "ui_confirm", "ui_cancel", "coin", "hurt",
    "sword_swing", "sword_hit", "fireball", "ice_spell", "lightning",
    "meteor_fall", "level_up", "death", "shield", "shield_block",
    "dodge", "potion", "heal", "curse", "critical", "victory",
    "holy_cast", "shadow_step", "smoke_bomb", "battle_start", "boss_roar",
    "reward_open", "campfire", "map_advance",
)
DEFAULT_SOUND_FILES: dict[str, str] = {
    name: f"{name}.wav" for name in DEFAULT_SOUND_NAMES
}
DEFAULT_SOUND_GROUPS: dict[str, tuple[str, ...]] = {}
DEFAULT_WARMUP_GROUPS: dict[str, tuple[str, ...]] = {
    "ui": ("ui_click", "ui_confirm", "ui_cancel"),
    "combat": (
        "hurt", "sword_swing", "sword_hit", "shield", "shield_block",
        "dodge", "critical", "battle_start", "boss_roar",
    ),
    "magic": (
        "fireball", "ice_spell", "lightning", "meteor_fall", "curse",
        "holy_cast", "shadow_step", "smoke_bomb",
    ),
    "progression": (
        "coin", "level_up", "death", "victory", "reward_open",
        "campfire", "map_advance", "potion", "heal",
    ),
}
DEFAULT_SOUND_ALIASES: dict[str, str] = {
    "ui_click_2": "ui_click", "ui_click_3": "ui_click",
    "ui_error": "ui_cancel", "ui_panel_open": "ui_confirm",
    "ui_panel_close": "ui_cancel", "ui_page_turn": "ui_click",
    "ui_talent_unlock": "level_up",
    "coin_2": "coin", "coin_3": "coin", "jump": "dodge",
    "hurt_2": "hurt", "hurt_3": "hurt",
    "sword_swing_2": "sword_swing", "sword_swing_3": "sword_swing",
    "sword_hit_2": "sword_hit", "sword_hit_3": "sword_hit",
    "fireball_cast": "fireball", "fireball_impact": "fireball",
    "ice_cast": "ice_spell", "ice_shatter": "ice_spell",
    "lightning_cast": "lightning", "lightning_impact": "lightning",
    "explosion": "meteor_fall", "shield_break": "sword_hit",
    "curse_tick": "curse", "holy_impact": "holy_cast",
    "event_positive": "reward_open", "event_negative": "hurt",
    "shop_open": "coin", "boss_victory": "victory",
}
DEFAULT_PITCH_RANGES: dict[str, tuple[float, float]] = {
    "ui_click": (.975, 1.025),
    "coin": (.98, 1.045),
    "hurt": (.94, 1.045),
    "sword_swing": (.94, 1.055),
    "sword_hit": (.955, 1.035),
    "potion": (.975, 1.025),
    "shield_block": (.965, 1.025),
}
CRITICAL_SOUND_NAMES = frozenset({
    "battle_start", "boss_roar", "critical", "death", "hurt",
    "shield_block", "sword_hit", "victory",
})
DEFAULT_SOUND_PRIORITIES: dict[str, int] = {
    name: 100 for name in CRITICAL_SOUND_NAMES
}
DEFAULT_SOUND_PRIORITIES.update({
    "ui_click": 10, "ui_cancel": 20, "ui_confirm": 30,
    "coin": 30, "campfire": 35, "map_advance": 35,
})
CRITICAL_SOUND_PRIORITY = 100


def _clamp_volume(value: float) -> float:
    """把音量限制在 Arcade 接受的 0.0～1.0。"""
    return max(0.0, min(1.0, float(value)))


class SoundManager:
    """預載、播放、個別控制與停止 Arcade 短音效。"""

    def __init__(
        self,
        sound_dir: str | Path = DEFAULT_SOUND_DIR,
        master_volume: float = 1.0,
        sound_volumes: Mapping[str, float] | None = None,
        sound_files: Mapping[str, str] | None = None,
        sound_groups: Mapping[str, tuple[str, ...]] | None = None,
        sound_aliases: Mapping[str, str] | None = None,
        warmup_groups: Mapping[str, tuple[str, ...]] | None = None,
        sound_priorities: Mapping[str, int] | None = None,
        max_active_players: int = 24,
        max_players_per_sound: int = 6,
        random_seed: int = 20_260_719,
        preload: bool = True,
    ) -> None:
        self.sound_dir = Path(sound_dir)
        self.master_volume = _clamp_volume(master_volume)
        self.sound_volumes: dict[str, float] = {
            name: _clamp_volume(volume)
            for name, volume in (sound_volumes or {}).items()
        }
        self.sound_files: dict[str, str] = dict(sound_files or DEFAULT_SOUND_FILES)
        self.sound_groups: dict[str, tuple[str, ...]] = dict(
            sound_groups or DEFAULT_SOUND_GROUPS
        )
        self.sound_aliases: dict[str, str] = dict(sound_aliases or DEFAULT_SOUND_ALIASES)
        self.warmup_groups: dict[str, tuple[str, ...]] = dict(
            warmup_groups or DEFAULT_WARMUP_GROUPS
        )
        self.sound_priorities: dict[str, int] = dict(DEFAULT_SOUND_PRIORITIES)
        if sound_priorities:
            self.sound_priorities.update(
                {str(name): int(priority) for name, priority in sound_priorities.items()}
            )
        self.max_active_players = max(1, int(max_active_players))
        self.max_players_per_sound = max(1, int(max_players_per_sound))
        self._rng = random.Random(random_seed)
        self._last_variants: dict[str, str] = {}
        self.muted = False
        self._sounds: dict[str, arcade.Sound] = {}
        # A failed preload is remembered so a hot combat path never performs
        # the same filesystem/decode work on every call to ``play``. Explicit
        # and incremental retry APIs below are the only paths that bypass it.
        self._failed_loads: dict[str, str] = {}
        self.dropped_voice_count = 0
        # 同一音效可同時存在多個播放器，保留參考才能精準停止。
        self._players: dict[str, list[Any]] = {}
        if preload:
            self.load_all()

    @property
    def loaded_names(self) -> tuple[str, ...]:
        """回傳已成功載入的音效名稱。"""
        return tuple(self._sounds)

    @property
    def failed_names(self) -> tuple[str, ...]:
        """Return names held in the negative load cache."""
        return tuple(self._failed_loads)

    @property
    def active_player_count(self) -> int:
        """Return retained active voices after conservatively pruning finishes."""
        self.prune_finished_players()
        return sum(len(players) for players in self._players.values())

    def _warn(self, message: str) -> None:
        """音效失敗只發出警告，不中斷遊戲流程。"""
        warnings.warn(message, RuntimeWarning, stacklevel=2)

    def load(self, name: str, filename: str | None = None, *,
             retry_failed: bool = False) -> arcade.Sound | None:
        """Load one WAV, negatively caching failures until an explicit retry."""
        if name in self._sounds:
            return self._sounds[name]
        if name in self._failed_loads and not retry_failed:
            return None
        selected_filename = filename or self.sound_files.get(name)
        if not selected_filename:
            self._failed_loads[name] = "unknown sound name"
            self._warn(f"找不到音效名稱：{name}")
            return None
        path = self.sound_dir / selected_filename
        if not path.is_file():
            self._failed_loads[name] = f"missing file: {path}"
            self._warn(f"音效檔案不存在：{path}")
            return None
        try:
            sound = arcade.load_sound(path, streaming=False)
        except Exception as exc:  # 音效後端錯誤不能讓遊戲崩潰。
            self._failed_loads[name] = f"decode/backend failure: {exc}"
            self._warn(f"無法載入音效 {name}（{path.name}）：{exc}")
            return None
        self._sounds[name] = sound
        self._failed_loads.pop(name, None)
        self._players.setdefault(name, [])
        return sound

    def _expanded_warmup_names(
        self, names: str | Iterable[str] | None,
    ) -> tuple[str, ...]:
        """Expand named warmup groups, aliases, and iterables without repeats."""
        requested: Iterable[str]
        if names is None:
            requested = self.sound_files
        elif isinstance(names, str):
            requested = self.warmup_groups.get(names, (names,))
        else:
            requested = names

        expanded: list[str] = []
        seen: set[str] = set()
        for requested_name in requested:
            group_names = self.warmup_groups.get(requested_name, (requested_name,))
            for group_name in group_names:
                canonical = self.sound_aliases.get(group_name, group_name)
                variants = self.sound_groups.get(canonical, (canonical,))
                for variant in variants:
                    if variant not in seen:
                        seen.add(variant)
                        expanded.append(variant)
        return tuple(expanded)

    def iter_warmup(
        self,
        names: str | Iterable[str] | None = None,
        *,
        retry_failed: bool = False,
    ) -> Iterator[tuple[str, bool]]:
        """Incrementally load one cue per iteration.

        A caller may retain this iterator and advance it once per idle/update
        tick, keeping decode work away from combat input. Setting
        ``retry_failed`` makes this an explicit background retry path.
        """
        for name in self._expanded_warmup_names(names):
            loaded = self.load(name, retry_failed=retry_failed)
            yield name, loaded is not None

    def preload_group(self, group: str, *, retry_failed: bool = False
                      ) -> tuple[str, ...]:
        """Synchronously warm one named group and return successful cue names."""
        if group not in self.warmup_groups:
            raise KeyError(f"Unknown sound warmup group: {group}")
        return tuple(
            name for name, loaded in self.iter_warmup(
                group, retry_failed=retry_failed
            )
            if loaded
        )

    def load_all(self, *, retry_failed: bool = False) -> tuple[str, ...]:
        """Load every configured short cue and return successful names."""
        return tuple(
            name for name, loaded in self.iter_warmup(
                retry_failed=retry_failed
            )
            if loaded
        )

    def retry_failed(self, names: Iterable[str] | None = None) -> tuple[str, ...]:
        """Explicitly retry failed loads, suitable for a caller-driven idle pass."""
        targets = tuple(names) if names is not None else self.failed_names
        return tuple(
            name for name, loaded in self.iter_warmup(
                targets, retry_failed=True
            )
            if loaded
        )

    def reload(self, name: str) -> arcade.Sound | None:
        """Stop and explicitly reload one cue, bypassing its negative cache."""
        canonical = self.sound_aliases.get(name, name)
        for player_name in (name, canonical):
            if player_name in self._players:
                self.stop(player_name)
        self._sounds.pop(canonical, None)
        self._failed_loads.pop(canonical, None)
        return self.load(canonical, retry_failed=True)

    def reload_all(self) -> None:
        """停止播放器並重新載入全部檔案，供開發時重生音效後使用。"""
        self.stop_all()
        self._sounds.clear()
        self._players.clear()
        self._last_variants.clear()
        self._failed_loads.clear()
        self.load_all(retry_failed=True)

    def _resolve_variant(self, name: str) -> str:
        """從音效族群選擇變體，並避免連續兩次使用同一檔案。"""
        name = self.sound_aliases.get(name, name)
        candidates = tuple(
            candidate for candidate in self.sound_groups.get(name, (name,))
            if candidate in self._sounds or candidate in self.sound_files
        )
        if not candidates:
            return name
        previous = self._last_variants.get(name)
        choices = tuple(candidate for candidate in candidates if candidate != previous)
        selected = self._rng.choice(choices or candidates)
        self._last_variants[name] = selected
        return selected

    def set_master_volume(self, volume: float) -> None:
        """設定總音效音量；不改變各音效的相對音量。"""
        self.master_volume = _clamp_volume(volume)

    def set_volume(self, name: str, volume: float) -> None:
        """設定指定音效的固定音量倍率。"""
        if name not in self.sound_files and name not in self.sound_aliases:
            self._warn(f"設定未知音效的音量：{name}")
        self.sound_volumes[name] = _clamp_volume(volume)

    def get_volume(self, name: str) -> float:
        """取得指定音效的個別音量，未設定時為 1.0。"""
        return self.sound_volumes.get(name, 1.0)

    def mute(self) -> None:
        """靜音後續播放；既有播放器會立即停止。"""
        self.muted = True
        self.stop_all()

    def unmute(self) -> None:
        """解除靜音。"""
        self.muted = False

    def toggle_mute(self) -> bool:
        """切換靜音狀態，並回傳切換後是否為靜音。"""
        if self.muted:
            self.unmute()
        else:
            self.mute()
        return self.muted

    @staticmethod
    def _player_is_playing(player: Any) -> bool:
        """Conservatively query backend player state without stopping it."""
        probe = getattr(arcade, "is_sound_playing", None)
        if callable(probe):
            try:
                return bool(probe(player))
            except Exception:
                pass
        for attribute_name in ("playing", "is_playing"):
            try:
                state = getattr(player, attribute_name)
                return bool(state() if callable(state) else state)
            except (AttributeError, TypeError, RuntimeError):
                continue
        # Unknown backends are kept. A false positive retains only a reference;
        # a false negative could cut a still-audible critical cue.
        return True

    def prune_finished_players(self) -> int:
        """Forget naturally finished voices without calling ``stop_sound``."""
        removed = 0
        for name, players in self._players.items():
            playing: list[Any] = []
            for player in players:
                if player is not None and self._player_is_playing(player):
                    playing.append(player)
                else:
                    removed += 1
            players[:] = playing
        return removed

    def sound_priority(self, requested_name: str, selected_name: str | None = None) -> int:
        """Return the strongest configured priority for a cue and its variant."""
        canonical = self.sound_aliases.get(requested_name, requested_name)
        return max(
            self.sound_priorities.get(requested_name, 50),
            self.sound_priorities.get(canonical, 50),
            self.sound_priorities.get(selected_name or canonical, 50),
        )

    def _voice_available(self, requested_name: str, selected_name: str) -> bool:
        """Admit voices conservatively; never interrupt a playing cue."""
        self.prune_finished_players()
        priority = self.sound_priority(requested_name, selected_name)
        critical = priority >= CRITICAL_SOUND_PRIORITY
        active_total = sum(len(players) for players in self._players.values())
        active_for_name = len(self._players.get(requested_name, ()))
        if critical:
            # Critical impact, death, victory, and boss cues may temporarily
            # exceed soft limits. They are pruned as soon as playback ends.
            return True
        return (
            active_total < self.max_active_players
            and active_for_name < self.max_players_per_sound
        )

    def play(
        self,
        name: str,
        volume: float = 1.0,
        pan: float = 0.0,
        loop: bool = False,
        speed: float = 1.0,
        vary: bool = True,
    ) -> Any | None:
        """以名稱播放；音效族群會自動輪替內容並微調音高與音量。"""
        if self.muted:
            return None
        selected_name = self._resolve_variant(name) if vary else name
        sound = self._sounds.get(selected_name)
        if sound is None:
            # A preload=False client still gets one compatibility load. Once
            # that attempt fails, ``load`` returns from its negative cache on
            # later combat calls without touching disk or the decoder again.
            sound = self.load(selected_name)
        if sound is None:
            return None
        if not self._voice_available(name, selected_name):
            self.dropped_voice_count += 1
            return None
        volume_jitter = self._rng.uniform(.94, 1.025) if vary else 1.0
        pitch_low, pitch_high = DEFAULT_PITCH_RANGES.get(name, (.985, 1.015))
        pitch_jitter = self._rng.uniform(pitch_low, pitch_high) if vary else 1.0
        effective_volume = _clamp_volume(
            self.master_volume * self.get_volume(name) * _clamp_volume(volume)
            * volume_jitter
        )
        try:
            player = arcade.play_sound(
                sound,
                volume=effective_volume,
                pan=max(-1.0, min(1.0, float(pan))),
                loop=loop,
                speed=max(0.01, float(speed) * pitch_jitter),
            )
        except Exception as exc:  # 無音效裝置時也必須讓遊戲繼續。
            self._warn(f"無法播放音效 {name}（{selected_name}）：{exc}")
            return None
        if player is not None:
            self._players.setdefault(name, []).append(player)
        return player

    def stop(self, name: str, player: Any | None = None) -> None:
        """停止指定名稱的全部實例，或只停止傳入的播放器。"""
        players = self._players.get(name)
        if players is None:
            self._warn(f"找不到可停止的音效：{name}")
            return
        targets = [player] if player is not None else list(players)
        for target in targets:
            if target is None:
                continue
            try:
                arcade.stop_sound(target)
            except Exception as exc:
                self._warn(f"停止音效 {name} 失敗：{exc}")
            if target in players:
                players.remove(target)

    def stop_all(self) -> None:
        """停止由此管理器啟動的全部播放器。"""
        for name in tuple(self._players):
            self.stop(name)
