"""Localization equivalence, coverage, and bounded-cache regression checks."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import localization  # noqa: E402


SOURCE_FILES = (
    "rpg.py",
    "rpg_drawing.py",
    "mage.py",
    "warrior.py",
    "paladin.py",
    "rogue.py",
    "warlock.py",
    "combat_intents.py",
    "encounter_modifiers.py",
    "replay_variation.py",
)
# Cover radicals, CJK symbols, unified ideographs, and compatibility
# ideographs.  The old range missed characters such as compatibility glyphs,
# allowing an English render to pass while still displaying Chinese text.
CJK = re.compile(r"[\u2e80-\u2fff\u3400-\u9fff\uf900-\ufaff]")

# Representative values that are commonly interpolated into UI strings.  A
# numeric-only replacement checks the surrounding f-string grammar, but cannot
# prove that recursively inserted Chinese values are localized as well.
INTERPOLATION_SAMPLES = ("2", "符文骸骨巨將", "戰士", "第一層", "斬擊", "補血藥水")
NUMERIC_FIELD_HINTS = (
    "amount", "attack", "block", "bonus", "chance", "cooldown", "count", "critical", "damage",
    "defense", "gold", "heal", "hp", "index", "level", "lv", "max_",
    "multiplier", "point", "price", "rank", "slot", "stage", "stacks",
    "total", "turn", "value",
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    result: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            result.add(id(first.value))
    return result


def _render_joined_string(node: ast.JoinedStr, placeholder: str = "2") -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            expression = ast.unparse(value.value).lower()
            numeric = any(hint in expression for hint in NUMERIC_FIELD_HINTS)
            parts.append("2" if numeric else placeholder)
    return "".join(parts)


def _source_samples() -> tuple[list[str], list[str]]:
    standalone: list[str] = []
    rendered_fstrings: list[str] = []
    for relative_path in SOURCE_FILES:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        docs = _docstring_ids(tree)
        joined = [node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)]
        joined_descendants = {
            id(descendant)
            for node in joined
            for descendant in ast.walk(node)
        }
        standalone.extend(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and CJK.search(node.value)
            and id(node) not in docs
            and id(node) not in joined_descendants
        )
        rendered_fstrings.extend(
            rendered
            for node in joined
            for placeholder in INTERPOLATION_SAMPLES
            if CJK.search(rendered := _render_joined_string(node, placeholder))
        )
    return standalone, rendered_fstrings


def _template_samples() -> list[str]:
    return [
        re.sub(r"\{[^{}]+\}", "2", source)
        for source in localization.EN
        if "{" in source and "}" in source
    ]


def _assert_equivalent_without_residual(samples: list[str], label: str) -> None:
    for source in samples:
        expected = localization._translate_text_uncached(source)
        actual = localization.translate(source, "EN")
        assert actual == expected, (label, source, expected, actual)
        assert not CJK.search(actual), (label, source, actual)


def _assert_catalog_has_no_residual() -> None:
    for source, target in localization.EN.items():
        assert not CJK.search(target), ("catalog-target", source, target)
    for source, target in localization._PHRASE_TRANSLATIONS:
        assert not CJK.search(target), ("phrase-target", source, target)


def _assert_cache_contract() -> None:
    localization.clear_translation_cache()
    initial = localization.translation_cache_info()
    assert initial.maxsize == 8192 and initial.currsize == 0

    assert localization.translate("攻擊", "EN") == "ATTACK"
    after_miss = localization.translation_cache_info()
    assert after_miss.misses == 1 and after_miss.hits == 0
    assert localization.translate("攻擊", "EN") == "ATTACK"
    after_hit = localization.translation_cache_info()
    assert after_hit.misses == 1 and after_hit.hits == 1

    original = ["攻擊", {"stat": "防禦"}]
    assert localization.translate(original, "zh-TW") is original
    translated = localization.translate(original, "EN")
    translated[0] = "mutated"
    translated[1]["stat"] = "mutated"
    assert localization.translate(original, "EN") == [
        "ATTACK", {"stat": "DEFENSE"}
    ]

    previous_generation = localization._CATALOG_GENERATION
    assert localization.bump_catalog_generation() == previous_generation + 1
    assert localization.translation_cache_info().currsize == 0
    assert localization.translate("攻擊", "EN") == "ATTACK"
    assert localization.translation_cache_info().misses == 1

    localization.clear_translation_cache()
    for index in range(8200):
        localization.translate(f"cache-boundary-{index}", "EN")
    bounded = localization.translation_cache_info()
    assert bounded.currsize == bounded.maxsize == 8192


def main() -> None:
    standalone, rendered_fstrings = _source_samples()
    templates = _template_samples()
    # Production refactors legitimately add/remove source literals. Guard the
    # breadth of the audit without coupling the test to an exact AST count.
    assert len(standalone) >= 1100, len(standalone)
    assert len(rendered_fstrings) >= 200, len(rendered_fstrings)
    assert len(templates) >= 140, len(templates)

    _assert_equivalent_without_residual(standalone, "literal")
    _assert_equivalent_without_residual(rendered_fstrings, "f-string")
    _assert_equivalent_without_residual(templates, "template")
    _assert_catalog_has_no_residual()
    _assert_cache_contract()

    print(
        "literal/f-string/template coverage: "
        f"{len(standalone)}/{len(rendered_fstrings)}/{len(templates)}"
    )
    print(f"cache: {localization.translation_cache_info()}")


if __name__ == "__main__":
    main()
