from __future__ import annotations

from collections import Counter
from dataclasses import replace
import unittest

from route_map import (
    CHAPTER_COUNT,
    FINAL_BOSS_DEPTH,
    LAYERS_PER_CHAPTER,
    JourneyRoute,
    MIDDLE_NODE_KIND_WEIGHTS,
    NodeKind,
    ROUTE_GENERATION_VERSION,
    generate_journey_route,
)


class JourneyRouteTests(unittest.TestCase):
    def test_same_seed_is_identical_and_other_runs_differ(self) -> None:
        first = generate_journey_route(987654321, 2)
        repeated = generate_journey_route(987654321, 2)
        different = generate_journey_route(987654322, 2)

        self.assertEqual(first, repeated)
        self.assertEqual(first.to_dict(), repeated.to_dict())
        self.assertNotEqual(first.nodes, different.nodes)

    def test_round_trip_preserves_graph(self) -> None:
        original = generate_journey_route(42, 3, version=1)
        restored = JourneyRoute.from_dict(original.to_dict())

        self.assertEqual(restored, original)
        self.assertEqual(restored.to_dict(), original.to_dict())
        self.assertTrue(all(
            {node.kind for node in original.chapter_nodes(chapter) if node.layer == 6}
            == {NodeKind.BATTLE}
            for chapter in range(1, CHAPTER_COUNT + 1)
        ))

    def test_new_routes_use_the_current_generation_version(self) -> None:
        route = generate_journey_route(42, 3)
        self.assertEqual(route.version, ROUTE_GENERATION_VERSION)
        self.assertGreaterEqual(route.version, 2)

    def test_middle_nodes_follow_the_declared_distribution(self) -> None:
        counts: Counter[NodeKind] = Counter()
        for seed in range(200):
            route = generate_journey_route(seed, 1)
            counts.update(
                node.kind for node in route.nodes
                if node.chapter <= CHAPTER_COUNT
                and 1 <= node.layer < LAYERS_PER_CHAPTER - 1
            )
        total = sum(counts.values())
        for kind, weight in MIDDLE_NODE_KIND_WEIGHTS:
            with self.subTest(kind=kind):
                self.assertAlmostEqual(
                    counts[kind] / total, weight / 100, delta=.02,
                )

    def test_every_chapter_has_single_endpoints_and_weighted_middle_tree(self) -> None:
        self.assertEqual(
            dict(MIDDLE_NODE_KIND_WEIGHTS),
            {
                NodeKind.BATTLE: 64,
                NodeKind.ELITE: 12,
                NodeKind.CAMPFIRE: 12,
                NodeKind.SHOP: 12,
            },
        )
        self.assertEqual(sum(dict(MIDDLE_NODE_KIND_WEIGHTS).values()), 100)
        for seed in range(25):
            route = generate_journey_route(seed, 1 + seed % 3)
            route.validate()
            for chapter in range(1, CHAPTER_COUNT + 1):
                nodes = route.chapter_nodes(chapter)
                by_layer = {
                    layer: [node for node in nodes if node.layer == layer]
                    for layer in range(LAYERS_PER_CHAPTER)
                }
                self.assertEqual(len(by_layer[0]), 1)
                self.assertIs(by_layer[0][0].kind, NodeKind.BATTLE)
                self.assertEqual(by_layer[0][0].lane, 0)
                self.assertEqual(len(by_layer[6]), 1)
                self.assertIs(by_layer[6][0].kind, NodeKind.ELITE)
                self.assertEqual(by_layer[6][0].lane, 0)
                for layer in range(1, LAYERS_PER_CHAPTER - 1):
                    self.assertIn(len(by_layer[layer]), {2, 3})
                    self.assertTrue(all(
                        node.kind in dict(MIDDLE_NODE_KIND_WEIGHTS)
                        for node in by_layer[layer]
                    ))

                # Every branch in the penultimate layer converges on the one
                # elite endpoint for this chapter.
                endpoint_id = by_layer[6][0].id
                self.assertTrue(all(
                    node.next_ids == (endpoint_id,) for node in by_layer[5]
                ))

    def test_graph_has_only_forward_edges_and_no_islands(self) -> None:
        route = generate_journey_route(1234, 3)
        self.assertTrue(route.start_ids)
        reachable = set(route.start_ids)
        frontier = list(route.start_ids)
        while frontier:
            node_id = frontier.pop()
            node = route.node_by_id(node_id)
            for successor in route.available_successors(node_id):
                self.assertEqual(successor.depth, node.depth + 1)
                if successor.id not in reachable:
                    reachable.add(successor.id)
                    frontier.append(successor.id)

        self.assertEqual(reachable, {node.id for node in route.nodes})
        boss = [node for node in route.nodes if node.depth == FINAL_BOSS_DEPTH]
        self.assertEqual(len(boss), 1)
        self.assertIs(boss[0].kind, NodeKind.BOSS)
        self.assertEqual(boss[0].next_ids, ())

    def test_lane_local_edges_create_distinct_route_choices(self) -> None:
        found_distinct_choices = False
        for seed in range(25):
            route = generate_journey_route(seed, 1 + seed % 3)
            incoming = {node.id: 0 for node in route.nodes}
            for source in route.nodes:
                targets = [route.node_by_id(node_id) for node_id in source.next_ids]
                for target in targets:
                    incoming[target.id] += 1
                if source.depth == FINAL_BOSS_DEPTH:
                    continue
                self.assertTrue(targets)
                distances = [abs(source.lane - target.lane) for target in targets]
                self.assertTrue(
                    all(distance <= 1 for distance in distances)
                    or len(set(distances)) == 1
                )

            for node in route.nodes:
                if node.depth > 0:
                    self.assertGreater(incoming[node.id], 0)

            for depth in range(FINAL_BOSS_DEPTH):
                source_nodes = [
                    node for node in route.nodes if node.depth == depth
                ]
                if len(source_nodes) > 1 and len({
                    node.next_ids for node in source_nodes
                }) > 1:
                    found_distinct_choices = True

        self.assertTrue(found_distinct_choices)

    def test_every_layer_uses_centered_lane_contract(self) -> None:
        expected_lanes = {
            1: (0,),
            2: (-1, 1),
            3: (-1, 0, 1),
        }
        for seed in range(20):
            route = generate_journey_route(seed, 1 + seed % 3)
            for depth in range(FINAL_BOSS_DEPTH + 1):
                layer_nodes = [node for node in route.nodes if node.depth == depth]
                self.assertEqual(
                    tuple(sorted(node.lane for node in layer_nodes)),
                    expected_lanes[len(layer_nodes)],
                )

    def test_validation_rejects_a_dead_end(self) -> None:
        route = generate_journey_route(7, 1)
        victim = next(node for node in route.nodes if node.depth == 3)
        broken_nodes = tuple(
            replace(node, next_ids=()) if node.id == victim.id else node
            for node in route.nodes
        )
        broken = replace(route, nodes=broken_nodes)
        with self.assertRaisesRegex(ValueError, "successor"):
            broken.validate()

    def test_public_lookup_helpers(self) -> None:
        route = generate_journey_route(999, 2)
        first_id = route.start_ids[0]
        first = route.node_by_id(first_id)
        self.assertEqual(first.depth, 0)
        self.assertEqual(
            tuple(node.id for node in route.available_successors(first_id)),
            first.next_ids,
        )
        with self.assertRaises(KeyError):
            route.node_by_id("missing")
        with self.assertRaises(ValueError):
            route.chapter_nodes(0)

    def test_invalid_generation_inputs_are_rejected(self) -> None:
        for arguments in ((-1, 1, 1), (1, 0, 1), (1, 1, 0), (True, 1, 1)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    generate_journey_route(*arguments)


if __name__ == "__main__":
    unittest.main()
