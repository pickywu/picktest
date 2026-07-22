"""Audit character art and build a body-landmark manifest without rewriting PNGs.

The historical name is intentional: normalization now happens at runtime.  This
tool only measures source art, writes QA reports/contact sheets, and optionally
writes the reviewed JSON manifest consumed by the game.  It never resamples or
overwrites character images.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PLAYER_BODY_HEIGHTS = {"elf": 900, "orc": 873, "human": 837, "dwarf": 702}
REFERENCE_CANVAS = 1024
REFERENCE_FOOT_Y = 968
REACTION_REFERENCE_HEIGHT = 900
ALPHA_THRESHOLD = 12
PLAYER_ROOT_PARTS = ("players", "tier_1")


@dataclass(frozen=True)
class AlphaMetrics:
    canvas_width: int
    canvas_height: int
    mode: str
    bbox: tuple[int, int, int, int]
    anchor_x: int
    opaque_pixels: int

    @property
    def visible_width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def visible_height(self) -> int:
        return self.bbox[3] - self.bbox[1]


@dataclass(frozen=True)
class BodyLandmark:
    top: int
    bottom: int
    left: int
    right: int
    anchor_x: int
    confidence: str

    @property
    def height(self) -> int:
        return self.bottom - self.top


def _alpha_mask(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGBA").getchannel("A")) > ALPHA_THRESHOLD


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("character sprite has no visible alpha pixels")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _weighted_quantile(values: np.ndarray, quantile: float) -> int:
    if not len(values):
        return 0
    return int(np.quantile(values, quantile, method="nearest"))


def _rolling_forward(values: np.ndarray, window: int) -> np.ndarray:
    prefix = np.concatenate(([0], np.cumsum(values, dtype=np.int64)))
    indices = np.arange(len(values))
    ends = np.minimum(len(values), indices + window)
    return prefix[ends] - prefix[indices]


def _mass_anchor_x(mask: np.ndarray, top: int, bottom: int) -> int:
    height = max(1, bottom - top)
    sample_top = top + round(height * 0.16)
    sample_bottom = top + round(height * 0.88)
    _ys, xs = np.nonzero(mask[sample_top:sample_bottom])
    if not len(xs):
        _ys, xs = np.nonzero(mask[top:bottom])
    return _weighted_quantile(xs, 0.50)


def alpha_metrics(image: Image.Image) -> AlphaMetrics:
    mask = _alpha_mask(image)
    box = _bbox(mask)
    return AlphaMetrics(
        canvas_width=image.width,
        canvas_height=image.height,
        mode=image.mode,
        bbox=box,
        anchor_x=_mass_anchor_x(mask, box[1], box[3]),
        opaque_pixels=int(mask.sum()),
    )


def detect_idle_body_landmark(image: Image.Image) -> BodyLandmark:
    """Estimate feet-to-hair bounds while suppressing thin vertical weapons.

    This result is a manifest *proposal*.  Runtime never calls this heuristic;
    the generated overlay must be reviewed before the JSON is promoted.
    """
    mask = _alpha_mask(image)
    left, top, right, bottom = _bbox(mask)
    anchor_x = _mass_anchor_x(mask, top, bottom)
    half_width = max(80, round(image.width * 0.08))
    corridor_left = max(0, anchor_x - half_width)
    corridor_right = min(image.width, anchor_x + half_width + 1)
    row_mass = mask[:, corridor_left:corridor_right].sum(axis=1)
    window = max(32, round((bottom - top) * 0.06))
    forward = _rolling_forward(row_mass, window)
    threshold = max(1, round(float(forward.max(initial=0)) * 0.22))
    candidates = np.nonzero((forward >= threshold) & (row_mass >= 2))[0]
    body_top = int(candidates[0]) if len(candidates) else top

    body_region = mask[body_top:bottom]
    _ys, body_xs = np.nonzero(body_region)
    if len(body_xs):
        # Mass quantiles intentionally discard long, thin weapons and shields.
        body_left = _weighted_quantile(body_xs, 0.04)
        body_right = _weighted_quantile(body_xs, 0.96) + 1
        body_anchor = _weighted_quantile(body_xs, 0.50)
    else:
        body_left, body_right, body_anchor = left, right, anchor_x

    removed_top = body_top - top
    confidence = "review"
    if removed_top == 0 or removed_top >= round((bottom - top) * 0.035):
        confidence = "high"
    return BodyLandmark(
        top=body_top,
        bottom=bottom,
        left=body_left,
        right=body_right,
        anchor_x=body_anchor,
        confidence=confidence,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pose_record(path: Path, image: Image.Image) -> dict[str, Any]:
    metrics = alpha_metrics(image)
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "canvas": [metrics.canvas_width, metrics.canvas_height],
        "mode": metrics.mode,
        "alpha_bbox": list(metrics.bbox),
        "visible_width": metrics.visible_width,
        "visible_height": metrics.visible_height,
        "alpha_bottom_y": metrics.bbox[3],
        "anchor_x": metrics.anchor_x,
        "opaque_pixels": metrics.opaque_pixels,
    }


def _landmark_record(landmark: BodyLandmark) -> dict[str, Any]:
    return {
        "body_top_y": landmark.top,
        "body_bottom_y": landmark.bottom,
        "body_left_x": landmark.left,
        "body_right_x": landmark.right,
        "anchor_x": landmark.anchor_x,
        "body_height": landmark.height,
        "confidence": landmark.confidence,
    }


def build_manifest(root: Path) -> dict[str, Any]:
    players_root = root / "players" / "tier_1"
    monsters_root = root / "monsters"
    players: dict[str, Any] = {}
    for idle_path in sorted((players_root / "idle").glob("*/*/*.png")):
        sex, race, filename = idle_path.relative_to(players_root / "idle").parts
        job = Path(filename).stem
        key = f"{sex}/{race}/{job}"
        with Image.open(idle_path) as image:
            idle_landmark = detect_idle_body_landmark(image)
        poses: dict[str, Any] = {}
        for path in sorted(players_root.glob(f"*/{sex}/{race}/{job}.png")):
            pose = path.relative_to(players_root).parts[0]
            with Image.open(path) as image:
                poses[pose] = _pose_record(path, image)
        players[key] = {
            "sex": sex,
            "race": race,
            "job": job,
            "target_body_height": PLAYER_BODY_HEIGHTS[race],
            "idle_body": _landmark_record(idle_landmark),
            "poses": poses,
        }

    monsters: dict[str, Any] = {}
    for idle_path in sorted(monsters_root.glob("rank_*/idle/*.png")):
        rank, _pose, filename = idle_path.relative_to(monsters_root).parts
        kind = Path(filename).stem
        key = f"{rank}/{kind}"
        with Image.open(idle_path) as image:
            idle_metrics = alpha_metrics(image)
        idle_landmark = BodyLandmark(
            top=idle_metrics.bbox[1],
            bottom=idle_metrics.bbox[3],
            left=idle_metrics.bbox[0],
            right=idle_metrics.bbox[2],
            anchor_x=idle_metrics.anchor_x,
            confidence="paired-alpha-bbox",
        )
        poses: dict[str, Any] = {}
        for path in sorted((monsters_root / rank).glob(f"*/{kind}.png")):
            pose = path.relative_to(monsters_root / rank).parts[0]
            with Image.open(path) as image:
                poses[pose] = _pose_record(path, image)
        monsters[key] = {
            "rank": int(rank.removeprefix("rank_")),
            "kind": kind,
            "idle_body": _landmark_record(idle_landmark),
            "poses": poses,
        }

    return {
        "schema_version": 1,
        "policy": {
            "source_pngs_are_immutable": True,
            "scale_is_uniform_xy": True,
            "scale_source_pose": "idle",
            "pose_ground_alignment": "own_alpha_bottom",
            "reference_canvas": REFERENCE_CANVAS,
            "reference_foot_y": REFERENCE_FOOT_Y,
            "reaction_reference_height": REACTION_REFERENCE_HEIGHT,
            "player_body_height_by_race": PLAYER_BODY_HEIGHTS,
        },
        "players": players,
        "monsters": monsters,
        "excluded_assets": [
            path.as_posix()
            for suffix in ("*_v1.png", "*_v2.png")
            for path in sorted(players_root.rglob(suffix))
        ],
    }


def _audit_rows(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for category in ("players", "monsters"):
        for identity, record in manifest[category].items():
            idle = record["idle_body"]
            for pose, metrics in record["poses"].items():
                box = metrics["alpha_bbox"]
                yield {
                    "category": category,
                    "identity": identity,
                    "pose": pose,
                    "path": metrics["path"],
                    "canvas_width": metrics["canvas"][0],
                    "canvas_height": metrics["canvas"][1],
                    "mode": metrics["mode"],
                    "alpha_left": box[0],
                    "alpha_top": box[1],
                    "alpha_right": box[2],
                    "alpha_bottom": box[3],
                    "visible_width": metrics["visible_width"],
                    "visible_height": metrics["visible_height"],
                    "pose_anchor_x": metrics["anchor_x"],
                    "idle_body_top": idle["body_top_y"],
                    "idle_body_bottom": idle["body_bottom_y"],
                    "idle_body_height": idle["body_height"],
                    "landmark_confidence": idle["confidence"],
                }


def write_audit_csv(manifest: dict[str, Any], path: Path) -> None:
    rows = list(_audit_rows(manifest))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_targets_csv(manifest: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for identity, record in manifest["players"].items():
        idle = record["idle_body"]
        target = int(record["target_body_height"])
        rows.append({
            "identity": identity,
            "race": record["race"],
            "idle_body_height": idle["body_height"],
            "target_body_height_1024": target,
            "uniform_scale_to_reference": target / max(1, idle["body_height"]),
            "confidence": idle["confidence"],
            "poses": ",".join(sorted(record["poses"])),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_player_landmark_sheet(root: Path, manifest: dict[str, Any], path: Path) -> None:
    identities = sorted(manifest["players"])
    tile_width, tile_height = 260, 300
    columns = 5
    rows = (len(identities) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, identity in enumerate(identities):
        record = manifest["players"][identity]
        idle = record["idle_body"]
        pose = record["poses"]["idle"]
        with Image.open(Path(pose["path"])) as source:
            image = source.convert("RGBA")
        image.thumbnail((240, 240), Image.Resampling.LANCZOS)
        tile_x = (index % columns) * tile_width
        tile_y = (index // columns) * tile_height
        image_x = tile_x + (tile_width - image.width) // 2
        image_y = tile_y + 8 + (240 - image.height)
        sheet.paste(image, (image_x, image_y), image)
        sx = image.width / pose["canvas"][0]
        sy = image.height / pose["canvas"][1]
        left = image_x + round(idle["body_left_x"] * sx)
        right = image_x + round(idle["body_right_x"] * sx)
        top = image_y + round(idle["body_top_y"] * sy)
        bottom = image_y + round(idle["body_bottom_y"] * sy)
        anchor = image_x + round(idle["anchor_x"] * sx)
        draw.rectangle((left, top, right, bottom), outline=(0, 240, 255), width=1)
        draw.line((anchor, top, anchor, bottom), fill=(255, 210, 0), width=1)
        label = f"{identity}\nbody={idle['body_height']} conf={idle['confidence']}"
        draw.multiline_text((tile_x + 6, tile_y + 252), label, fill=(240, 240, 240),
                            font=font, spacing=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("assets/characters"))
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/character_scale_audit"))
    parser.add_argument(
        "--write-manifest", type=Path,
        help="Promote the generated proposal to this JSON path after QA review.",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.root)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    proposal = args.out_dir / "body_landmarks.proposed.json"
    proposal.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    write_audit_csv(manifest, args.out_dir / "character_scale_audit.csv")
    write_targets_csv(manifest, args.out_dir / "player_scale_targets.csv")
    write_player_landmark_sheet(args.root, manifest,
                                args.out_dir / "player_idle_landmarks.png")
    if args.write_manifest:
        args.write_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote reviewed manifest: {args.write_manifest}")
    print(f"Wrote audit proposal: {proposal}")


if __name__ == "__main__":
    main()
