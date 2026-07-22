from __future__ import annotations

import unittest
from unittest.mock import patch

from rpg_drawing import RPGDrawingMixin


class EnglishLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.drawing = object.__new__(RPGDrawingMixin)
        self.drawing.display_text = lambda value: str(value)
        # A deterministic width model is sufficient for testing the wrapping
        # contract without creating a GL window or depending on installed fonts.
        self.drawing.measure_text_width = (
            lambda value, size=11, bold=False: len(str(value)) * size
        )

    def test_latin_units_only_break_at_whitespace(self) -> None:
        text = "Red-Sac Marsh/Toad can't use life-drain—yet."
        self.assertEqual(
            RPGDrawingMixin._latin_break_units(text),
            ["Red-Sac", " Marsh/Toad", " can't", " use",
             " life-drain—yet."],
        )

    def test_english_wrap_never_splits_words(self) -> None:
        source = "A dead branch snaps beside the road. Something approaches."
        with patch("rpg_drawing.get_locale", return_value="EN"):
            lines = self.drawing.wrap_text_pixels(source, 145, 5)

        self.assertEqual(" ".join(lines), source)
        source_words = source.split()
        wrapped_words = [word for line in lines for word in line.split()]
        self.assertEqual(wrapped_words, source_words)

    def test_fitted_wrapping_keeps_all_content(self) -> None:
        source = (
            "Spend 3 points in each tier to unlock the next. "
            "The final tier requires only 1 point."
        )
        with patch("rpg_drawing.get_locale", return_value="EN"):
            lines, fitted_size = self.drawing.fitted_wrapped_lines(
                source, 420, 14, min_size=12, max_lines=3
            )

        self.assertGreaterEqual(fitted_size, 12)
        self.assertEqual(" ".join(lines), source)

    def test_status_rows_pack_by_width_without_dropping_labels(self) -> None:
        values = ["CORRUPTION 12x3", "GUARANTEED CRIT", "REFLECT"]
        lines = self.drawing.pack_status_lines(values, 180, 5, " | ")

        self.assertGreater(len(lines), 1)
        self.assertEqual(" | ".join(lines), " | ".join(values))


if __name__ == "__main__":
    unittest.main()
