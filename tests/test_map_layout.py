from __future__ import annotations

import pytest

from ui.map_layout import JOURNEY_MAP_NODES, cover_map_viewport


def test_cover_map_fills_widescreen_without_distortion() -> None:
    viewport = cover_map_viewport(3072, 2048, 1180, 720)

    assert viewport.width == pytest.approx(1180)
    assert viewport.height == pytest.approx(786.6666667)
    assert viewport.left == pytest.approx(0)
    assert viewport.bottom == pytest.approx(-33.3333333)
    assert viewport.width / viewport.height == pytest.approx(3072 / 2048)


def test_normalized_anchor_is_resolution_independent() -> None:
    standard = cover_map_viewport(3072, 2048, 1180, 720)
    doubled = cover_map_viewport(6144, 4096, 1180, 720)

    for node in JOURNEY_MAP_NODES:
        assert standard.normalized_to_screen(node.u, node.v_from_top) == pytest.approx(
            doubled.normalized_to_screen(node.u, node.v_from_top)
        )


def test_all_route_nodes_remain_visible_in_fullscreen_cover() -> None:
    viewport = cover_map_viewport(3072, 2048, 1180, 720)

    positions = [viewport.normalized_to_screen(node.u, node.v_from_top)
                 for node in JOURNEY_MAP_NODES]
    assert all(0 <= x <= 1180 and 0 <= y <= 720 for x, y in positions)
    assert [x for x, _ in positions] == sorted(x for x, _ in positions)


@pytest.mark.parametrize(
    "dimensions",
    [(0, 2048, 1180, 715), (3072, -1, 1180, 715), (3072, 2048, 0, 715)],
)
def test_cover_map_rejects_invalid_dimensions(dimensions: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        cover_map_viewport(*dimensions)
