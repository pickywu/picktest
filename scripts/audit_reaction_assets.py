"""Validate and render side-by-side QA sheets for hurt/block character art."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


POSES = ("hurt", "block")
PLAYER_ROOT = Path("assets/characters/players/tier_1")
MONSTER_ROOT = Path("assets/characters/monsters")


def expected_player_assets(root: Path) -> Iterable[tuple[str, Path, Path, Path]]:
    idle_root = root / "idle"
    for idle in sorted(idle_root.glob("*/*/*.png")):
        sex, race, filename = idle.relative_to(idle_root).parts
        identity = f"{sex}/{race}/{Path(filename).stem}"
        yield (
            identity,
            idle,
            root / "hurt" / sex / race / filename,
            root / "block" / sex / race / filename,
        )


def expected_monster_assets(root: Path) -> Iterable[tuple[str, Path, Path, Path]]:
    for idle in sorted(root.glob("rank_*/idle/*.png")):
        rank, _pose, filename = idle.relative_to(root).parts
        identity = f"{rank}/{Path(filename).stem}"
        yield (
            identity,
            idle,
            root / rank / "hurt" / filename,
            root / rank / "block" / filename,
        )


def inspect_reaction(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"path": path.as_posix(), "status": "missing"}
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        corners = (
            alpha.getpixel((0, 0)),
            alpha.getpixel((rgba.width - 1, 0)),
            alpha.getpixel((0, rgba.height - 1)),
            alpha.getpixel((rgba.width - 1, rgba.height - 1)),
        )
        errors: list[str] = []
        if image.mode != "RGBA":
            errors.append(f"mode={image.mode}")
        if image.size != (1024, 1024):
            errors.append(f"canvas={image.size}")
        if bbox is None:
            errors.append("empty-alpha")
        else:
            if not 960 <= bbox[3] <= 974:
                errors.append(f"foot-y={bbox[3] - 1}")
            if bbox[0] < 3 or bbox[1] < 3 or bbox[2] > 1021:
                errors.append(f"edge-clipping={bbox}")
        if any(corners):
            errors.append(f"opaque-corners={corners}")
        return {
            "path": path.as_posix(),
            "status": "pass" if not errors else "fail",
            "mode": image.mode,
            "canvas": list(image.size),
            "alpha_bbox": list(bbox) if bbox else None,
            "errors": errors,
        }


def thumbnail(path: Path, size: int) -> Image.Image:
    if not path.is_file():
        tile = Image.new("RGBA", (size, size), (35, 20, 24, 255))
        ImageDraw.Draw(tile).text((12, size // 2), "MISSING", fill=(255, 110, 110, 255))
        return tile
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        rgba.thumbnail((size - 12, size - 12), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (size, size), (18, 18, 22, 255))
        tile.alpha_composite(rgba, ((size - rgba.width) // 2, size - rgba.height - 6))
        return tile


def write_sheet(rows: list[tuple[str, Path, Path, Path]], output: Path) -> None:
    tile_size, label_height = 240, 28
    width = tile_size * 3
    height = (tile_size + label_height) * len(rows)
    sheet = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    for row_index, (identity, idle, hurt, block) in enumerate(rows):
        y = row_index * (tile_size + label_height)
        for column, path in enumerate((idle, hurt, block)):
            sheet.paste(thumbnail(path, tile_size).convert("RGB"), (column * tile_size, y))
        draw.text(
            (8, y + tile_size + 6),
            f"{identity}   idle | hurt | block",
            fill=(240, 226, 190),
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/reaction_asset_audit"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    player_rows = list(expected_player_assets(PLAYER_ROOT))
    monster_rows = list(expected_monster_assets(MONSTER_ROOT))
    records: list[dict[str, object]] = []
    for category, rows in (("player", player_rows), ("monster", monster_rows)):
        for identity, _idle, hurt, block in rows:
            records.append(
                {
                    "category": category,
                    "identity": identity,
                    "hurt": inspect_reaction(hurt),
                    "block": inspect_reaction(block),
                }
            )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "report.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_sheet([row for row in player_rows if row[0].startswith("male/")],
                args.out_dir / "players_male.jpg")
    write_sheet([row for row in player_rows if row[0].startswith("female/")],
                args.out_dir / "players_female.jpg")
    write_sheet(monster_rows, args.out_dir / "monsters.jpg")

    failed = [
        (record["identity"], pose, record[pose]["status"])
        for record in records
        for pose in POSES
        if record[pose]["status"] != "pass"
    ]
    passed = len(records) * len(POSES) - len(failed)
    print(f"reaction assets: {passed}/{len(records) * len(POSES)} pass")
    for identity, pose, status in failed:
        print(f"{status}: {identity}/{pose}")
    if args.strict and failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
