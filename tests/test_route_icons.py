from pathlib import Path
import unittest

from PIL import Image

from route_map import NodeKind
from rpg_drawing import ROUTE_KIND_ICON_ASSETS


ROOT = Path(__file__).resolve().parents[1]


class RouteIconTests(unittest.TestCase):
    def test_every_route_kind_has_one_transparent_icon(self) -> None:
        self.assertEqual(
            set(ROUTE_KIND_ICON_ASSETS),
            {kind.value for kind in NodeKind},
        )
        self.assertEqual(
            len(set(ROUTE_KIND_ICON_ASSETS.values())),
            len(NodeKind),
        )
        for kind, relative_path in ROUTE_KIND_ICON_ASSETS.items():
            with self.subTest(kind=kind):
                path = ROOT / "assets" / "ui" / relative_path
                self.assertTrue(path.is_file(), path)
                with Image.open(path) as icon:
                    self.assertEqual(icon.size, (256, 256))
                    self.assertEqual(icon.mode, "RGBA")
                    self.assertEqual(icon.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
