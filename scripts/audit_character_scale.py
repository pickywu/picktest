"""Generate alpha-bound diagnostics for character-scale QA.

The contact sheet deliberately fits each sprite by its complete alpha bounds.
It therefore includes weapons, shields, spell effects, and trailing cloth and is
not a canonical measurement of body scale.  Runtime scale decisions must use
the reviewed body-landmark manifest instead.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw


JOBS = ("mage", "paladin", "rogue", "warlock", "warrior")
RACES = ("elf", "orc", "human", "dwarf")
SEXES = ("male", "female")
RACE_HEIGHT = {"elf": 1.00, "orc": 0.97, "human": 0.93, "dwarf": 0.78}


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    rgba = image.convert("RGBA")
    return rgba.getchannel("A").getbbox() or (0, 0, *rgba.size)


def write_metrics(root: Path, output: Path) -> None:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.png")):
        with Image.open(path) as image:
            box = alpha_bbox(image)
            rows.append(
                {
                    "path": path.as_posix(),
                    "canvas_width": image.width,
                    "canvas_height": image.height,
                    "mode": image.mode,
                    "left": box[0],
                    "top": box[1],
                    "right": box[2],
                    "bottom": box[3],
                    "visible_width": box[2] - box[0],
                    "visible_height": box[3] - box[1],
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_idle_alpha_diagnostic(players_root: Path, output: Path) -> None:
    cell_width, cell_height = 300, 330
    label_height, baseline = 28, 315
    sheet = Image.new("RGBA", (cell_width * len(JOBS), cell_height * 8), (18, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    for row, (sex, race) in enumerate((s, r) for s in SEXES for r in RACES):
        target_height = round(270 * RACE_HEIGHT[race])
        for col, job in enumerate(JOBS):
            path = players_root / "idle" / sex / race / f"{job}.png"
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
                box = alpha_bbox(rgba)
                tight = rgba.crop(box)
                scale = target_height / max(1, tight.height)
                scale = min(scale, 282 / max(1, tight.width))
                resized = tight.resize(
                    (max(1, round(tight.width * scale)), max(1, round(tight.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            x0 = col * cell_width
            y0 = row * cell_height
            x = x0 + (cell_width - resized.width) // 2
            y = y0 + baseline - resized.height
            sheet.alpha_composite(resized, (x, y))
            draw.text((x0 + 8, y0 + 7), f"{sex} {race} {job}", fill=(245, 230, 190, 255))
            draw.line((x0, y0 + baseline, x0 + cell_width, y0 + baseline), fill=(100, 100, 110, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("assets/characters"))
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/character_scale_audit"))
    args = parser.parse_args()
    write_metrics(args.root, args.out_dir / "metrics.csv")
    write_idle_alpha_diagnostic(
        args.root / "players" / "tier_1",
        args.out_dir / "idle_alpha_bbox_diagnostic.jpg",
    )


if __name__ == "__main__":
    main()
