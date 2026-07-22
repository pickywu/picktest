"""Runtime localization loaded from editable ``Localization/*.json`` files.

MOD friendly: every language is a plain JSON file in the ``Localization`` folder
next to the game.  The file name is the locale code (``en.json`` → ``EN``); its
contents map an authored Traditional-Chinese source string to its translation.
Players can edit a value, add a missing key, or drop in a brand-new
``<code>.json`` to add a language — it appears in the in-game picker
automatically.  Malformed files are skipped with a warning instead of crashing.

How a rendered string is translated (per locale):
1. exact match in the locale catalog;
2. authored ``{placeholder}`` template match (numbers/names are re-inserted and
   recursively translated in the same locale);
3. a runtime pattern from ``_DYNAMIC_SPECS`` (stage/damage/gold numbers …);
4. English only: free phrase composition for any leftover generated sentence;
5. otherwise the Traditional source is returned unchanged (safe fallback).

Steps 2–3 let Japanese/Korean cover generated combat/HUD text too, so a complete
``ja.json`` / ``ko.json`` yields no Traditional-Chinese fallback in play.  Logo
art (title / VICTORY / DEATH) is image-based and is never translated here.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import json
from pathlib import Path
import sys
import re
from typing import Any
import warnings

try:
    import zhconv
except ModuleNotFoundError:  # pragma: no cover - degrade gracefully if missing.
    zhconv = None


# ---------------------------------------------------------------------------
# External, mod-editable locale folder (next to the .exe in a packaged build).
# ---------------------------------------------------------------------------
def _resolve_localization_dir() -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "Localization")
        candidates.append(exe_dir / "_internal" / "Localization")
    candidates.append(Path(__file__).resolve().parent / "Localization")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


LOCALIZATION_DIR = _resolve_localization_dir()

SOURCE_LOCALE = "zh-TW"
DEFAULT_LOCALE = "zh-TW"
_PREFERRED_ORDER = ("zh-TW", "zh-CN", "EN", "JA", "KO")

_LOCALE_ALIASES = {
    "zh-tw": "zh-TW", "zh_tw": "zh-TW", "zh": "zh-TW",
    "zh-hant": "zh-TW", "zh-cht": "zh-TW",
    "zh-cn": "zh-CN", "zh_cn": "zh-CN", "zh-hans": "zh-CN",
    "zh-chs": "zh-CN", "cn": "zh-CN",
    "en": "EN", "en-us": "EN", "en_us": "EN", "english": "EN",
    "ja": "JA", "jp": "JA", "ja-jp": "JA", "ja_jp": "JA", "japanese": "JA",
    "ko": "KO", "kr": "KO", "ko-kr": "KO", "ko_kr": "KO", "korean": "KO",
}

_CJK_RE = re.compile(r"[㐀-鿿]")


def _canonical_locale(stem: str) -> str:
    value = str(stem).strip()
    return _LOCALE_ALIASES.get(value.lower(), value)


def _load_json(path: Path) -> dict[str, str]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        warnings.warn(f"無法讀取語系檔 {path.name}：{exc}", RuntimeWarning, stacklevel=2)
        return {}
    if not isinstance(data, dict):
        warnings.warn(f"語系檔 {path.name} 必須是 JSON 物件。", RuntimeWarning, stacklevel=2)
        return {}
    return {str(key): str(value) for key, value in data.items()}


_RESERVED_STEMS = {"en.phrases"}
_CATALOGS: dict[str, dict[str, str]] = {}
_EN_PHRASES_EXTRA: dict[str, str] = {}


def _discover_catalogs() -> None:
    _CATALOGS.clear()
    _EN_PHRASES_EXTRA.clear()
    if not LOCALIZATION_DIR.is_dir():
        warnings.warn(f"找不到語系資料夾：{LOCALIZATION_DIR}", RuntimeWarning, stacklevel=2)
        return
    for path in sorted(LOCALIZATION_DIR.glob("*.json")):
        stem = path.name[: -len(".json")]
        if stem.startswith("_"):
            continue  # Working/scratch files (e.g. _todo_*.json) are not locales.
        if stem in _RESERVED_STEMS:
            if stem == "en.phrases":
                _EN_PHRASES_EXTRA.update(_load_json(path))
            continue
        code = _canonical_locale(stem)
        if code == SOURCE_LOCALE:
            continue
        _CATALOGS[code] = _load_json(path)


_discover_catalogs()


def _supported_locales() -> tuple[str, ...]:
    available = {SOURCE_LOCALE}
    available.update(
        code for code, catalog in _CATALOGS.items()
        if code != "zh-CN" or bool(catalog) or zhconv is not None
    )
    if zhconv is not None:
        available.add("zh-CN")
    ordered = [code for code in _PREFERRED_ORDER if code in available]
    ordered.extend(sorted(code for code in available if code not in _PREFERRED_ORDER))
    return tuple(ordered)


SUPPORTED_LOCALES = _supported_locales()

_locale = DEFAULT_LOCALE
_CATALOG_GENERATION = 1
_TRANSLATION_CACHE_SIZE = 8192


# ---------------------------------------------------------------------------
# Authored ``{placeholder}`` templates, compiled per locale.
# ---------------------------------------------------------------------------
def _compile_template(source: str, target: str) -> tuple[re.Pattern[str], str, tuple[str, ...]]:
    tokens = tuple(re.findall(r"\{[^{}]+\}", source))
    pieces: list[str] = []
    cursor = 0
    for token in tokens:
        index = source.index(token, cursor)
        pieces.append(re.escape(source[cursor:index]))
        pieces.append("(.*?)")
        cursor = index + len(token)
    pieces.append(re.escape(source[cursor:]))
    return re.compile("^" + "".join(pieces) + "$", re.DOTALL), target, tokens


def _build_templates(catalog: Mapping[str, str]) -> tuple[tuple[re.Pattern[str], str, tuple[str, ...]], ...]:
    return tuple(
        _compile_template(source, target)
        for source, target in sorted(
            catalog.items(),
            key=lambda item: (
                -len(re.sub(r"\{[^{}]+\}", "", item[0])),
                -len(re.findall(r"\{[^{}]+\}", item[0])),
                -len(item[0]),
            ),
        )
        if "{" in source and "}" in source
    )


def _build_all_templates() -> dict[str, tuple]:
    return {locale: _build_templates(catalog) for locale, catalog in _CATALOGS.items()}


_LOCALE_TEMPLATES: dict[str, tuple] = _build_all_templates()


def _translate_template(text: str, locale: str) -> str | None:
    for pattern, target, tokens in _LOCALE_TEMPLATES.get(locale, ()):  # type: ignore[union-attr]
        match = pattern.fullmatch(text)
        if match is None:
            continue
        values: dict[str, str] = {}
        for index, token in enumerate(tokens, start=1):
            translated = _tr(locale, match.group(index)).rstrip()
            values.setdefault(token, translated.rstrip(" .,!?:;、。，"))
        return re.sub(
            r"\{[^{}]+\}",
            lambda placeholder: values.get(placeholder.group(0), placeholder.group(0)),
            target,
        )
    return None


# ---------------------------------------------------------------------------
# Runtime patterns (stage/save/damage numbers, stat deltas …).  Each spec is a
# source regex plus a per-locale output.  ``{N}`` inserts capture group N as-is;
# ``[N]`` inserts group N recursively translated into the same locale.
# ---------------------------------------------------------------------------
_DYNAMIC_SPECS_RAW: tuple[tuple[str, dict[str, str]], ...] = (
    # 等級 N(角色列/預覽會遞迴用到)
    (r"^等級 (\d+)$", {"EN": "LEVEL {1}", "JA": "レベル {1}", "KO": "레벨 {1}"}),
    # 護盾數值徽章 / 防禦意圖
    (r"^護盾 (\d+)$", {"EN": "Shield {1}", "JA": "シールド {1}", "KO": "보호막 {1}"}),
    (r"^\+(\d+) 護盾$", {"EN": "+{1} Shield", "JA": "+{1} シールド", "KO": "+{1} 보호막"}),
    # 營火治療選項
    (r"^恢復 (\d+) 血量$",
     {"EN": "Restore {1} HP", "JA": "{1} HP回復", "KO": "{1} HP 회복"}),
    # 角色建立步驟列:N 名字/種族/性別/職業(遞迴翻譯詞彙)
    (r"^(\d+) (名字|種族|性別|職業)$",
     {"EN": "{1} [2]", "JA": "{1} [2]", "KO": "{1} [2]"}),
    # 天賦節點:名稱 rank/max(遞迴翻譯名稱)。名稱不得含數字或斜線,避免誤匹配數值列。
    (r"^([^0-9/　]+) (\d+)/(\d+)$",
     {"EN": "[1] {2}/{3}", "JA": "[1] {2}/{3}", "KO": "[1] {2}/{3}"}),
    (r"^[（(]\s*(\d+)\s*層\s*[）)]$",
     {"EN": "({1} stacks)", "JA": "({1}スタック)", "KO": "({1} 스택)"}),
    (r"^\s*層\s*(\d+)\s*$",
     {"EN": "Stacks {1}", "JA": "{1}スタック", "KO": "{1} 스택"}),
    (r"^抵達第\s*(\d+)\s*關(.*)$",
     {"EN": "REACHED STAGE {1}[2]", "JA": "第{1}関に到達[2]", "KO": "{1} 스테이지 도달[2]"}),
    (r"^第\s*(\d+)\s*關(.+)$",
     {"EN": "STAGE {1}[2]", "JA": "第{1}関[2]", "KO": "{1} 스테이지[2]"}),
    (r"^第\s*(\d+)\s*關$",
     {"EN": "STAGE {1}", "JA": "第{1}関", "KO": "{1} 스테이지"}),
    (r"^存檔槽\s*(\d+)$",
     {"EN": "SAVE SLOT {1}", "JA": "セーブ枠 {1}", "KO": "저장 슬롯 {1}"}),
    (r"^讀取存檔槽\s*(\d+)\s*的旅程進度。$",
     {"EN": "Load the journey in slot {1}.", "JA": "スロット{1}の冒険を読み込む。", "KO": "슬롯 {1}의 여정을 불러옵니다."}),
    (r"^旅程進度已寫入存檔槽\s*(\d+)。$",
     {"EN": "Journey saved to slot {1}.", "JA": "冒険をスロット{1}に保存しました。", "KO": "여정을 슬롯 {1}에 저장했습니다."}),
    (r"^存檔槽\s*(\d+)\s*已損毀，無法讀取。$",
     {"EN": "Save slot {1} is corrupted and cannot be loaded.", "JA": "セーブ枠{1}は破損しており読み込めません。", "KO": "저장 슬롯 {1}이(가) 손상되어 불러올 수 없습니다."}),
    (r"^存檔失敗：無法寫入存檔槽\s*(\d+)。$",
     {"EN": "Save failed: could not write slot {1}.", "JA": "セーブ失敗:スロット{1}に書き込めません。", "KO": "저장 실패: 슬롯 {1}에 기록할 수 없습니다."}),
    (r"^冷卻\s*(\d+)\s*回合$",
     {"EN": "Cooldown: {1} turns", "JA": "クールダウン: {1}ターン", "KO": "재사용 대기: {1}턴"}),
    (r"^(.+)（已使用）$",
     {"EN": "[1] (USED)", "JA": "[1](使用済み)", "KO": "[1] (사용됨)"}),
    (r"^(.+)（生效中）$",
     {"EN": "[1] (ACTIVE)", "JA": "[1](発動中)", "KO": "[1] (발동 중)"}),
    (r"^(.+)\s+已用$",
     {"EN": "[1] — USED", "JA": "[1] — 使用済み", "KO": "[1] — 사용됨"}),
    (r"^(.+)\s+生效中$",
     {"EN": "[1] — ACTIVE", "JA": "[1] — 発動中", "KO": "[1] — 발동 중"}),
    (r"^(.+)天賦$",
     {"EN": "[1] TALENTS", "JA": "[1]の才能", "KO": "[1] 특성"}),
    (r"^(.+)倒在了冒險途中。$",
     {"EN": "[1] fell on the journey.", "JA": "[1]は冒険の途中で倒れた。", "KO": "[1]이(가) 모험 도중 쓰러졌다."}),
    (r"^(.+)擊敗(.+)，王城終於迎回黎明！$",
     {"EN": "[1] defeated [2]. Dawn returns to the royal city!", "JA": "[1]が[2]を倒し、王都についに夜明けが訪れた!", "KO": "[1]이(가) [2]을(를) 물리치고 왕성에 마침내 새벽이 찾아왔다!"}),
    (r"^(.+)出現了。它偏向(.+)，準備攻擊你。$",
     {"EN": "[1] appears. This [2] foe prepares to attack.", "JA": "[1]が現れた。[2]型で、攻撃を仕掛けてくる。", "KO": "[1]이(가) 나타났다. [2]형이며 공격을 준비한다."}),
    (r"^(.+)倒下，你搜出\s*(\d+)G。$",
     {"EN": "[1] falls. You loot {2} Gold.", "JA": "[1]が倒れ、{2}Gを手に入れた。", "KO": "[1]이(가) 쓰러지고 {2}G를 얻었다."}),
    (r"^(.+)受到(.+)傷害\s*(\d+)\s*點。$",
     {"EN": "[1] immediately takes {3} [2] damage.", "JA": "[1]は即座に{3}の[2]ダメージを受けた。", "KO": "[1]이(가) 즉시 {3}의 [2] 피해를 받았다."}),
    (r"^(.+)的護盾擋下\s*(\d+)\s*點傷害。$",
     {"EN": "[1]'s Shield absorbs {2} damage.", "JA": "[1]のシールドが{2}ダメージを防いだ。", "KO": "[1]의 보호막이 {2} 피해를 막았다."}),
    (r"^你對\s*(.+)\s*造成\s*(\d+)\s*點傷害。$",
     {"EN": "You deal {2} damage to [1].", "JA": "[1]に{2}のダメージを与えた。", "KO": "[1]에게 {2}의 피해를 입혔다."}),
    (r"^(.+)\s*對你造成\s*(\d+)\s*點傷害。$",
     {"EN": "[1] deals {2} damage to you.", "JA": "[1]から{2}のダメージを受けた。", "KO": "[1](으)로부터 {2}의 피해를 받았다."}),
    (r"^你施放(.+)，獲得\s*(\d+)\s*點護盾。$",
     {"EN": "You cast [1] and gain {2} Shield.", "JA": "[1]を唱え、{2}のシールドを得た。", "KO": "[1]을(를) 시전해 {2}의 보호막을 얻었다."}),
    (r"^獲得\s*(\d+)\s*點護盾。?$",
     {"EN": "Gain {1} Shield.", "JA": "{1}のシールドを得た。", "KO": "{1}의 보호막을 얻었다."}),
    (r"^恢復\s*(\d+)\s*點血量。?$",
     {"EN": "Restore {1} HP.", "JA": "{1} HPを回復した。", "KO": "{1} HP를 회복했다."}),
    (r"^造成\s*(\d+)\s*點傷害。?$",
     {"EN": "Deal {1} damage.", "JA": "{1}のダメージを与えた。", "KO": "{1}의 피해를 입혔다."}),
    (r"^護盾\s*\+\s*(\d+)$",
     {"EN": "Shield +{1}", "JA": "シールド +{1}", "KO": "보호막 +{1}"}),
    (r"^金幣\s*\+\s*(\d+)G?$",
     {"EN": "Gold +{1}", "JA": "ゴールド +{1}", "KO": "골드 +{1}"}),
    (r"^藥水\s*x\s*(\d+)$",
     {"EN": "Potions ×{1}", "JA": "ポーション ×{1}", "KO": "물약 ×{1}"}),
    (r"^(攻擊|防禦|暴擊|血量上限|目前血量|金幣|藥水)\s*([+-])\s*(\d+)(G|%)?$",
     {"EN": "[1] {2}{3}{4}", "JA": "[1] {2}{3}{4}", "KO": "[1] {2}{3}{4}"}),
    (r"^(\d+)點：(.+)$",
     {"EN": "Rank {1}: [2]", "JA": "{1}ランク: [2]", "KO": "{1}랭크: [2]"}),
)

_DYNAMIC_SPECS = tuple(
    (re.compile(pattern), outputs) for pattern, outputs in _DYNAMIC_SPECS_RAW
)


def _render_dynamic(match: re.Match[str], template: str, locale: str) -> str:
    def raw(m: re.Match[str]) -> str:
        return match.group(int(m.group(1))) or ""

    def translated(m: re.Match[str]) -> str:
        return _tr(locale, (match.group(int(m.group(1))) or "").strip())

    result = re.sub(r"\[(\d+)\]", translated, template)
    result = re.sub(r"\{(\d+)\}", raw, result)
    return result


def _translate_dynamic(text: str, locale: str) -> str | None:
    for pattern, outputs in _DYNAMIC_SPECS:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        template = outputs.get(locale)
        if template is None:
            return None  # No output for this locale → fall back to source.
        return _render_dynamic(match, template, locale)
    return None


# ---------------------------------------------------------------------------
# English-only free phrase composition (kept for English's generated text).
# ---------------------------------------------------------------------------
def _en_phrase_map() -> dict[str, str]:
    return {**_CATALOGS.get("EN", {}), **_EN_PHRASES_EXTRA}


_PUNCTUATION = str.maketrans({
    "，": ", ", "。": ".", "；": "; ", "：": ": ",
    "（": " (", "）": ")", "「": '"', "」": '"',
    "、": ", ", "｜": " | ", "・": " · ", "！": "!", "？": "?",
})


def _build_phrase_list() -> tuple[tuple[str, str], ...]:
    phrases = _en_phrase_map()
    exact_only = {source for source in phrases if len(source.strip()) <= 1}
    exact_only.update({"關", "開", "攻", "防", "守", "戰", "旅", "市"})
    trimmed = {k: v for k, v in phrases.items() if k not in exact_only}
    return tuple(sorted(trimmed.items(), key=lambda item: len(item[0]), reverse=True))


_PHRASE_TRANSLATIONS = _build_phrase_list()


def _en_compose(core: str) -> str:
    result = core
    for source, target in _PHRASE_TRANSLATIONS:
        if source in result:
            result = result.replace(source, target)
    result = result.translate(_PUNCTUATION)
    result = re.sub(
        r"\b(unlock|gain|deal|restore|apply|extend|suppress|spend|sacrifice)(?=[A-Z0-9])",
        r"\1 ", result, flags=re.IGNORECASE,
    )
    result = re.sub(r"\b1\s+turn\(s\)", "1 turn", result)
    result = result.replace("turn(s)", "turns").replace("time(s)", "times")
    result = result.replace("point(s)", "points").replace("stack(s)", "stacks")
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r" {2,}", " ", result).strip()
    return result


# ---------------------------------------------------------------------------
# Core per-locale translation.
# ---------------------------------------------------------------------------
def _to_simplified(text: str) -> str:
    override = _CATALOGS.get("zh-CN", {}).get(text)
    if override is not None:
        return override
    if zhconv is None:
        return text
    return zhconv.convert(text, "zh-hans")


def _translate_for(locale: str, text: str) -> str:
    """Translate one string into ``locale`` (uncached; recursion goes via _tr)."""
    if locale == SOURCE_LOCALE:
        return text
    if locale == "zh-CN":
        return _to_simplified(text)

    catalog = _CATALOGS.get(locale, {})
    if text in catalog:
        return catalog[text]
    if not _CJK_RE.search(text):
        return text

    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    core = text.strip()
    if core in catalog:
        return leading + catalog[core] + trailing

    template = _translate_template(core, locale)
    if template is not None:
        return leading + template + trailing

    dynamic = _translate_dynamic(core, locale)
    if dynamic is not None:
        return leading + dynamic + trailing

    if locale == "EN":
        return leading + _en_compose(core) + trailing

    # JA / KO / mod locales: no fragment composition — keep the source safely.
    return text


@lru_cache(maxsize=_TRANSLATION_CACHE_SIZE)
def _translate_string_cached(locale: str, catalog_generation: int, text: str) -> str:
    return _translate_for(locale, text)


def _tr(locale: str, text: str) -> str:
    """Cached recursion helper for templates/dynamic capture groups."""
    return _translate_string_cached(locale, _CATALOG_GENERATION, text)


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------
def _normalize_locale(locale: str) -> str:
    normalized = _canonical_locale(locale)
    if normalized not in SUPPORTED_LOCALES:
        raise ValueError(
            f"Unsupported locale {locale!r}; expected one of {SUPPORTED_LOCALES!r}"
        )
    return normalized


def set_locale(locale: str) -> str:
    global _locale
    _locale = _normalize_locale(locale)
    return _locale


def get_locale() -> str:
    return _locale


def translation_cache_info() -> Any:
    return _translate_string_cached.cache_info()


def clear_translation_cache() -> None:
    _translate_string_cached.cache_clear()


def bump_catalog_generation() -> int:
    global _CATALOG_GENERATION
    _CATALOG_GENERATION += 1
    clear_translation_cache()
    return _CATALOG_GENERATION


def reload_catalogs() -> tuple[str, ...]:
    """Re-read every ``Localization/*.json`` (hot reload for modders/testing)."""
    global _LOCALE_TEMPLATES, _PHRASE_TRANSLATIONS, SUPPORTED_LOCALES
    _discover_catalogs()
    _LOCALE_TEMPLATES = _build_all_templates()
    _PHRASE_TRANSLATIONS = _build_phrase_list()
    SUPPORTED_LOCALES = _supported_locales()
    bump_catalog_generation()
    return SUPPORTED_LOCALES


def translate(value: Any, locale: str | None = None) -> Any:
    target = _locale if locale is None else _normalize_locale(locale)
    if target == SOURCE_LOCALE:
        return value
    if isinstance(value, str):
        return _translate_string_cached(target, _CATALOG_GENERATION, value)
    if isinstance(value, Mapping):
        return {key: translate(item, target) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(translate(item, target) for item in value)
    if isinstance(value, list):
        return [translate(item, target) for item in value]
    if isinstance(value, set):
        return {translate(item, target) for item in value}
    return value


t = translate


__all__ = (
    "DEFAULT_LOCALE", "SOURCE_LOCALE", "SUPPORTED_LOCALES", "LOCALIZATION_DIR",
    "set_locale", "get_locale", "translate", "t", "reload_catalogs",
    "translation_cache_info", "clear_translation_cache", "bump_catalog_generation",
)
