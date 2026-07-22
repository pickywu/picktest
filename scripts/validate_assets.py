"""Validate generated runtime images against docs/ASSET_MANIFEST.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "docs" / "ASSET_MANIFEST.json"
ASSET_ROOT = (PROJECT_ROOT / "assets").resolve()


def validate() -> tuple[int, int, list[str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ready = 0
    missing = 0
    errors: list[str] = []

    for entry in manifest["assets"]:
        relative = Path(entry["path"])
        path = (PROJECT_ROOT / relative).resolve()
        if ASSET_ROOT not in path.parents:
            errors.append(f"outside assets directory: {relative.as_posix()}")
            continue
        if not path.is_file():
            missing += 1
            continue
        if path.stat().st_size == 0:
            errors.append(f"empty file: {relative.as_posix()}")
            continue

        try:
            with Image.open(path) as image:
                image.load()
                actual_size = image.size
                mode = image.mode
                corner_alpha = None
                if entry.get("transparent") and "A" in image.getbands():
                    alpha = image.getchannel("A")
                    corners = (
                        alpha.getpixel((0, 0)),
                        alpha.getpixel((image.width - 1, 0)),
                        alpha.getpixel((0, image.height - 1)),
                        alpha.getpixel((image.width - 1, image.height - 1)),
                    )
                    corner_alpha = max(corners)
        except Exception as exc:
            errors.append(f"decode failed: {relative.as_posix()} ({exc})")
            continue

        expected_size = (int(entry["width"]), int(entry["height"]))
        if actual_size != expected_size:
            errors.append(
                f"wrong size: {relative.as_posix()} "
                f"expected={expected_size} actual={actual_size}"
            )
            continue
        if entry.get("transparent") and mode != "RGBA":
            errors.append(f"not RGBA: {relative.as_posix()} mode={mode}")
            continue
        if corner_alpha is not None and corner_alpha > 24:
            errors.append(
                f"opaque corner: {relative.as_posix()} max_alpha={corner_alpha}"
            )
            continue
        ready += 1

    return ready, missing, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing", action="store_true",
        help="report missing files without failing the command",
    )
    args = parser.parse_args()
    ready, missing, errors = validate()
    for message in errors:
        print(f"[INVALID] {message}")
    print(f"ready={ready} missing={missing} invalid={len(errors)}")
    if errors or (missing and not args.allow_missing):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
