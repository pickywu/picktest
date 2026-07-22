"""Responsive geometry for the full-screen journey map.

The artwork uses a conventional top-left image origin while Arcade draws in a
bottom-left coordinate system. Keeping that conversion here prevents route
markers from acquiring one-off offsets when the map asset is regenerated at a
different resolution.
"""

from __future__ import annotations

from dataclasses import dataclass


# The route UI deliberately uses canvas coordinates rather than image-space
# anchors.  Both the renderer and the invisible mouse targets use this helper,
# so a regenerated background can never make the clickable area drift away
# from the visible node.
ROUTE_DEPTH_COUNT = 7
ROUTE_MAP_LEFT = 70.0
ROUTE_MAP_RIGHT = 1110.0
ROUTE_MAP_CENTER_Y = 390.0
ROUTE_MAP_LANE_GAP = 120.0
ROUTE_NODE_HIT_SIZE = 60.0


@dataclass(frozen=True, slots=True)
class RouteNodeGeometry:
    """Shared screen-space geometry for one node in the current chapter."""

    center_x: float
    center_y: float
    hit_width: float = ROUTE_NODE_HIT_SIZE
    hit_height: float = ROUTE_NODE_HIT_SIZE

    @property
    def left(self) -> float:
        return self.center_x - self.hit_width / 2

    @property
    def bottom(self) -> float:
        return self.center_y - self.hit_height / 2


def route_node_geometry(layer: int, lane: int) -> RouteNodeGeometry:
    """Return the canonical 7-layer, 3-lane node position.

    ``layer`` runs from 0 through 6 inside the visible chapter. Route nodes may
    also carry a run-global ``depth``; callers must pass their chapter-local
    layer here. ``lane`` uses -1/0/1, with positive lanes
    above the centre line.  The resulting 60px mouse targets remain inside the
    map's 70..1110 by 205..600 safe region.
    """

    layer = int(layer)
    lane = int(lane)
    if not 0 <= layer < ROUTE_DEPTH_COUNT:
        raise ValueError(f"route layer must be 0..{ROUTE_DEPTH_COUNT - 1}")
    if lane not in (-1, 0, 1):
        raise ValueError("route lane must be -1, 0, or 1")
    step = (ROUTE_MAP_RIGHT - ROUTE_MAP_LEFT) / (ROUTE_DEPTH_COUNT - 1)
    return RouteNodeGeometry(
        ROUTE_MAP_LEFT + layer * step,
        ROUTE_MAP_CENTER_Y + lane * ROUTE_MAP_LANE_GAP,
    )


def route_boss_geometry() -> RouteNodeGeometry:
    """Place the one-node final chapter at the visual centre of the map."""
    return RouteNodeGeometry(
        (ROUTE_MAP_LEFT + ROUTE_MAP_RIGHT) / 2,
        ROUTE_MAP_CENTER_Y,
    )


@dataclass(frozen=True, slots=True)
class MapViewport:
    """A texture rectangle fitted over a destination with ``cover`` scaling."""

    left: float
    bottom: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def center_y(self) -> float:
        return self.bottom + self.height / 2

    def normalized_to_screen(self, u: float, v_from_top: float) -> tuple[float, float]:
        """Map normalized image coordinates to Arcade screen coordinates."""
        return (
            self.left + self.width * u,
            self.bottom + self.height * (1.0 - v_from_top),
        )


def cover_map_viewport(
    source_width: float,
    source_height: float,
    destination_width: float,
    destination_height: float,
    *,
    destination_left: float = 0.0,
    destination_bottom: float = 0.0,
) -> MapViewport:
    """Scale a map to cover the destination without changing its aspect ratio."""
    if min(source_width, source_height, destination_width, destination_height) <= 0:
        raise ValueError("map and destination dimensions must be positive")
    scale = max(destination_width / source_width, destination_height / source_height)
    width = source_width * scale
    height = source_height * scale
    return MapViewport(
        destination_left + (destination_width - width) / 2,
        destination_bottom + (destination_height - height) / 2,
        width,
        height,
    )


@dataclass(frozen=True, slots=True)
class JourneyMapNode:
    milestone: int
    label: str
    u: float
    v_from_top: float


# Anchors measured on the shipped 1536x1024 high-detail composition and stored
# as ratios.  Labels are intentionally not separately anchored: they follow the
# icon so the marker, pulse and caption can never drift apart.
JOURNEY_MAP_NODES: tuple[JourneyMapNode, ...] = (
    JourneyMapNode(1, "城塞", 270.0 / 1536.0, 557.0 / 1024.0),
    JourneyMapNode(6, "霧林", 541.0 / 1536.0, 563.0 / 1024.0),
    JourneyMapNode(11, "教堂", 805.0 / 1536.0, 607.0 / 1024.0),
    JourneyMapNode(16, "深淵", 1048.0 / 1536.0, 643.0 / 1024.0),
    JourneyMapNode(21, "王座", 1366.0 / 1536.0, 570.0 / 1024.0),
)


__all__ = [
    "JOURNEY_MAP_NODES",
    "JourneyMapNode",
    "MapViewport",
    "ROUTE_DEPTH_COUNT",
    "ROUTE_MAP_CENTER_Y",
    "ROUTE_MAP_LANE_GAP",
    "ROUTE_MAP_LEFT",
    "ROUTE_MAP_RIGHT",
    "ROUTE_NODE_HIT_SIZE",
    "RouteNodeGeometry",
    "cover_map_viewport",
    "route_boss_geometry",
    "route_node_geometry",
]
