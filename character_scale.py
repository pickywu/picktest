"""Runtime helpers for body-aware, pose-stable character scaling."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


MANIFEST_PATH = (
    Path(__file__).resolve().parent / "assets" / "characters" / "body_landmarks.json"
)
PLAYER_RACE_HEIGHT_FACTORS = {
    "elf": 1.00,
    "orc": 0.97,
    "human": 0.93,
    "dwarf": 0.78,
}
MONSTER_IDLE_WIDTH_ALLOWANCE = 1.05
REACTION_REFERENCE_HEIGHT = 900.0


@lru_cache(maxsize=1)
def load_character_scale_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != 1:
        raise ValueError(f"Unsupported character-scale manifest: {MANIFEST_PATH}")
    return manifest


def _player_record(sex: str, race: str, job: str) -> dict[str, Any]:
    key = f"{sex}/{race}/{job}"
    try:
        return load_character_scale_manifest()["players"][key]
    except KeyError as exc:
        raise ValueError(f"Missing player body landmark: {key}") from exc


def _monster_record(rank: int, kind: str) -> dict[str, Any]:
    key = f"rank_{rank:02d}/{kind}"
    try:
        return load_character_scale_manifest()["monsters"][key]
    except KeyError as exc:
        raise ValueError(f"Missing monster idle metric: {key}") from exc


def player_uniform_scale(sex: str, race: str, job: str,
                         max_body_height: float,
                         max_body_width: float,
                         pose: str = "idle") -> float:
    """Return an identity scale for legacy poses or standardized reactions."""
    del max_body_width
    record = _player_record(sex, race, job)
    source_height = (
        REACTION_REFERENCE_HEIGHT
        if pose in {"hurt", "block"}
        else max(1.0, float(record["idle_body"]["body_height"]))
    )
    target_height = max_body_height * PLAYER_RACE_HEIGHT_FACTORS[race]
    return target_height / source_height


def player_pose_anchor_x(sex: str, race: str, job: str, pose: str) -> float:
    record = _player_record(sex, race, job)
    poses = record["poses"]
    if pose not in poses:
        pose = "idle"
    return float(poses[pose]["anchor_x"])


def monster_uniform_scale(rank: int, kind: str,
                          max_body_height: float,
                          max_body_width: float) -> float:
    """Use an idle alpha box for both idle and attack poses of one monster."""
    record = _monster_record(rank, kind)
    idle = record["idle_body"]
    source_height = max(1.0, float(idle["body_height"]))
    scale = max_body_height / source_height
    source_width = max(1.0, float(record["poses"]["idle"]["visible_width"]))
    loose_width_limit = max_body_width * MONSTER_IDLE_WIDTH_ALLOWANCE
    return min(scale, loose_width_limit / source_width)


def monster_pose_scale(rank: int, kind: str, pose: str,
                       max_body_height: float,
                       max_body_width: float) -> float:
    """Preserve paired source scale, adapting standardized reaction canvases."""
    idle_scale = monster_uniform_scale(
        rank, kind, max_body_height, max_body_width
    )
    if pose not in {"hurt", "block"}:
        return idle_scale
    record = _monster_record(rank, kind)
    idle_visible_height = max(
        1.0, float(record["poses"]["idle"]["visible_height"])
    )
    return idle_visible_height * idle_scale / REACTION_REFERENCE_HEIGHT


def monster_pose_anchor_x(rank: int, kind: str, pose: str) -> float:
    record = _monster_record(rank, kind)
    poses = record["poses"]
    if pose not in poses:
        pose = "idle"
    return float(poses[pose]["anchor_x"])


def canvas_center_offset(anchor_x: float, canvas_width: float,
                         scale: float) -> float:
    """Offset a drawn texture centre so its body anchor lands on the target X."""
    return (anchor_x - canvas_width / 2.0) * scale
