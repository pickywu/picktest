from __future__ import annotations

import unittest

from perf_probe import PerfProbe
from ui.bootstrap import AssetWarmupQueue, BootstrapRunner, BootstrapTask


class BootstrapRunnerTests(unittest.TestCase):
    def test_order_budget_and_completion(self) -> None:
        calls: list[str] = []
        runner = BootstrapRunner([
            BootstrapTask("one", lambda: calls.append("one")),
            ("two", lambda: calls.append("two")),
        ])

        first = runner.step(0)
        self.assertEqual(calls, ["one"])
        self.assertEqual(first.executed, 1)
        self.assertFalse(first.done)

        runner.step(0)
        final = runner.step(0)
        self.assertEqual(calls, ["one", "two"])
        self.assertTrue(final.done)
        self.assertEqual(runner.progress, 1.0)

    def test_error_is_captured_and_stops_runner(self) -> None:
        def fail() -> None:
            raise RuntimeError("broken")

        runner = BootstrapRunner([("fail", fail), lambda: None])
        result = runner.step(10)
        self.assertIsInstance(result.error, RuntimeError)
        self.assertEqual(result.executed, 0)
        self.assertFalse(result.done)


class AssetWarmupQueueTests(unittest.TestCase):
    def test_priority_fifo_and_completed_dedupe(self) -> None:
        calls: list[str] = []
        queue = AssetWarmupQueue(default_budget_ms=100)
        self.assertTrue(queue.enqueue("low", lambda: calls.append("low"),
                                      priority=1))
        self.assertTrue(queue.enqueue("high-a", lambda: calls.append("high-a"),
                                      priority=10))
        self.assertTrue(queue.enqueue("high-b", lambda: calls.append("high-b"),
                                      priority=10))
        self.assertFalse(queue.enqueue("low", lambda: None, priority=0))

        result = queue.step()
        self.assertEqual(calls, ["high-a", "high-b", "low"])
        self.assertEqual(result.succeeded, 3)
        self.assertTrue(queue.idle)
        self.assertFalse(queue.enqueue("low", lambda: None))

    def test_generation_cancellation_and_requeue(self) -> None:
        calls: list[str] = []
        queue = AssetWarmupQueue()
        queue.enqueue("old", lambda: calls.append("old"))
        generation = queue.begin_generation(cancel_older=True)
        self.assertEqual(generation, 1)
        self.assertEqual(queue.remaining, 0)
        self.assertTrue(queue.enqueue(
            "old", lambda: calls.append("new"), generation=generation,
        ))
        queue.step(0)
        self.assertEqual(calls, ["new"])

    def test_failure_can_be_retried_explicitly(self) -> None:
        calls: list[str] = []
        queue = AssetWarmupQueue()

        def fail() -> None:
            raise ValueError("bad asset")

        queue.enqueue("asset", fail)
        result = queue.step(0)
        self.assertEqual(result.failed_keys, ("asset",))
        self.assertFalse(queue.enqueue("asset", lambda: None))
        self.assertTrue(queue.enqueue(
            "asset", lambda: calls.append("recovered"), retry_failed=True,
        ))
        queue.step(0)
        self.assertEqual(calls, ["recovered"])


class PerfProbeTests(unittest.TestCase):
    def test_disabled_probe_and_bounded_ring(self) -> None:
        disabled = PerfProbe(enabled=False, capacity=2)
        disabled.mark("ignored")
        with disabled.span("ignored-span"):
            pass
        self.assertEqual(disabled.snapshot(), ())

        enabled = PerfProbe(enabled=True, capacity=2)
        enabled.mark("one")
        enabled.mark("two")
        enabled.mark("three")
        self.assertEqual(
            [sample.name for sample in enabled.snapshot()], ["two", "three"]
        )


if __name__ == "__main__":
    unittest.main()
