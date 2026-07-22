from __future__ import annotations

from unittest.mock import patch

import localization
import rpg_drawing


class _FakeZhconv:
    """Small deterministic stand-in; the real package is optional in CI."""

    @staticmethod
    def convert(text: str, profile: str) -> str:
        assert profile == "zh-hans"
        return text.translate(str.maketrans({
            "攻": "攻",
            "擊": "击",
            "護": "护",
            "藥": "药",
            "勝": "胜",
            "與": "与",
        }))


def test_zh_cn_uses_converter_when_available() -> None:
    source = "攻擊、護盾、藥水與勝利。"
    with (
        patch.object(localization, "zhconv", _FakeZhconv),
        patch.object(
            localization,
            "SUPPORTED_LOCALES",
            tuple(dict.fromkeys((*localization.SUPPORTED_LOCALES, "zh-CN"))),
        ),
    ):
        localization.clear_translation_cache()
        assert localization.translate(source, "zh-CN") == "攻击、护盾、药水与胜利。"
    localization.clear_translation_cache()


def test_simplified_chinese_aliases_normalize_to_zh_cn() -> None:
    aliases = ("zh-CN", "zh_cn", "zh-Hans", "zh-CHS", "cn")
    with patch.object(
        localization,
        "SUPPORTED_LOCALES",
        tuple(dict.fromkeys((*localization.SUPPORTED_LOCALES, "zh-CN"))),
    ):
        assert {localization._normalize_locale(alias) for alias in aliases} == {"zh-CN"}


def test_missing_converter_does_not_advertise_fake_zh_cn() -> None:
    # zh-CN.json is intentionally an empty override catalog.  Without the
    # converter, exposing CN in the picker would silently return Traditional
    # Chinese for every string while pretending the locale is available.
    assert localization._CATALOGS.get("zh-CN") == {}
    with patch.object(localization, "zhconv", None):
        assert "zh-CN" not in localization._supported_locales()


def test_zh_cn_prefers_a_distinct_lightweight_serif_font() -> None:
    """Simplified Chinese must not default to the heavier YaHei UI face."""
    with patch.object(rpg_drawing, "get_locale", return_value="zh-CN"):
        simplified_stack = rpg_drawing.current_font_stack()
    with patch.object(rpg_drawing, "get_locale", return_value="zh-TW"):
        traditional_stack = rpg_drawing.current_font_stack()

    preferred = simplified_stack[0]
    assert preferred != "Microsoft YaHei"
    assert preferred != traditional_stack[0]
    assert "Light" in preferred or "Serif" in preferred, (
        "zh-CN should prefer an explicitly light or serif family; "
        f"got {preferred!r}"
    )
