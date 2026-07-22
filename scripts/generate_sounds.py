r"""以 NumPy 程序合成遊戲短音效，並以 SciPy 輸出 44.1 kHz WAV。

執行方式：
    .\.venv\Scripts\python.exe scripts\generate_sounds.py

本檔不依賴任何外部音效素材。每次執行都會重設固定亂數種子，
因此相同版本的 NumPy／SciPy 會產生一致的輸出。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path
import sys

import numpy as np
from numpy.random import Generator
from numpy.typing import NDArray
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt


SAMPLE_RATE = 44_100
RANDOM_SEED = 20_260_719
TARGET_PEAK = 0.95
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "assets" / "audio"

AudioArray = NDArray[np.float64]
AudioLayer = AudioArray | tuple[AudioArray, float]


def _sample_count(duration: float, sample_rate: int) -> int:
    """把秒數轉成至少一格的取樣數。"""
    if duration <= 0:
        raise ValueError("duration 必須大於 0")
    if sample_rate <= 0:
        raise ValueError("sample_rate 必須大於 0")
    return max(1, int(round(duration * sample_rate)))


def _time_axis(duration: float, sample_rate: int) -> AudioArray:
    return np.arange(_sample_count(duration, sample_rate), dtype=np.float64) / sample_rate


def sine_wave(frequency: float, duration: float, amplitude: float = 1.0,
              phase: float = 0.0, sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """產生指定頻率、相位與振幅的正弦波。"""
    time = _time_axis(duration, sample_rate)
    return amplitude * np.sin(2.0 * np.pi * frequency * time + phase)


def square_wave(frequency: float, duration: float, amplitude: float = 1.0,
                phase: float = 0.0, sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """產生方波；實際音效會再搭配濾波與包絡使用。"""
    source = sine_wave(frequency, duration, 1.0, phase, sample_rate)
    return amplitude * np.where(source >= 0.0, 1.0, -1.0)


def triangle_wave(frequency: float, duration: float, amplitude: float = 1.0,
                  phase: float = 0.0, sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """產生三角波，提供比正弦波更豐富但柔和的泛音。"""
    time = _time_axis(duration, sample_rate)
    return amplitude * (2.0 / np.pi) * np.arcsin(
        np.sin(2.0 * np.pi * frequency * time + phase)
    )


def frequency_sweep(start_frequency: float, end_frequency: float, duration: float,
                    amplitude: float = 1.0, curve: str = "linear",
                    phase: float = 0.0,
                    sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """產生線性或指數 frequency sweep，並以累積相位避免不連續。"""
    count = _sample_count(duration, sample_rate)
    if curve == "linear":
        frequencies = np.linspace(start_frequency, end_frequency, count, dtype=np.float64)
    elif curve == "exponential":
        if start_frequency <= 0 or end_frequency <= 0:
            raise ValueError("指數 sweep 的起訖頻率必須大於 0")
        frequencies = np.geomspace(start_frequency, end_frequency, count, dtype=np.float64)
    else:
        raise ValueError("curve 僅支援 'linear' 或 'exponential'")
    accumulated_phase = 2.0 * np.pi * np.cumsum(frequencies) / sample_rate
    return amplitude * np.sin(accumulated_phase + phase)


def white_noise(duration: float, amplitude: float = 1.0,
                sample_rate: int = SAMPLE_RATE,
                rng: Generator | None = None) -> AudioArray:
    """產生白雜訊；未傳入 RNG 時仍使用固定種子。"""
    generator = rng if rng is not None else np.random.default_rng(RANDOM_SEED)
    return amplitude * generator.uniform(
        -1.0, 1.0, _sample_count(duration, sample_rate)
    ).astype(np.float64)


def low_pass_filter(audio: AudioArray, cutoff_hz: float,
                    sample_rate: int = SAMPLE_RATE, order: int = 4) -> AudioArray:
    """使用 Butterworth 低通濾波器移除高頻。"""
    if not 0 < cutoff_hz < sample_rate / 2:
        raise ValueError("cutoff_hz 必須介於 0 與 Nyquist 頻率之間")
    if audio.size < 2:
        return audio.astype(np.float64, copy=True)
    sections = butter(order, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    return np.asarray(sosfiltfilt(sections, audio), dtype=np.float64)


def high_pass_filter(audio: AudioArray, cutoff_hz: float,
                     sample_rate: int = SAMPLE_RATE, order: int = 4) -> AudioArray:
    """使用 Butterworth 高通濾波器移除低頻。"""
    if not 0 < cutoff_hz < sample_rate / 2:
        raise ValueError("cutoff_hz 必須介於 0 與 Nyquist 頻率之間")
    if audio.size < 2:
        return audio.astype(np.float64, copy=True)
    sections = butter(order, cutoff_hz, btype="highpass", fs=sample_rate, output="sos")
    return np.asarray(sosfiltfilt(sections, audio), dtype=np.float64)


def filtered_noise(duration: float, amplitude: float = 1.0,
                   low_cut_hz: float | None = None,
                   high_cut_hz: float | None = None,
                   sample_rate: int = SAMPLE_RATE,
                   rng: Generator | None = None) -> AudioArray:
    """產生可選高通／低通的雜訊層，用於破風、撞擊與爆炸。"""
    audio = white_noise(duration, amplitude, sample_rate, rng)
    if low_cut_hz is not None:
        audio = high_pass_filter(audio, low_cut_hz, sample_rate)
    if high_cut_hz is not None:
        audio = low_pass_filter(audio, high_cut_hz, sample_rate)
    return audio


def adsr_envelope(duration: float, attack: float, decay: float,
                  sustain_level: float, release: float,
                  sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """建立 ADSR 音量包絡；若階段總長超過音效，會按比例縮短。"""
    count = _sample_count(duration, sample_rate)
    stages = np.array([max(0.0, attack), max(0.0, decay), max(0.0, release)])
    stage_samples = np.rint(stages * sample_rate).astype(int)
    if stage_samples.sum() > count:
        stage_samples = np.floor(stage_samples * (count / stage_samples.sum())).astype(int)
    attack_count, decay_count, release_count = (int(value) for value in stage_samples)
    sustain_count = max(0, count - attack_count - decay_count - release_count)
    parts: list[AudioArray] = []
    if attack_count:
        parts.append(np.linspace(0.0, 1.0, attack_count, endpoint=False))
    if decay_count:
        parts.append(np.linspace(1.0, sustain_level, decay_count, endpoint=False))
    if sustain_count:
        parts.append(np.full(sustain_count, sustain_level, dtype=np.float64))
    if release_count:
        parts.append(np.linspace(sustain_level, 0.0, release_count, endpoint=True))
    envelope = np.concatenate(parts) if parts else np.zeros(count, dtype=np.float64)
    if envelope.size < count:
        envelope = np.pad(envelope, (0, count - envelope.size))
    return envelope[:count].astype(np.float64, copy=False)


def fade_in_out(audio: AudioArray, fade_in: float = 0.005,
                fade_out: float = 0.02,
                sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """加入短暫淡入淡出，避免波形在邊界突然截斷而爆音。"""
    result = np.asarray(audio, dtype=np.float64).copy()
    if result.size == 0:
        return result
    fade_in_count = min(result.size, max(0, int(round(fade_in * sample_rate))))
    fade_out_count = min(result.size, max(0, int(round(fade_out * sample_rate))))
    if fade_in_count:
        result[:fade_in_count] *= np.linspace(0.0, 1.0, fade_in_count, endpoint=True)
    if fade_out_count:
        result[-fade_out_count:] *= np.linspace(1.0, 0.0, fade_out_count, endpoint=True)
    return result


def normalize_audio(audio: AudioArray, target_peak: float = TARGET_PEAK) -> AudioArray:
    """檢查有限值並將峰值正規化；target_peak 必須小於等於 1。"""
    result = np.asarray(audio, dtype=np.float64)
    if result.size == 0:
        raise ValueError("不能正規化空白音訊")
    if not np.all(np.isfinite(result)):
        raise ValueError("音訊包含 NaN 或 Infinity")
    if not 0 < target_peak <= 1.0:
        raise ValueError("target_peak 必須介於 0 與 1 之間")
    peak = float(np.max(np.abs(result)))
    if peak <= np.finfo(np.float64).eps:
        raise ValueError("不能輸出全靜音音訊")
    normalized = result * (target_peak / peak)
    return np.clip(normalized, -1.0, 1.0)


def mix_layers(layers: Iterable[AudioLayer]) -> AudioArray:
    """混合不同長度的音訊層；短層會在尾端補零。"""
    prepared: list[tuple[AudioArray, float]] = []
    for layer in layers:
        if isinstance(layer, tuple):
            audio, gain = layer
        else:
            audio, gain = layer, 1.0
        prepared.append((np.asarray(audio, dtype=np.float64), float(gain)))
    if not prepared:
        raise ValueError("mix_layers 至少需要一個音訊層")
    length = max(audio.size for audio, _gain in prepared)
    mixed = np.zeros(length, dtype=np.float64)
    for audio, gain in prepared:
        mixed[:audio.size] += audio * gain
    return mixed


def save_wav(path: str | Path, audio: AudioArray,
             sample_rate: int = SAMPLE_RATE) -> Path:
    """正規化、clipping 檢查後，以 scipy.io.wavfile 輸出 16-bit mono WAV。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_audio = normalize_audio(audio, TARGET_PEAK)
    if np.any(np.abs(safe_audio) > 1.0):
        raise ValueError(f"clipping 檢查失敗：{output_path.name}")
    pcm = np.rint(safe_audio * np.iinfo(np.int16).max).astype(np.int16)
    if pcm.ndim != 1:
        raise ValueError("僅支援 mono 音訊")
    wavfile.write(output_path, sample_rate, pcm)
    return output_path


def _place(audio: AudioArray, offset: float, total_duration: float,
           sample_rate: int = SAMPLE_RATE) -> AudioArray:
    """把音訊放進指定長度的時間軸。"""
    result = np.zeros(_sample_count(total_duration, sample_rate), dtype=np.float64)
    start = max(0, int(round(offset * sample_rate)))
    end = min(result.size, start + audio.size)
    if start < result.size:
        result[start:end] = audio[:end - start]
    return result


def _soft_saturate(audio: AudioArray, drive: float = 1.25) -> AudioArray:
    """以柔和非線性增加泛音與密度，避免純振盪器的呆板感。"""
    if drive <= 0:
        raise ValueError("drive 必須大於 0")
    return np.tanh(np.asarray(audio, dtype=np.float64) * drive) / np.tanh(drive)


def _short_room(audio: AudioArray, wet: float = 0.16,
                brightness: float = 5_500.0) -> AudioArray:
    """以多重早期反射建立短空間感，不使用任何外部 impulse response。"""
    source = np.asarray(audio, dtype=np.float64)
    reflected = np.zeros_like(source)
    for delay, gain in ((.013, .54), (.027, .37), (.043, .25), (.071, .14)):
        offset = int(round(delay * SAMPLE_RATE))
        if offset < source.size:
            reflected[offset:] += source[:-offset] * gain
    reflected = low_pass_filter(reflected, brightness)
    return source * (1.0 - wet) + reflected * wet


def _fm_tone(carrier: float, modulator: float, modulation_index: float,
             duration: float, amplitude: float = 1.0,
             decay_rate: float = 0.0) -> AudioArray:
    """FM 音色提供非整數側頻，適合魔法、金屬與黑霧能量。"""
    time = _time_axis(duration, SAMPLE_RATE)
    phase_modulation = modulation_index * np.sin(2.0 * np.pi * modulator * time)
    signal = amplitude * np.sin(2.0 * np.pi * carrier * time + phase_modulation)
    if decay_rate > 0:
        signal *= np.exp(-decay_rate * time)
    return signal


def _modal_impact(frequencies: tuple[float, ...], duration: float,
                  rng: Generator, decay_base: float = 7.0) -> AudioArray:
    """疊加非諧和模態與隨機相位，模擬金屬、木石與玻璃共振。"""
    time = _time_axis(duration, SAMPLE_RATE)
    result = np.zeros_like(time)
    for index, frequency in enumerate(frequencies):
        phase = rng.uniform(0.0, np.pi * 2.0)
        detune = rng.uniform(.992, 1.008)
        amplitude = 1.0 / (1.0 + index * .62)
        decay = decay_base * (1.0 + index * .22)
        envelope = np.exp(-decay * time)
        result += amplitude * np.sin(
            2.0 * np.pi * frequency * detune * time + phase
        ) * envelope
        # 雙模態的細微拍頻可保留不規則尾韻。
        result += amplitude * .22 * np.sin(
            2.0 * np.pi * frequency * 1.013 * time - phase
        ) * envelope
    return result


def _finalize(audio: AudioArray, fade_in: float = 0.004,
              fade_out: float = 0.025) -> AudioArray:
    """所有成品共用的邊界淡化與安全正規化。"""
    enriched = _soft_saturate(audio)
    return normalize_audio(fade_in_out(enriched, fade_in, fade_out), 0.92)


def _master_depth(name: str, audio: AudioArray, rng: Generator) -> AudioArray:
    """為每個成品補上低頻身體、高頻空氣與短反射，避免單薄電子感。"""
    source = np.asarray(audio, dtype=np.float64)
    duration = source.size / SAMPLE_RATE
    ui_sound = name.startswith("ui_")
    body = low_pass_filter(source, 1_050 if ui_sound else 820)
    air = high_pass_filter(source, 3_800 if ui_sound else 2_900)
    texture = filtered_noise(
        duration, 1.0, 650 if ui_sound else 120,
        8_500 if ui_sound else 6_800, rng=rng,
    )
    texture *= adsr_envelope(
        duration, .002, min(.045, duration * .18),
        .10 if ui_sound else .18, min(.08, duration * .28),
    )
    layered = mix_layers((
        (source, 1.0),
        (body, .07 if ui_sound else .14),
        (air, .055 if ui_sound else .09),
        (texture, .004 if ui_sound else .011),
    ))
    room = _short_room(
        layered, .055 if ui_sound else .14,
        7_200 if ui_sound else 5_800,
    )
    return _finalize(room, .002, min(.06, duration * .18))


def _damped_tone(frequency: float, duration: float, decay_rate: float,
                 amplitude: float = 1.0) -> AudioArray:
    """含基音、二次與非整數泛音的自然衰減音色。"""
    time = _time_axis(duration, SAMPLE_RATE)
    harmonics = mix_layers((
        sine_wave(frequency, duration, 1.0),
        (sine_wave(frequency * 2.01, duration, 1.0), 0.34),
        (sine_wave(frequency * 3.97, duration, 1.0), 0.13),
    ))
    return amplitude * harmonics * np.exp(-decay_rate * time)


def build_ui_click(rng: Generator) -> AudioArray:
    duration = 0.105
    envelope = adsr_envelope(duration, 0.002, 0.025, 0.18, 0.055)
    tone = mix_layers((
        (triangle_wave(1_180, duration), 0.70),
        (sine_wave(1_940, duration), 0.30),
        (filtered_noise(duration, 1.0, 1_500, 8_500, rng=rng), 0.09),
    ))
    return _finalize(tone * envelope, 0.002, 0.018)


def build_coin(rng: Generator) -> AudioArray:
    del rng
    duration = 0.48
    layers: list[AudioLayer] = []
    for offset, frequency, gain in ((0.0, 1_760, 0.75), (0.075, 2_360, 0.66),
                                    (0.15, 3_120, 0.55)):
        note = _damped_tone(frequency, 0.30, 12.0, gain)
        layers.append(_place(note, offset, duration))
    shimmer = frequency_sweep(2_400, 4_500, 0.20, 0.18, "exponential")
    layers.append(_place(shimmer * adsr_envelope(0.20, .002, .04, .2, .12), .04, duration))
    return _finalize(mix_layers(layers), 0.002, 0.045)


def build_jump(rng: Generator) -> AudioArray:
    duration = 0.31
    sweep = frequency_sweep(150, 920, duration, 0.78, "exponential")
    bright = frequency_sweep(360, 1_720, duration, 0.26, "exponential", phase=.7)
    air = filtered_noise(duration, .12, 900, 6_500, rng=rng)
    envelope = adsr_envelope(duration, .008, .05, .55, .12)
    return _finalize(mix_layers((sweep, bright, air)) * envelope, .004, .035)


def build_hurt(rng: Generator) -> AudioArray:
    duration = 0.38
    body = frequency_sweep(210, 58, duration, .78, "exponential")
    grit = low_pass_filter(square_wave(105, duration, .34), 1_250)
    impact = filtered_noise(duration, .45, 55, 1_900, rng=rng)
    envelope = adsr_envelope(duration, .002, .07, .34, .20)
    time = _time_axis(duration, SAMPLE_RATE)
    impact *= np.exp(-14.0 * time)
    return _finalize(mix_layers((body, grit, impact)) * envelope, .002, .05)


def build_sword_swing(rng: Generator) -> AudioArray:
    duration = 0.34
    time = _time_axis(duration, SAMPLE_RATE)
    air = filtered_noise(duration, .85, 650, 9_500, rng=rng)
    whoosh_shape = np.sin(np.pi * np.clip(time / duration, 0.0, 1.0)) ** 2
    edge = frequency_sweep(1_700, 260, duration, .34, "exponential")
    edge *= adsr_envelope(duration, .012, .08, .34, .11)
    return _finalize(mix_layers((air * whoosh_shape, edge)), .006, .04)


def build_sword_hit(rng: Generator) -> AudioArray:
    duration = 0.52
    time = _time_axis(duration, SAMPLE_RATE)
    metal = mix_layers(tuple(
        (_damped_tone(frequency, duration, 8.0 + index * 1.2), gain)
        for index, (frequency, gain) in enumerate(
            ((420, .55), (735, .48), (1_173, .36), (1_921, .22), (2_687, .14))
        )
    ))
    impact = filtered_noise(duration, .70, 90, 5_200, rng=rng) * np.exp(-25.0 * time)
    thump = frequency_sweep(135, 52, .25, .46, "exponential")
    thump = _place(thump * adsr_envelope(.25, .001, .05, .25, .13), 0.0, duration)
    return _finalize(mix_layers((metal, impact, thump)), .0015, .055)


def build_fireball(rng: Generator) -> AudioArray:
    duration = 0.92
    charge_duration = 0.30
    charge = frequency_sweep(90, 520, charge_duration, .42, "exponential")
    charge += frequency_sweep(180, 1_140, charge_duration, .20, "exponential", phase=1.2)
    charge *= adsr_envelope(charge_duration, .02, .07, .65, .06)
    flight_duration = 0.58
    flight_time = _time_axis(flight_duration, SAMPLE_RATE)
    flight = filtered_noise(flight_duration, .45, 160, 4_800, rng=rng)
    flight *= (.45 + .55 * np.sin(np.pi * flight_time / flight_duration))
    flight += frequency_sweep(430, 190, flight_duration, .22, "exponential")
    burst_duration = 0.34
    burst_time = _time_axis(burst_duration, SAMPLE_RATE)
    burst = filtered_noise(burst_duration, .90, 45, 2_900, rng=rng) * np.exp(-9.0 * burst_time)
    burst += frequency_sweep(125, 38, burst_duration, .55, "exponential") * np.exp(-6.0 * burst_time)
    return _finalize(mix_layers((
        _place(charge, 0.0, duration),
        _place(flight, .22, duration),
        _place(burst, .58, duration),
    )), .006, .07)


def build_ice_spell(rng: Generator) -> AudioArray:
    duration = 0.72
    layers: list[AudioLayer] = []
    for index, (offset, frequency) in enumerate(
        ((0.0, 1_420), (.055, 2_130), (.12, 3_170), (.19, 4_260))
    ):
        crystal = _damped_tone(frequency, .34, 11.0 + index, .62 - index * .08)
        layers.append(_place(crystal, offset, duration))
    shards = filtered_noise(.46, .46, 2_200, 11_500, rng=rng)
    shard_time = _time_axis(.46, SAMPLE_RATE)
    gate = (np.sin(2 * np.pi * 31 * shard_time) > .58).astype(np.float64)
    shards *= gate * np.exp(-4.8 * shard_time)
    layers.append(_place(shards, .18, duration))
    return _finalize(mix_layers(layers), .002, .075)


def build_lightning(rng: Generator) -> AudioArray:
    duration = 0.60
    time = _time_axis(duration, SAMPLE_RATE)
    crack = filtered_noise(duration, .90, 1_200, 14_500, rng=rng)
    pulse = np.maximum(0.0, np.sin(2 * np.pi * (58 + 55 * time) * time)) ** 7
    crack *= (.18 + .82 * pulse) * np.exp(-5.8 * time)
    electric = frequency_sweep(4_800, 620, .25, .35, "exponential")
    electric = _place(electric * adsr_envelope(.25, .001, .025, .38, .12), 0.0, duration)
    thunder = frequency_sweep(105, 34, .50, .58, "exponential")
    thunder = _place(thunder * adsr_envelope(.50, .002, .10, .35, .26), .055, duration)
    return _finalize(mix_layers((crack, electric, thunder)), .001, .075)


def build_explosion(rng: Generator) -> AudioArray:
    duration = 1.08
    time = _time_axis(duration, SAMPLE_RATE)
    blast = filtered_noise(duration, .95, 28, 2_600, rng=rng) * np.exp(-4.5 * time)
    body = frequency_sweep(118, 31, duration, .82, "exponential") * np.exp(-3.0 * time)
    pressure = low_pass_filter(white_noise(duration, .52, rng=rng), 320)
    pressure *= np.exp(-3.4 * time)
    debris = filtered_noise(duration, .32, 2_000, 9_000, rng=rng)
    debris_gate = (np.sin(2 * np.pi * 19 * time + .7) > .79).astype(np.float64)
    debris *= debris_gate * np.exp(-2.6 * time)
    return _finalize(mix_layers((blast, body, pressure, debris)), .0015, .11)


def build_level_up(rng: Generator) -> AudioArray:
    del rng
    duration = 1.34
    layers: list[AudioLayer] = []
    notes = ((0.00, 523.25), (.22, 659.25), (.44, 783.99), (.68, 1_046.50))
    for index, (offset, frequency) in enumerate(notes):
        note_duration = .55 if index == len(notes) - 1 else .40
        note = _damped_tone(frequency, note_duration, 5.2, .58)
        note += sine_wave(frequency * 1.5, note_duration, .13)
        note *= adsr_envelope(note_duration, .008, .08, .55, .20)
        layers.append(_place(note, offset, duration))
    shimmer = frequency_sweep(1_300, 4_200, .78, .18, "exponential")
    shimmer *= adsr_envelope(.78, .08, .12, .42, .24)
    layers.append(_place(shimmer, .34, duration))
    return _finalize(mix_layers(layers), .004, .12)


def build_death(rng: Generator) -> AudioArray:
    duration = 1.82
    layers: list[AudioLayer] = []
    notes = ((0.0, 392.0), (.34, 311.13), (.68, 261.63), (1.03, 196.0))
    for index, (offset, frequency) in enumerate(notes):
        note_duration = .72 if index == len(notes) - 1 else .50
        note = mix_layers((
            (triangle_wave(frequency, note_duration), .64),
            (sine_wave(frequency / 2, note_duration), .35),
            (sine_wave(frequency * 2.01, note_duration), .15),
        ))
        note = low_pass_filter(note, 2_400)
        note *= adsr_envelope(note_duration, .018, .10, .52, .28)
        layers.append(_place(note, offset, duration))
    wind = filtered_noise(duration, .12, 180, 1_700, rng=rng)
    wind *= adsr_envelope(duration, .20, .25, .45, .55)
    layers.append(wind)
    return _finalize(mix_layers(layers), .008, .15)


def build_shield(rng: Generator) -> AudioArray:
    duration = 0.56
    time = _time_axis(duration, SAMPLE_RATE)
    ward = mix_layers((
        (_damped_tone(286, duration, 6.5), .58),
        (_damped_tone(431, duration, 7.2), .42),
        (_damped_tone(692, duration, 8.0), .25),
    ))
    impact = filtered_noise(duration, .42, 180, 4_000, rng=rng) * np.exp(-19.0 * time)
    magic = frequency_sweep(510, 1_180, .30, .24, "exponential")
    magic = _place(magic * adsr_envelope(.30, .004, .06, .35, .14), .02, duration)
    return _finalize(mix_layers((ward, impact, magic)), .002, .065)


def build_potion(rng: Generator) -> AudioArray:
    duration = 0.62
    clink = mix_layers((
        (_damped_tone(1_420, .34, 11.0), .55),
        (_damped_tone(2_387, .34, 13.0), .30),
    ))
    liquid = filtered_noise(.48, .36, 260, 2_200, rng=rng)
    liquid_time = _time_axis(.48, SAMPLE_RATE)
    liquid *= (0.45 + 0.55 * np.sin(2 * np.pi * 7.5 * liquid_time) ** 2)
    glug = frequency_sweep(190, 92, .24, .34, "exponential")
    return _finalize(mix_layers((
        _place(clink, 0.0, duration),
        _place(liquid, .10, duration),
        _place(glug * adsr_envelope(.24, .008, .05, .42, .10), .28, duration),
    )), .003, .07)


def build_heal(rng: Generator) -> AudioArray:
    duration = 0.94
    layers: list[AudioLayer] = []
    for offset, frequency in ((0.0, 523.25), (.14, 659.25), (.28, 783.99), (.43, 987.77)):
        note = _damped_tone(frequency, .46, 6.7, .42)
        note *= adsr_envelope(.46, .02, .08, .50, .20)
        layers.append(_place(note, offset, duration))
    shimmer = filtered_noise(.72, .14, 2_800, 10_500, rng=rng)
    shimmer *= adsr_envelope(.72, .10, .12, .42, .24)
    layers.append(_place(shimmer, .12, duration))
    return _finalize(mix_layers(layers), .008, .11)


def build_curse(rng: Generator) -> AudioArray:
    duration = 0.88
    time = _time_axis(duration, SAMPLE_RATE)
    first = frequency_sweep(510, 72, duration, .50, "exponential")
    second = frequency_sweep(733, 91, duration, .31, "exponential", phase=1.3)
    drone = triangle_wave(58, duration, .30) + sine_wave(87, duration, .22)
    whisper = filtered_noise(duration, .30, 170, 3_600, rng=rng)
    whisper *= (.35 + .65 * np.sin(2 * np.pi * 9.0 * time) ** 2) * np.exp(-1.8 * time)
    envelope = adsr_envelope(duration, .025, .12, .55, .28)
    return _finalize(mix_layers((first, second, drone, whisper)) * envelope, .008, .10)


def build_critical(rng: Generator) -> AudioArray:
    duration = 0.64
    time = _time_axis(duration, SAMPLE_RATE)
    impact = filtered_noise(duration, .86, 70, 6_200, rng=rng) * np.exp(-20.0 * time)
    low = frequency_sweep(155, 38, .42, .72, "exponential")
    low = _place(low * adsr_envelope(.42, .001, .06, .30, .22), 0.0, duration)
    ring = mix_layers((
        (_damped_tone(880, duration, 7.4), .42),
        (_damped_tone(1_327, duration, 8.6), .30),
        (_damped_tone(2_243, duration, 10.0), .18),
    ))
    return _finalize(mix_layers((impact, low, ring)), .001, .08)


def build_victory(rng: Generator) -> AudioArray:
    duration = 1.92
    layers: list[AudioLayer] = []
    notes = ((0.00, 523.25), (.22, 659.25), (.44, 783.99),
             (.70, 1_046.50), (.98, 1_318.51))
    for index, (offset, frequency) in enumerate(notes):
        note_duration = .78 if index >= 3 else .48
        note = _damped_tone(frequency, note_duration, 4.6, .48)
        note += triangle_wave(frequency / 2, note_duration, .14)
        note *= adsr_envelope(note_duration, .012, .10, .58, .30)
        layers.append(_place(note, offset, duration))
    sparkle = filtered_noise(1.25, .13, 3_200, 12_000, rng=rng)
    sparkle_time = _time_axis(1.25, SAMPLE_RATE)
    sparkle *= (np.sin(2 * np.pi * 17 * sparkle_time) > .70).astype(np.float64)
    sparkle *= adsr_envelope(1.25, .18, .20, .40, .42)
    layers.append(_place(sparkle, .42, duration))
    return _finalize(mix_layers(layers), .008, .16)


def build_ui_click_variant(rng: Generator, variant: int) -> AudioArray:
    """短促木革／暗鐵 UI 點擊變體，避免電子嗶聲感。"""
    duration = .105 + variant * .008
    base = 760 + variant * 95
    modal = _modal_impact((base, base * 1.71, base * 2.43), duration, rng, 23.0)
    transient = filtered_noise(duration, .22, 900, 7_800, rng=rng)
    transient *= np.exp(-42.0 * _time_axis(duration, SAMPLE_RATE))
    body = triangle_wave(112 + variant * 14, duration, .18)
    body *= adsr_envelope(duration, .001, .018, .08, .055)
    return _finalize(mix_layers(((modal, .54), transient, body)), .001, .022)


def build_coin_variant(rng: Generator, variant: int) -> AudioArray:
    """三種略不同材質與落點的金幣聲。"""
    duration = .46 + variant * .025
    base = (1_680, 1_850, 1_575)[variant]
    first = _modal_impact((base, base * 1.48, base * 2.17, base * 3.02),
                          duration, rng, 9.5 + variant)
    second = _modal_impact((base * 1.22, base * 1.83, base * 2.76),
                           .30, rng, 13.0)
    sparkle = _fm_tone(base * 1.5, 73 + variant * 11, 2.2, .24, .22, 11.0)
    return _finalize(_short_room(mix_layers((
        first,
        _place(second, .07 + variant * .016, duration),
        _place(sparkle, .03, duration),
    )), .12, 8_500), .001, .055)


def build_hurt_variant(rng: Generator, variant: int) -> AudioArray:
    """低頻肉身衝擊、裝甲摩擦與呼吸感受傷變體。"""
    duration = .36 + variant * .035
    time = _time_axis(duration, SAMPLE_RATE)
    body = frequency_sweep(205 + variant * 18, 52 + variant * 4,
                           duration, .72, "exponential")
    impact = filtered_noise(duration, .68, 45, 2_300 + variant * 350, rng=rng)
    impact *= np.exp(-(16.0 - variant) * time)
    armor = _modal_impact((174 + variant * 21, 283 + variant * 33,
                           467 + variant * 41), duration, rng, 10.0)
    groan = _fm_tone(74 + variant * 7, 19 + variant * 2, 3.0,
                     duration, .30, 4.8)
    envelope = adsr_envelope(duration, .002, .06, .34, .18)
    return _finalize(mix_layers((body, impact, (armor, .30), groan)) * envelope,
                     .0015, .055)


def build_sword_swing_variant(rng: Generator, variant: int) -> AudioArray:
    """不同速度與刃重的破風揮砍。"""
    duration = (.31, .36, .42)[variant]
    time = _time_axis(duration, SAMPLE_RATE)
    center = (.48, .54, .60)[variant]
    width = (.20, .24, .29)[variant]
    whoosh_shape = np.exp(-((time / duration - center) / width) ** 2)
    air = filtered_noise(duration, .88, 420 + variant * 170,
                         8_700 - variant * 900, rng=rng) * whoosh_shape
    blade = frequency_sweep(2_050 - variant * 260, 210 - variant * 25,
                            duration, .32, "exponential") * whoosh_shape
    flutter = _fm_tone(290 - variant * 25, 37 + variant * 4, 4.5,
                       duration, .16) * whoosh_shape
    return _finalize(mix_layers((air, blade, flutter)), .004, .045)


def build_sword_hit_variant(rng: Generator, variant: int) -> AudioArray:
    """三種劍刃撞擊：硬甲、厚甲與沉重招架。"""
    duration = .50 + variant * .06
    frequencies = (
        (390, 711, 1_173, 1_941, 2_815),
        (328, 604, 997, 1_537, 2_311),
        (244, 451, 779, 1_261, 2_087),
    )[variant]
    metal = _modal_impact(frequencies, duration, rng, 6.8 + variant * .5)
    time = _time_axis(duration, SAMPLE_RATE)
    strike = filtered_noise(duration, .75, 80, 5_500, rng=rng)
    strike *= np.exp(-(24.0 - variant * 2) * time)
    thump = frequency_sweep(142 - variant * 13, 39, .30 + variant * .04,
                            .52, "exponential")
    thump = _place(thump, 0.0, duration)
    return _finalize(_short_room(mix_layers((metal, strike, thump)), .10, 4_800),
                     .001, .07)


def build_ui_confirm(rng: Generator) -> AudioArray:
    duration = .24
    first = _modal_impact((720, 1_227, 1_941), duration, rng, 17.0)
    second = _modal_impact((960, 1_637, 2_511), .16, rng, 20.0)
    return _finalize(mix_layers((first, _place(second, .055, duration))), .001, .035)


def build_ui_cancel(rng: Generator) -> AudioArray:
    duration = .22
    wood = _modal_impact((510, 823, 1_307), duration, rng, 18.0)
    fall = frequency_sweep(720, 280, duration, .28, "exponential")
    return _finalize(mix_layers((wood, fall)), .001, .035)


def build_ui_error(rng: Generator) -> AudioArray:
    duration = .31
    buzz = _fm_tone(132, 47, 6.2, duration, .58, 5.0)
    knock = _modal_impact((188, 277, 433), duration, rng, 14.0)
    noise = filtered_noise(duration, .18, 220, 1_900, rng=rng)
    return _finalize(mix_layers((buzz, knock, noise)) *
                     adsr_envelope(duration, .002, .05, .40, .13), .002, .045)


def build_ui_panel_open(rng: Generator) -> AudioArray:
    duration = .38
    leather = filtered_noise(duration, .44, 180, 2_900, rng=rng)
    shape = adsr_envelope(duration, .012, .09, .45, .14)
    latch = _place(_modal_impact((610, 947, 1_493), .20, rng, 17.0), .14, duration)
    rise = frequency_sweep(180, 520, duration, .20, "exponential")
    return _finalize(mix_layers((leather * shape, latch, rise)), .004, .05)


def build_ui_panel_close(rng: Generator) -> AudioArray:
    duration = .34
    leather = filtered_noise(duration, .38, 160, 2_400, rng=rng)
    latch = _place(_modal_impact((470, 781, 1_171), .18, rng, 19.0), .13, duration)
    fall = frequency_sweep(470, 165, duration, .20, "exponential")
    return _finalize(mix_layers((leather * adsr_envelope(duration, .006, .07, .34, .15),
                                 latch, fall)), .003, .05)


def build_ui_page_turn(rng: Generator) -> AudioArray:
    duration = .42
    time = _time_axis(duration, SAMPLE_RATE)
    paper = filtered_noise(duration, .52, 650, 7_500, rng=rng)
    gesture = np.sin(np.pi * time / duration) ** 1.5
    fibers = _fm_tone(280, 63, 3.8, duration, .16) * gesture
    return _finalize(mix_layers((paper * gesture, fibers)), .006, .05)


def build_ui_talent_unlock(rng: Generator) -> AudioArray:
    duration = .82
    impact = _modal_impact((660, 991, 1_487, 2_223), duration, rng, 7.8)
    rise = frequency_sweep(330, 1_980, .52, .34, "exponential")
    aura = _short_room(_fm_tone(440, 71, 4.2, duration, .26, 2.5), .24, 7_800)
    return _finalize(mix_layers((impact, _place(rise, .08, duration), aura)), .005, .10)


def build_shield_block(rng: Generator) -> AudioArray:
    duration = .47
    metal = _modal_impact((214, 357, 593, 947, 1_481), duration, rng, 8.5)
    thud = filtered_noise(duration, .65, 45, 1_600, rng=rng)
    thud *= np.exp(-22 * _time_axis(duration, SAMPLE_RATE))
    return _finalize(mix_layers((metal, thud)), .001, .06)


def build_shield_break(rng: Generator) -> AudioArray:
    duration = .72
    ring = _modal_impact((243, 419, 701, 1_119, 1_883), duration, rng, 6.5)
    shards = filtered_noise(duration, .58, 1_700, 11_000, rng=rng)
    shard_time = _time_axis(duration, SAMPLE_RATE)
    shards *= (np.sin(2 * np.pi * 27 * shard_time) > .72) * np.exp(-4.2 * shard_time)
    fall = frequency_sweep(430, 61, duration, .34, "exponential")
    return _finalize(_short_room(mix_layers((ring, shards, fall)), .19, 6_000), .001, .09)


def build_dodge(rng: Generator) -> AudioArray:
    duration = .29
    time = _time_axis(duration, SAMPLE_RATE)
    air = filtered_noise(duration, .72, 850, 9_500, rng=rng)
    air *= np.exp(-((time / duration - .48) / .22) ** 2)
    snap = frequency_sweep(1_160, 310, duration, .25, "exponential")
    return _finalize(mix_layers((air, snap)), .004, .035)


def build_fireball_cast(rng: Generator) -> AudioArray:
    duration = .52
    charge = frequency_sweep(72, 690, duration, .48, "exponential")
    core = _fm_tone(184, 43, 6.5, duration, .38, 1.7)
    flame = filtered_noise(duration, .32, 120, 4_200, rng=rng)
    return _finalize(_short_room(mix_layers((charge, core, flame)) *
                                 adsr_envelope(duration, .035, .10, .62, .12), .16, 4_600),
                     .008, .06)


def build_fireball_impact(rng: Generator) -> AudioArray:
    duration = .68
    time = _time_axis(duration, SAMPLE_RATE)
    blast = filtered_noise(duration, .88, 38, 3_600, rng=rng) * np.exp(-6.8 * time)
    bass = frequency_sweep(143, 34, duration, .64, "exponential") * np.exp(-3.5 * time)
    embers = filtered_noise(duration, .25, 2_200, 10_000, rng=rng)
    embers *= (np.sin(2 * np.pi * 23 * time) > .73) * np.exp(-3.2 * time)
    return _finalize(_short_room(mix_layers((blast, bass, embers)), .14, 4_400), .001, .09)


def build_ice_cast(rng: Generator) -> AudioArray:
    duration = .56
    frost = frequency_sweep(480, 2_800, duration, .32, "exponential")
    glass = _modal_impact((1_211, 1_843, 2_977, 4_381), duration, rng, 8.5)
    mist = filtered_noise(duration, .20, 2_000, 12_000, rng=rng)
    return _finalize(_short_room(mix_layers((frost, glass, mist)), .22, 10_000), .006, .075)


def build_ice_shatter(rng: Generator) -> AudioArray:
    duration = .64
    time = _time_axis(duration, SAMPLE_RATE)
    glass = _modal_impact((1_030, 1_697, 2_647, 4_033, 6_211), duration, rng, 9.0)
    shards = filtered_noise(duration, .72, 2_400, 13_500, rng=rng)
    gate = (np.sin(2 * np.pi * (21 + 9 * time) * time) > .62).astype(np.float64)
    shards *= gate * np.exp(-5.0 * time)
    return _finalize(_short_room(mix_layers((glass, shards)), .24, 11_000), .001, .09)


def build_lightning_cast(rng: Generator) -> AudioArray:
    duration = .42
    time = _time_axis(duration, SAMPLE_RATE)
    charge = _fm_tone(620, 91, 9.0, duration, .42, 2.0)
    static = filtered_noise(duration, .54, 1_900, 14_000, rng=rng)
    static *= (.25 + .75 * np.sin(2 * np.pi * 47 * time) ** 8)
    rise = frequency_sweep(310, 5_200, duration, .28, "exponential")
    return _finalize(mix_layers((charge, static, rise)) *
                     adsr_envelope(duration, .012, .08, .58, .09), .003, .045)


def build_lightning_impact(rng: Generator) -> AudioArray:
    duration = .73
    time = _time_axis(duration, SAMPLE_RATE)
    crack = filtered_noise(duration, .92, 700, 15_000, rng=rng) * np.exp(-10.0 * time)
    thunder = frequency_sweep(122, 29, duration, .72, "exponential") * np.exp(-2.8 * time)
    arc = _fm_tone(1_140, 163, 11.0, .31, .32, 9.0)
    return _finalize(_short_room(mix_layers((crack, thunder, _place(arc, 0, duration))),
                                 .18, 5_200), .001, .10)


def build_holy_cast(rng: Generator) -> AudioArray:
    duration = .68
    choir = mix_layers(tuple(
        (_fm_tone(freq, freq / 7.0, 1.4, duration, amp, 2.2), 1.0)
        for freq, amp in ((261.63, .34), (329.63, .30), (392.0, .26), (523.25, .18))
    ))
    chime = _modal_impact((1_047, 1_568, 2_349, 3_521), duration, rng, 7.2)
    return _finalize(_short_room(mix_layers((choir, chime)), .28, 8_800), .012, .10)


def build_holy_impact(rng: Generator) -> AudioArray:
    duration = .72
    beam = frequency_sweep(2_600, 420, duration, .42, "exponential")
    impact = _modal_impact((523, 784, 1_176, 1_759, 2_639), duration, rng, 6.8)
    air = filtered_noise(duration, .28, 1_500, 9_000, rng=rng)
    return _finalize(_short_room(mix_layers((beam, impact, air)), .25, 8_000), .002, .10)


def build_shadow_step(rng: Generator) -> AudioArray:
    duration = .44
    time = _time_axis(duration, SAMPLE_RATE)
    air = filtered_noise(duration, .58, 320, 5_900, rng=rng)
    air *= np.sin(np.pi * time / duration) ** 2
    warp = frequency_sweep(620, 74, duration, .42, "exponential")
    phase = _fm_tone(190, 31, 7.5, duration, .30, 3.0)
    return _finalize(_short_room(mix_layers((air, warp, phase)), .22, 3_600), .006, .065)


def build_smoke_bomb(rng: Generator) -> AudioArray:
    duration = .78
    time = _time_axis(duration, SAMPLE_RATE)
    pop = filtered_noise(duration, .82, 60, 4_500, rng=rng) * np.exp(-19 * time)
    hiss = filtered_noise(duration, .46, 650, 7_800, rng=rng) * np.exp(-2.8 * time)
    puff = frequency_sweep(190, 47, .46, .38, "exponential")
    return _finalize(mix_layers((pop, hiss, _place(puff, .03, duration))), .001, .10)


def build_curse_tick(rng: Generator) -> AudioArray:
    duration = .38
    bite = _fm_tone(173, 53, 8.5, duration, .48, 7.5)
    grit = filtered_noise(duration, .35, 130, 3_100, rng=rng)
    fall = frequency_sweep(410, 68, duration, .35, "exponential")
    return _finalize(_short_room(mix_layers((bite, grit, fall)), .16, 3_400), .002, .055)


def build_meteor_fall(rng: Generator) -> AudioArray:
    duration = 1.18
    time = _time_axis(duration, SAMPLE_RATE)
    roar = filtered_noise(duration, .74, 75, 4_200, rng=rng)
    roar *= np.linspace(.16, 1.0, roar.size) ** 1.6
    pitch = frequency_sweep(680, 48, duration, .52, "exponential")
    rumble = _fm_tone(57, 14, 5.0, duration, .42) * np.linspace(.18, 1.0, time.size)
    return _finalize(_short_room(mix_layers((roar, pitch, rumble)), .12, 3_800), .02, .035)


def build_battle_start(rng: Generator) -> AudioArray:
    duration = .88
    drum = filtered_noise(duration, .70, 35, 520, rng=rng)
    drum *= np.exp(-5.4 * _time_axis(duration, SAMPLE_RATE))
    horn = _fm_tone(146.83, 36.7, 1.9, duration, .46, 2.1)
    metal = _place(_modal_impact((293, 451, 719), .44, rng, 7.8), .22, duration)
    return _finalize(_short_room(mix_layers((drum, horn, metal)), .24, 3_200), .004, .11)


def build_boss_roar(rng: Generator) -> AudioArray:
    duration = 1.38
    time = _time_axis(duration, SAMPLE_RATE)
    throat = _fm_tone(64, 23, 8.8, duration, .64, 1.5)
    throat += _fm_tone(91, 17, 5.4, duration, .38, 1.8)
    breath = filtered_noise(duration, .58, 45, 1_900, rng=rng)
    shape = adsr_envelope(duration, .08, .18, .72, .34)
    rumble = low_pass_filter(white_noise(duration, .36, rng=rng), 240)
    return _finalize(_short_room(mix_layers((throat, breath, rumble)) * shape,
                                 .28, 2_500), .015, .16)


def build_event_positive(rng: Generator) -> AudioArray:
    duration = .76
    notes = ((0, 523.25), (.12, 659.25), (.25, 783.99))
    layers = [_place(_damped_tone(freq, .46, 6.8, .42), offset, duration)
              for offset, freq in notes]
    layers.append(_short_room(_modal_impact((1_568, 2_349, 3_521), duration, rng, 8.0),
                              .24, 9_500))
    return _finalize(mix_layers(layers), .004, .10)


def build_event_negative(rng: Generator) -> AudioArray:
    duration = .82
    fall = frequency_sweep(392, 73, duration, .56, "exponential")
    dissonance = _fm_tone(147, 61, 7.2, duration, .46, 2.8)
    impact = _modal_impact((131, 203, 317, 487), duration, rng, 6.2)
    return _finalize(_short_room(mix_layers((fall, dissonance, impact)), .24, 3_000),
                     .004, .11)


def build_reward_open(rng: Generator) -> AudioArray:
    duration = .92
    latch = _modal_impact((311, 527, 859, 1_337), duration, rng, 7.3)
    coins = _place(build_coin_variant(rng, 1) * .42, .19, duration)
    rise = frequency_sweep(220, 1_320, .54, .25, "exponential")
    return _finalize(_short_room(mix_layers((latch, coins, rise)), .16, 7_000), .003, .12)


def build_campfire(rng: Generator) -> AudioArray:
    duration = 1.08
    time = _time_axis(duration, SAMPLE_RATE)
    flame = filtered_noise(duration, .38, 90, 2_600, rng=rng)
    flame *= (.38 + .62 * np.sin(2 * np.pi * 8.3 * time +
                                 .5 * np.sin(2 * np.pi * 1.7 * time)) ** 2)
    crackle = filtered_noise(duration, .28, 1_300, 9_500, rng=rng)
    crackle *= (np.sin(2 * np.pi * 17 * time) > .86)
    warmth = _fm_tone(110, 13, 1.7, duration, .16, 1.4)
    return _finalize(mix_layers((flame, crackle, warmth)), .02, .12)


def build_map_advance(rng: Generator) -> AudioArray:
    duration = .54
    step = filtered_noise(duration, .48, 55, 1_700, rng=rng)
    step *= np.exp(-18 * _time_axis(duration, SAMPLE_RATE))
    marker = _place(_modal_impact((440, 733, 1_177), .31, rng, 10.0), .12, duration)
    road = frequency_sweep(180, 430, duration, .22, "exponential")
    return _finalize(mix_layers((step, marker, road)), .002, .07)


def build_shop_open(rng: Generator) -> AudioArray:
    duration = .86
    bell = _modal_impact((781, 1_303, 2_089, 3_337), duration, rng, 6.8)
    curtain = filtered_noise(duration, .32, 350, 4_500, rng=rng)
    curtain *= adsr_envelope(duration, .04, .12, .42, .30)
    mystery = _fm_tone(196, 47, 3.2, duration, .22, 2.2)
    return _finalize(_short_room(mix_layers((bell, curtain, mystery)), .22, 6_800),
                     .005, .12)


def build_boss_victory(rng: Generator) -> AudioArray:
    duration = 2.46
    fanfare = _place(build_victory(rng) * .72, .28, duration)
    impact = filtered_noise(duration, .58, 30, 760, rng=rng)
    impact *= np.exp(-5.0 * _time_axis(duration, SAMPLE_RATE))
    chord = mix_layers(tuple(
        (_fm_tone(freq, freq / 8, 1.3, duration, amp, 1.2), 1.0)
        for freq, amp in ((130.81, .34), (196.0, .28), (261.63, .24), (392.0, .18))
    ))
    return _finalize(_short_room(mix_layers((impact, chord, fanfare)), .30, 5_500),
                     .008, .22)


SOUND_BUILDERS: dict[str, Callable[[Generator], AudioArray]] = {
    "ui_click": partial(build_ui_click_variant, variant=0),
    "ui_confirm": build_ui_confirm,
    "ui_cancel": build_ui_cancel,
    "coin": partial(build_coin_variant, variant=0),
    "hurt": partial(build_hurt_variant, variant=0),
    "sword_swing": partial(build_sword_swing_variant, variant=0),
    "sword_hit": partial(build_sword_hit_variant, variant=0),
    "fireball": build_fireball,
    "ice_spell": build_ice_spell,
    "lightning": build_lightning,
    "meteor_fall": build_meteor_fall,
    "level_up": build_level_up,
    "death": build_death,
    "shield": build_shield,
    "shield_block": build_shield_block,
    "dodge": build_dodge,
    "potion": build_potion,
    "heal": build_heal,
    "curse": build_curse,
    "critical": build_critical,
    "victory": build_victory,
    "holy_cast": build_holy_cast,
    "shadow_step": build_shadow_step,
    "smoke_bomb": build_smoke_bomb,
    "battle_start": build_battle_start,
    "boss_roar": build_boss_roar,
    "reward_open": build_reward_open,
    "campfire": build_campfire,
    "map_advance": build_map_advance,
}


def validate_wav(path: Path) -> dict[str, int | float]:
    """重新讀取 WAV，驗證格式、有限值、靜音與 clipping。"""
    sample_rate, pcm = wavfile.read(path)
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"{path.name}: 取樣率不是 {SAMPLE_RATE}")
    if pcm.dtype != np.int16:
        raise ValueError(f"{path.name}: 格式不是 16-bit PCM")
    if pcm.ndim != 1:
        raise ValueError(f"{path.name}: 不是 mono")
    if pcm.size == 0 or path.stat().st_size <= 44:
        raise ValueError(f"{path.name}: 空白檔案")
    floating = pcm.astype(np.float64) / np.iinfo(np.int16).max
    if not np.all(np.isfinite(floating)):
        raise ValueError(f"{path.name}: 包含 NaN 或 Infinity")
    peak_pcm = int(np.max(np.abs(pcm.astype(np.int32))))
    if peak_pcm >= np.iinfo(np.int16).max:
        raise ValueError(f"{path.name}: clipping")
    if peak_pcm == 0:
        raise ValueError(f"{path.name}: 全靜音")
    return {
        "samples": int(pcm.size),
        "duration": float(pcm.size / sample_rate),
        "peak_pcm": peak_pcm,
        "bytes": path.stat().st_size,
    }


def generate_all_sounds(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """以固定 seed 一次建立並驗證全部 canonical runtime 音效。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RANDOM_SEED)
    generated: list[Path] = []
    for name, builder in SOUND_BUILDERS.items():
        audio = _master_depth(name, builder(rng), rng)
        path = save_wav(output_dir / f"{name}.wav", audio)
        info = validate_wav(path)
        print(
            f"[OK] {path.name:<18} {info['duration']:.3f}s  "
            f"peak={info['peak_pcm']}  {info['bytes']} bytes"
        )
        generated.append(path)
    expected = {path.resolve() for path in generated}
    for stale in output_dir.glob("*.wav"):
        if stale.resolve() not in expected:
            stale.unlink()
            print(f"[移除] {stale.name}")
    return generated


def main() -> int:
    """命令列入口：成功回傳 0，任何驗證錯誤會停止並顯示原因。"""
    try:
        generated = generate_all_sounds()
    except Exception as exc:
        print(f"[ERROR] 音效生成失敗：{exc}", file=sys.stderr)
        return 1
    print(
        f"完成：{len(generated)} 個 44.1 kHz／16-bit／mono WAV，"
        f"輸出至 {OUTPUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
