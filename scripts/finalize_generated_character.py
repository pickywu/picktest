"""Remove chroma, normalize a generated sprite, validate it, and record progress."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image


CANVAS_SIZE = 1024
FOOT_BOTTOM = 968  # Alpha bbox is exclusive; last visible row is y=967.
SIDE_MARGIN = 28
TOP_MARGIN = 28


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_chroma(source: Path, alpha_path: Path, helper: Path) -> None:
    alpha_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(helper),
            "--input", str(source),
            "--out", str(alpha_path),
            "--auto-key", "border",
            "--soft-matte",
            "--transparent-threshold", "12",
            "--opaque-threshold", "220",
            "--despill",
        ],
        check=True,
    )


def normalize(alpha_path: Path, output: Path) -> dict[str, object]:
    with Image.open(alpha_path) as image:
        rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError(f"No visible subject after chroma removal: {alpha_path}")
    subject = rgba.crop(bbox)
    max_width = CANVAS_SIZE - SIDE_MARGIN * 2
    max_height = FOOT_BOTTOM - TOP_MARGIN
    scale = min(max_width / subject.width, max_height / subject.height)
    size = (
        max(1, round(subject.width * scale)),
        max(1, round(subject.height * scale)),
    )
    subject = subject.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    x = (CANVAS_SIZE - subject.width) // 2
    y = FOOT_BOTTOM - subject.height
    canvas.alpha_composite(subject, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)

    final_alpha = canvas.getchannel("A")
    final_bbox = final_alpha.getbbox()
    if final_bbox is None:
        raise ValueError(f"Final sprite is empty: {output}")
    corners = [
        final_alpha.getpixel((0, 0)),
        final_alpha.getpixel((CANVAS_SIZE - 1, 0)),
        final_alpha.getpixel((0, CANVAS_SIZE - 1)),
        final_alpha.getpixel((CANVAS_SIZE - 1, CANVAS_SIZE - 1)),
    ]
    if any(corners):
        raise ValueError(f"Final sprite corners are not transparent: {output}")
    if final_bbox[3] != FOOT_BOTTOM:
        raise ValueError(f"Final foot bottom is {final_bbox[3]}, expected {FOOT_BOTTOM}")

    magenta_fringe = 0
    green_fringe = 0
    for red, green, blue, value in canvas.getdata():
        if value <= 20:
            continue
        magenta_fringe += int(red > 180 and blue > 150 and green < 100)
        green_fringe += int(green > 180 and red < 100 and blue < 100)
    return {
        "mode": canvas.mode,
        "canvas": list(canvas.size),
        "alpha_bbox": list(final_bbox),
        "last_visible_y": final_bbox[3] - 1,
        "transparent_corners": corners,
        "magenta_fringe_pixels": magenta_fringe,
        "green_fringe_pixels": green_fringe,
        "sha256": sha256(output),
    }


def update_progress(progress_path: Path, identity: str, action: str,
                    source: Path, output: Path, prompt_id: str,
                    validation: dict[str, object]) -> None:
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"schema_version": 1, "characters": {}}
    character = progress["characters"].setdefault(identity, {})
    character[action] = {
        "status": "complete",
        "generated_source": str(source),
        "output": output.as_posix(),
        "prompt_id": prompt_id,
        "validation": validation,
    }
    completed = sum(
        1
        for actions in progress["characters"].values()
        for record in actions.values()
        if record.get("status") in {"complete", "complete_root"}
    )
    progress["completed_assets"] = completed
    progress["failed_assets"] = sum(
        1
        for actions in progress["characters"].values()
        for record in actions.values()
        if record.get("status") == "failed"
    )
    progress["target_assets"] = 40
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def record_failure(progress_path: Path, identity: str, action: str,
                   source: Path, prompt_id: str, reason: str) -> None:
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"schema_version": 1, "characters": {}}
    character = progress["characters"].setdefault(identity, {})
    character[action] = {
        "status": "failed",
        "generated_source": str(source),
        "prompt_id": prompt_id,
        "failure_reason": reason,
    }
    progress["completed_assets"] = sum(
        1 for actions in progress["characters"].values()
        for record in actions.values()
        if record.get("status") in {"complete", "complete_root"}
    )
    progress["failed_assets"] = sum(
        1 for actions in progress["characters"].values()
        for record in actions.values() if record.get("status") == "failed"
    )
    progress["target_assets"] = 40
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def record_delegation(progress_path: Path, identity: str, action: str,
                      status: str = "delegated_root") -> None:
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"schema_version": 1, "characters": {}}
    character = progress["characters"].setdefault(identity, {})
    character[action] = {"status": status}
    progress["completed_assets"] = sum(
        1 for actions in progress["characters"].values()
        for record in actions.values()
        if record.get("status") in {"complete", "complete_root"}
    )
    progress["failed_assets"] = sum(
        1 for actions in progress["characters"].values()
        for record in actions.values() if record.get("status") == "failed"
    )
    progress["target_assets"] = 40
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--action", choices=("hurt", "block"), required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--failure-reason")
    parser.add_argument("--delegated-root", action="store_true")
    parser.add_argument("--complete-root", action="store_true")
    parser.add_argument(
        "--progress", type=Path,
        default=Path("tmp/imagegen/player_female_progress.json"),
    )
    parser.add_argument(
        "--chroma-helper", type=Path,
        default=(
            Path.home() / ".codex" / "skills" / ".system" / "imagegen"
            / "scripts" / "remove_chroma_key.py"
        ),
    )
    args = parser.parse_args()
    if args.delegated_root or args.complete_root:
        status = "complete_root" if args.complete_root else "delegated_root"
        record_delegation(args.progress, args.identity, args.action, status)
        print(f"Recorded {status} asset: {args.identity}/{args.action}")
        return
    if args.failure_reason:
        if args.source is None:
            parser.error("--source is required with --failure-reason")
        record_failure(
            args.progress, args.identity, args.action, args.source,
            args.prompt_id, args.failure_reason,
        )
        print(f"Recorded failed asset: {args.identity}/{args.action}")
        return
    if args.output is None:
        parser.error("--output is required unless --failure-reason is provided")
    if args.source is None:
        parser.error("--source is required unless --delegated-root is provided")
    alpha_path = (
        Path("tmp/imagegen/female_alpha")
        / args.action
        / f"{args.identity.replace('/', '_')}.png"
    )
    remove_chroma(args.source, alpha_path, args.chroma_helper)
    validation = normalize(alpha_path, args.output)
    update_progress(
        args.progress, args.identity, args.action,
        args.source, args.output, args.prompt_id, validation,
    )
    print(json.dumps(validation, ensure_ascii=False))


if __name__ == "__main__":
    main()
