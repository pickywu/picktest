"""Deterministic, save-friendly journey route generation.

The route graph is pure game data: it has no Arcade dependency and consumes no
global random state.  A run seed, difficulty, and generation version always
produce the same complete graph, while the serialized graph remains stable even
if a future generator version changes its rules.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import random
from typing import Any, Mapping


CHAPTER_COUNT = 4
LAYERS_PER_CHAPTER = 7
FINAL_BOSS_DEPTH = CHAPTER_COUNT * LAYERS_PER_CHAPTER
ROUTE_GENERATION_VERSION = 2


class NodeKind(str, Enum):
    BATTLE = "battle"
    ELITE = "elite"
    CAMPFIRE = "campfire"
    SHOP = "shop"
    BOSS = "boss"


# The previous route structure produced these expected proportions across the
# five middle layers: ordinary battles occupied 64% of generated nodes, while
# elite battles, campfires, and shops each occupied 12%.  Keeping the weights
# explicit preserves that in-game distribution while allowing every middle
# layer to contain a real mix of route choices.
MIDDLE_NODE_KIND_WEIGHTS: tuple[tuple[NodeKind, int], ...] = (
    (NodeKind.BATTLE, 64),
    (NodeKind.ELITE, 12),
    (NodeKind.CAMPFIRE, 12),
    (NodeKind.SHOP, 12),
)


@dataclass(frozen=True, slots=True)
class RouteNode:
    id: str
    kind: NodeKind
    chapter: int
    layer: int
    depth: int
    lane: int
    next_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "chapter": self.chapter,
            "layer": self.layer,
            "depth": self.depth,
            "lane": self.lane,
            "next_ids": list(self.next_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RouteNode":
        if not isinstance(data, Mapping):
            raise ValueError("route node must be a mapping")
        try:
            node_id = data["id"]
            kind = NodeKind(data["kind"])
            chapter = data["chapter"]
            layer = data["layer"]
            depth = data["depth"]
            lane = data["lane"]
            next_ids = data.get("next_ids", ())
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid route node data") from exc
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("route node id must be a non-empty string")
        for name, value in (
            ("chapter", chapter), ("layer", layer),
            ("depth", depth), ("lane", lane),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"route node {name} must be an integer")
        if not isinstance(next_ids, (list, tuple)) or any(
            not isinstance(node_id, str) or not node_id for node_id in next_ids
        ):
            raise ValueError("route node next_ids must contain non-empty strings")
        return cls(
            node_id, kind, chapter, layer, depth, lane, tuple(next_ids),
        )


@dataclass(frozen=True, slots=True)
class JourneyRoute:
    run_seed: int
    difficulty: int
    version: int
    nodes: tuple[RouteNode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_seed": self.run_seed,
            "difficulty": self.difficulty,
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JourneyRoute":
        if not isinstance(data, Mapping):
            raise ValueError("journey route must be a mapping")
        try:
            run_seed = data["run_seed"]
            difficulty = data["difficulty"]
            version = data["version"]
            raw_nodes = data["nodes"]
        except KeyError as exc:
            raise ValueError("journey route is missing required data") from exc
        for name, value in (
            ("run_seed", run_seed),
            ("difficulty", difficulty),
            ("version", version),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"journey route {name} must be an integer")
        if not isinstance(raw_nodes, (list, tuple)):
            raise ValueError("journey route nodes must be a sequence")
        route = cls(
            run_seed, difficulty, version,
            tuple(RouteNode.from_dict(node) for node in raw_nodes),
        )
        route.validate()
        return route

    def validate(self) -> None:
        validate_journey_route(self)

    def node_by_id(self, node_id: str) -> RouteNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    @property
    def start_ids(self) -> tuple[str, ...]:
        return tuple(
            node.id for node in sorted(self.nodes, key=lambda item: item.lane)
            if node.depth == 0
        )

    def chapter_nodes(self, chapter: int) -> tuple[RouteNode, ...]:
        if chapter not in range(1, CHAPTER_COUNT + 1):
            raise ValueError(f"chapter must be between 1 and {CHAPTER_COUNT}")
        return tuple(
            sorted(
                (node for node in self.nodes if node.chapter == chapter),
                key=lambda item: (item.layer, item.lane),
            )
        )

    def available_successors(self, node_id: str) -> tuple[RouteNode, ...]:
        node = self.node_by_id(node_id)
        return tuple(self.node_by_id(next_id) for next_id in node.next_ids)


def _stable_rng(run_seed: int, difficulty: int, version: int) -> random.Random:
    material = (
        f"ember-kingdom:journey-route:{version}:{run_seed}:{difficulty}"
    ).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _validate_generation_inputs(run_seed: int, difficulty: int, version: int) -> None:
    for name, value, minimum in (
        ("run_seed", run_seed, 0),
        ("difficulty", difficulty, 1),
        ("version", version, 1),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")


def _lanes_for_count(node_count: int) -> tuple[int, ...]:
    try:
        return {
            1: (0,),
            2: (-1, 1),
            3: (-1, 0, 1),
        }[node_count]
    except KeyError as exc:
        raise ValueError("a route layer must contain one to three nodes") from exc


def generate_journey_route(
    run_seed: int,
    difficulty: int,
    version: int = ROUTE_GENERATION_VERSION,
) -> JourneyRoute:
    """Generate four converging tree chapters followed by one final boss.

    Each chapter starts at one ordinary battle, branches through five layers
    using the established encounter percentages, and converges at one elite.
    """

    _validate_generation_inputs(run_seed, difficulty, version)
    rng = _stable_rng(run_seed, difficulty, version)
    route_tag = f"r{run_seed:x}v{version}d{difficulty}"
    nodes: list[RouteNode] = []

    middle_kinds = tuple(kind for kind, _weight in MIDDLE_NODE_KIND_WEIGHTS)
    middle_weights = tuple(weight for _kind, weight in MIDDLE_NODE_KIND_WEIGHTS)
    for chapter in range(1, CHAPTER_COUNT + 1):
        if version == 1:
            middle_layers = tuple(range(1, LAYERS_PER_CHAPTER - 1))
            service_pairs = tuple(
                (first, second)
                for first in middle_layers
                for second in middle_layers
                if first < second and second - first > 1
            )
            first_service, second_service = rng.choice(service_pairs)
            if rng.random() < .5:
                campfire_layer, shop_layer = first_service, second_service
            else:
                shop_layer, campfire_layer = first_service, second_service
            middle_combat_layers = tuple(
                layer for layer in middle_layers
                if layer not in {campfire_layer, shop_layer}
            )
            elite_layer = rng.choice(middle_combat_layers)

        for layer in range(LAYERS_PER_CHAPTER):
            depth = (chapter - 1) * LAYERS_PER_CHAPTER + layer
            if version == 1:
                if layer == campfire_layer:
                    kinds = (NodeKind.CAMPFIRE,)
                elif layer == shop_layer:
                    kinds = (NodeKind.SHOP,)
                else:
                    node_count = rng.randint(1, 3)
                    if layer == elite_layer:
                        node_count = max(2, node_count)
                        elite_lane = rng.choice(_lanes_for_count(node_count))
                        kinds = tuple(
                            NodeKind.ELITE if lane == elite_lane else NodeKind.BATTLE
                            for lane in _lanes_for_count(node_count)
                        )
                    else:
                        kinds = (NodeKind.BATTLE,) * node_count
            elif layer == 0:
                kinds = (NodeKind.BATTLE,)
            elif layer == LAYERS_PER_CHAPTER - 1:
                kinds = (NodeKind.ELITE,)
            else:
                node_count = rng.randint(2, 3)
                kinds = tuple(rng.choices(
                    middle_kinds, weights=middle_weights, k=node_count,
                ))

            for lane, kind in zip(_lanes_for_count(len(kinds)), kinds):
                nodes.append(RouteNode(
                    id=f"{route_tag}:c{chapter}:l{layer}:n{lane}",
                    kind=kind,
                    chapter=chapter,
                    layer=layer,
                    depth=depth,
                    lane=lane,
                ))

    boss_id = f"{route_tag}:boss"
    nodes.append(RouteNode(
        id=boss_id,
        kind=NodeKind.BOSS,
        chapter=CHAPTER_COUNT + 1,
        layer=0,
        depth=FINAL_BOSS_DEPTH,
        lane=0,
    ))

    ids_by_depth: dict[int, tuple[str, ...]] = {}
    for depth in range(FINAL_BOSS_DEPTH + 1):
        ids_by_depth[depth] = tuple(
            node.id for node in sorted(nodes, key=lambda item: item.lane)
            if node.depth == depth
        )
    nodes_by_id = {node.id: node for node in nodes}
    successors: dict[str, list[str]] = {node.id: [] for node in nodes}
    for depth in range(FINAL_BOSS_DEPTH):
        sources = [nodes_by_id[node_id] for node_id in ids_by_depth[depth]]
        targets = [nodes_by_id[node_id] for node_id in ids_by_depth[depth + 1]]

        # Keep choices local to the current lane.  A side lane can reach the
        # centre and its own side, while crossing the whole map takes more
        # than one layer.
        for source in sources:
            local_targets = [
                target for target in targets
                if abs(source.lane - target.lane) <= 1
            ]
            if not local_targets:
                nearest_distance = min(
                    abs(source.lane - target.lane) for target in targets
                )
                local_targets = [
                    target for target in targets
                    if abs(source.lane - target.lane) == nearest_distance
                ]
            successors[source.id].extend(target.id for target in local_targets)

        # Sparse layers can otherwise leave a newly opened lane unreachable.
        # Attach any such target to one deterministic nearest source.
        incoming = {
            target.id: any(
                target.id in successors[source.id] for source in sources
            )
            for target in targets
        }
        for target in targets:
            if incoming[target.id]:
                continue
            nearest_source = min(
                sources,
                key=lambda source: (
                    abs(source.lane - target.lane), source.lane, source.id,
                ),
            )
            successors[nearest_source.id].append(target.id)

    linked_nodes = tuple(
        replace(node, next_ids=tuple(successors[node.id]))
        for node in nodes
    )
    route = JourneyRoute(run_seed, difficulty, version, linked_nodes)
    route.validate()
    return route


def validate_journey_route(route: JourneyRoute) -> None:
    """Raise ``ValueError`` unless ``route`` satisfies every graph invariant."""

    if not isinstance(route, JourneyRoute):
        raise ValueError("route must be a JourneyRoute")
    _validate_generation_inputs(route.run_seed, route.difficulty, route.version)
    if not route.nodes:
        raise ValueError("route must contain nodes")

    by_id: dict[str, RouteNode] = {}
    by_depth: dict[int, list[RouteNode]] = {}
    for node in route.nodes:
        if not isinstance(node, RouteNode):
            raise ValueError("route contains a non-RouteNode value")
        if not node.id or node.id in by_id:
            raise ValueError("route node ids must be non-empty and unique")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (node.chapter, node.layer, node.depth, node.lane)
        ):
            raise ValueError("route node coordinates must be integers")
        if min(node.chapter, node.layer, node.depth) < 0:
            raise ValueError("route chapter, layer, and depth cannot be negative")
        if node.lane not in {-1, 0, 1}:
            raise ValueError("route node lane must be -1, 0, or 1")
        if len(node.next_ids) != len(set(node.next_ids)):
            raise ValueError("route node successors must be unique")
        by_id[node.id] = node
        by_depth.setdefault(node.depth, []).append(node)

    expected_depths = set(range(FINAL_BOSS_DEPTH + 1))
    if set(by_depth) != expected_depths:
        raise ValueError("route must contain every journey depth exactly once")
    for depth, depth_nodes in by_depth.items():
        expected_count = 1 if depth == FINAL_BOSS_DEPTH else range(1, 4)
        if depth == FINAL_BOSS_DEPTH:
            if len(depth_nodes) != expected_count:
                raise ValueError("final boss depth must contain exactly one node")
        elif len(depth_nodes) not in expected_count:
            raise ValueError("each journey layer must contain one to three nodes")
        lanes = tuple(sorted(node.lane for node in depth_nodes))
        if lanes != _lanes_for_count(len(depth_nodes)):
            raise ValueError("node lanes do not match the centered lane contract")

    boss = by_depth[FINAL_BOSS_DEPTH][0]
    if (
        boss.kind is not NodeKind.BOSS
        or boss.chapter != CHAPTER_COUNT + 1
        or boss.layer != 0
        or boss.next_ids
    ):
        raise ValueError("route must end in one terminal boss node")
    if any(
        node.kind is NodeKind.BOSS and node.id != boss.id
        for node in route.nodes
    ):
        raise ValueError("boss nodes are only allowed at the final depth")

    for chapter in range(1, CHAPTER_COUNT + 1):
        chapter_nodes = [node for node in route.nodes if node.chapter == chapter]
        expected_chapter_depths = set(range(
            (chapter - 1) * LAYERS_PER_CHAPTER,
            chapter * LAYERS_PER_CHAPTER,
        ))
        if {node.depth for node in chapter_nodes} != expected_chapter_depths:
            raise ValueError("each chapter must contain exactly seven layers")

        kinds_by_layer: dict[int, set[NodeKind]] = {}
        for node in chapter_nodes:
            expected_depth = (chapter - 1) * LAYERS_PER_CHAPTER + node.layer
            if node.layer not in range(LAYERS_PER_CHAPTER) or node.depth != expected_depth:
                raise ValueError("chapter layer and global depth do not agree")
            kinds_by_layer.setdefault(node.layer, set()).add(node.kind)

        if route.version == 1:
            if kinds_by_layer[0] != {NodeKind.BATTLE}:
                raise ValueError("every legacy chapter must start with battles")
            if kinds_by_layer[LAYERS_PER_CHAPTER - 1] != {NodeKind.BATTLE}:
                raise ValueError("every legacy chapter must end with battles")
            campfire_layers = [
                layer for layer, kinds in kinds_by_layer.items()
                if kinds == {NodeKind.CAMPFIRE}
            ]
            shop_layers = [
                layer for layer, kinds in kinds_by_layer.items()
                if kinds == {NodeKind.SHOP}
            ]
            if len(campfire_layers) != 1 or len(shop_layers) != 1:
                raise ValueError("each legacy chapter needs one service layer of each kind")
            if abs(campfire_layers[0] - shop_layers[0]) <= 1:
                raise ValueError("legacy service layers cannot be adjacent")
            service_layers = {campfire_layers[0], shop_layers[0]}
            combat_layers = set(range(LAYERS_PER_CHAPTER)) - service_layers
            for layer in combat_layers:
                kinds = kinds_by_layer[layer]
                if not kinds <= {NodeKind.BATTLE, NodeKind.ELITE}:
                    raise ValueError("legacy combat layers contain an invalid node kind")
                if NodeKind.BATTLE not in kinds:
                    raise ValueError("legacy elite encounters must remain optional")
            elite_nodes = [
                node for node in chapter_nodes if node.kind is NodeKind.ELITE
            ]
            if len(elite_nodes) > 1:
                raise ValueError("legacy chapters allow at most one elite")
            if any(
                node.layer in {0, LAYERS_PER_CHAPTER - 1}
                for node in elite_nodes
            ):
                raise ValueError("legacy elites must be in middle layers")
        else:
            first_nodes = [node for node in chapter_nodes if node.layer == 0]
            if len(first_nodes) != 1 or first_nodes[0].kind is not NodeKind.BATTLE:
                raise ValueError("every chapter must start at one battle node")
            last_nodes = [
                node for node in chapter_nodes
                if node.layer == LAYERS_PER_CHAPTER - 1
            ]
            if len(last_nodes) != 1 or last_nodes[0].kind is not NodeKind.ELITE:
                raise ValueError("every chapter must end at one elite node")

            allowed_middle_kinds = {
                NodeKind.BATTLE, NodeKind.ELITE,
                NodeKind.CAMPFIRE, NodeKind.SHOP,
            }
            for layer in range(1, LAYERS_PER_CHAPTER - 1):
                layer_nodes = [node for node in chapter_nodes if node.layer == layer]
                if len(layer_nodes) not in {2, 3}:
                    raise ValueError("every middle route layer must branch")
                if any(node.kind not in allowed_middle_kinds for node in layer_nodes):
                    raise ValueError("middle route layers contain an invalid node kind")

    for node in route.nodes:
        if node.depth == FINAL_BOSS_DEPTH:
            continue
        if not node.next_ids:
            raise ValueError("every non-boss node must have a successor")
        for next_id in node.next_ids:
            target = by_id.get(next_id)
            if target is None:
                raise ValueError("route edge points to an unknown node")
            if target.depth != node.depth + 1:
                raise ValueError("route edges may only connect the next layer")

    start_ids = tuple(node.id for node in by_depth[0])
    reachable = set(start_ids)
    queue = deque(start_ids)
    while queue:
        current = by_id[queue.popleft()]
        for next_id in current.next_ids:
            if next_id not in reachable:
                reachable.add(next_id)
                queue.append(next_id)
    if reachable != set(by_id):
        raise ValueError("route contains unreachable nodes")

    reverse_edges: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for node in route.nodes:
        for next_id in node.next_ids:
            reverse_edges[next_id].add(node.id)
    can_reach_boss = {boss.id}
    queue = deque((boss.id,))
    while queue:
        current_id = queue.popleft()
        for previous_id in reverse_edges[current_id]:
            if previous_id not in can_reach_boss:
                can_reach_boss.add(previous_id)
                queue.append(previous_id)
    if can_reach_boss != set(by_id):
        raise ValueError("route contains a dead end")


__all__ = [
    "CHAPTER_COUNT",
    "LAYERS_PER_CHAPTER",
    "FINAL_BOSS_DEPTH",
    "JourneyRoute",
    "MIDDLE_NODE_KIND_WEIGHTS",
    "NodeKind",
    "ROUTE_GENERATION_VERSION",
    "RouteNode",
    "generate_journey_route",
    "validate_journey_route",
]
