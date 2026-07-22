from __future__ import annotations

import json
from pathlib import Path
import unittest

import localization


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ROUTE_KEYS = {
    "小怪", "菁英", "營火", "藥水商", "魔王",
    "一般遭遇；勝利後繼續深入本章。",
    "危險的強敵；勝利後可免費選一瓶藥水。",
    "休整並從數種永久增益中選擇一項。",
    "使用金幣補充本次旅程需要的藥水。",
    "本章最危險的決戰。",
    "已選路線", "目前位置", "節點預覽",
    "第 {chapter} 章", "章節 {chapter}",
    "{chapter_label}｜{prefix}：{kind_label}",
    "{chapter_label}｜選擇下一段路線",
    "將滑鼠移到可前往的節點查看內容；點擊後在下方確認。",
    "前往：{kind}", "請選擇下一個節點", "請先用滑鼠選擇可達節點",
    "前往所選節點", "選擇此旅途節點",
    "菁英戰利品｜免費選擇一瓶藥水", "請先選擇一瓶菁英戰利品",
    "菁英戰利品：獲得{potion} ×1。",
    "營火只能選擇一項；確認後會立即繼續旅程。",
    "持有 {gold}G｜買得起 {affordable}/{total} 種｜本關庫存已鎖定",
    "{stage_text}｜正在展開本章路線……",
    "1．古道", "2．荒野", "3．城郊", "4．城門", "5．王座",
    "目前可前往的章節", "預覽本局已生成的後續分支",
    "回到目前章節", "未來路線預覽",
    "{chapter_label}｜未來路線預覽｜{prefix}：{kind_label}",
    "{chapter_label}｜未來路線預覽｜選擇下一段路線",
    "戰", "菁", "營", "商", "王",
}


class RouteLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        localization.reload_catalogs()

    def test_every_authored_catalog_contains_route_copy(self) -> None:
        for filename in ("en.json", "ja.json", "ko.json"):
            with self.subTest(filename=filename):
                catalog = json.loads(
                    (ROOT / "Localization" / filename).read_text(encoding="utf-8")
                )
                self.assertTrue(REQUIRED_ROUTE_KEYS <= set(catalog))
                for key in REQUIRED_ROUTE_KEYS:
                    self.assertTrue(str(catalog[key]).strip())

    def test_route_templates_translate_rendered_ui_text(self) -> None:
        samples = (
            "第 2 章｜節點預覽：菁英",
            "前往：營火",
            "菁英戰利品：獲得月泉靈藥 ×1。",
            "持有 120G｜買得起 3/6 種｜本關庫存已鎖定",
            "第 4 章｜未來路線預覽｜節點預覽：藥水商",
            "回到目前章節",
            "5．王座",
        )
        for locale in ("EN", "JA", "KO"):
            for source in samples:
                with self.subTest(locale=locale, source=source):
                    translated = localization.translate(source, locale)
                    self.assertNotEqual(translated, source)

    def test_simplified_route_copy_uses_automatic_conversion(self) -> None:
        # zhconv performs script conversion rather than semantic synonym
        # replacement, so 「菁英」 remains 「菁英」 while 「戰」 becomes 「战」.
        self.assertEqual(localization.translate("菁英戰利品", "zh-CN"), "菁英战利品")
        self.assertEqual(localization.translate("請選擇下一個節點", "zh-CN"), "请选择下一个节点")


if __name__ == "__main__":
    unittest.main()
