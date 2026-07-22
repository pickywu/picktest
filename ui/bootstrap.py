"""Cooperative startup and asset-warmup scheduling primitives.

Actions run on the caller's thread.  This is deliberate: Arcade texture and GL
objects must be created on the main thread.  A time budget limits how many
indivisible actions begin during one step, but cannot interrupt an action that
has already started.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator, Sized
from dataclasses import dataclass
import heapq
from time import perf_counter_ns
from typing import Any, TypeAlias

from perf_probe import PerfProbe


TaskAction: TypeAlias = Callable[[], object]


@dataclass(frozen=True, slots=True)
class BootstrapTask:
    label: str
    action: TaskAction


BootstrapTaskLike: TypeAlias = (
    BootstrapTask | tuple[str, TaskAction] | TaskAction
)


@dataclass(frozen=True, slots=True)
class BootstrapStepResult:
    executed: int
    completed: int
    total: int | None
    elapsed_ms: float
    done: bool
    error: Exception | None


def _coerce_bootstrap_task(value: Any, index: int) -> BootstrapTask:
    if isinstance(value, BootstrapTask):
        return value
    if callable(value):
        label = getattr(value, "__name__", None) or f"Task {index + 1}"
        return BootstrapTask(str(label), value)
    if (isinstance(value, tuple) and len(value) == 2
            and isinstance(value[0], str) and callable(value[1])):
        return BootstrapTask(value[0], value[1])
    raise TypeError(
        "bootstrap tasks must be BootstrapTask, (label, callable), or callable"
    )


class BootstrapRunner:
    """Consume ordered startup tasks cooperatively with fatal error capture."""

    def __init__(
        self,
        tasks: Iterable[BootstrapTaskLike],
        *,
        total_tasks: int | None = None,
        probe: PerfProbe | None = None,
    ) -> None:
        if total_tasks is None and isinstance(tasks, Sized):
            total_tasks = len(tasks)
        if total_tasks is not None and total_tasks < 0:
            raise ValueError("total_tasks cannot be negative")
        self._tasks: Iterator[BootstrapTaskLike] = iter(tasks)
        self.total_tasks = total_tasks
        self.probe = probe
        self.completed_count = 0
        self.current_label = "Preparing"
        self.last_task_ms = 0.0
        self.done = False
        self.error: Exception | None = None

    @property
    def progress(self) -> float | None:
        if self.total_tasks is None:
            return None
        if self.total_tasks == 0:
            return 1.0 if self.done else 0.0
        return min(1.0, self.completed_count / self.total_tasks)

    def step(self, budget_ms: float = 8.0) -> BootstrapStepResult:
        if self.done or self.error is not None:
            return BootstrapStepResult(
                0, self.completed_count, self.total_tasks, 0.0,
                self.done, self.error,
            )
        budget_ns = max(0, round(float(budget_ms) * 1_000_000))
        started_ns = perf_counter_ns()
        executed = 0
        while executed == 0 or perf_counter_ns() - started_ns < budget_ns:
            try:
                raw_task = next(self._tasks)
            except StopIteration:
                self.done = True
                break
            try:
                task = _coerce_bootstrap_task(raw_task, self.completed_count)
                self.current_label = task.label
                task_started_ns = perf_counter_ns()
                if self.probe is None:
                    task.action()
                else:
                    with self.probe.span("bootstrap.task", task=task.label):
                        task.action()
                self.last_task_ms = (
                    perf_counter_ns() - task_started_ns
                ) / 1_000_000
            except Exception as exc:
                self.error = exc
                break
            self.completed_count += 1
            executed += 1
        elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000
        return BootstrapStepResult(
            executed, self.completed_count, self.total_tasks, elapsed_ms,
            self.done, self.error,
        )


@dataclass(frozen=True, slots=True)
class WarmupTask:
    key: Hashable
    action: TaskAction
    priority: int
    generation: int
    label: str
    sequence: int


@dataclass(frozen=True, slots=True)
class WarmupStepResult:
    executed: int
    succeeded: int
    remaining: int
    elapsed_ms: float
    failed_keys: tuple[Hashable, ...] = ()


class AssetWarmupQueue:
    """Priority queue for deduplicated, cancellable main-thread warmup work.

    Larger ``priority`` values run first.  FIFO order is preserved among equal
    priorities.  Completed keys remain deduplicated until :meth:`forget` is
    called.  The class is intentionally not thread-safe.
    """

    def __init__(self, *, default_budget_ms: float = 6.0,
                 probe: PerfProbe | None = None) -> None:
        self.default_budget_ms = max(0.0, float(default_budget_ms))
        self.probe = probe
        self._generation = 0
        self._sequence = 0
        self._heap: list[tuple[int, int, WarmupTask]] = []
        self._pending: dict[Hashable, WarmupTask] = {}
        self._completed: set[Hashable] = set()
        self._failures: dict[Hashable, Exception] = {}

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def remaining(self) -> int:
        return len(self._pending)

    @property
    def idle(self) -> bool:
        return not self._pending

    @property
    def failures(self) -> dict[Hashable, Exception]:
        return dict(self._failures)

    @property
    def completed_keys(self) -> frozenset[Hashable]:
        return frozenset(self._completed)

    def begin_generation(self, *, cancel_older: bool = True) -> int:
        self._generation += 1
        if cancel_older:
            self.cancel_older_than(self._generation)
        return self._generation

    def enqueue(
        self,
        key: Hashable,
        action: TaskAction,
        *,
        priority: int = 0,
        generation: int | None = None,
        label: str | None = None,
        retry_failed: bool = False,
    ) -> bool:
        if not callable(action):
            raise TypeError("warmup action must be callable")
        if key in self._completed:
            return False
        if key in self._failures and not retry_failed:
            return False
        generation = self._generation if generation is None else int(generation)
        existing = self._pending.get(key)
        priority = int(priority)
        if existing is not None:
            newer_generation = generation > existing.generation
            higher_priority = priority > existing.priority
            if not newer_generation and not higher_priority:
                return False
        self._failures.pop(key, None)
        self._sequence += 1
        task = WarmupTask(
            key, action, priority, generation,
            str(label or key), self._sequence,
        )
        self._pending[key] = task
        heapq.heappush(self._heap, (-priority, task.sequence, task))
        return True

    def cancel(self, key: Hashable) -> bool:
        return self._pending.pop(key, None) is not None

    def cancel_generation(self, generation: int) -> int:
        keys = [
            key for key, task in self._pending.items()
            if task.generation == generation
        ]
        for key in keys:
            self._pending.pop(key, None)
        return len(keys)

    def cancel_older_than(self, generation: int) -> int:
        keys = [
            key for key, task in self._pending.items()
            if task.generation < generation
        ]
        for key in keys:
            self._pending.pop(key, None)
        return len(keys)

    def cancel_all(self) -> int:
        count = len(self._pending)
        self._pending.clear()
        return count

    def forget(self, key: Hashable) -> None:
        """Allow a completed or failed key to be queued again."""
        self._completed.discard(key)
        self._failures.pop(key, None)

    def clear_history(self) -> None:
        self._completed.clear()
        self._failures.clear()

    def _pop_next(self) -> WarmupTask | None:
        while self._heap:
            _priority, _sequence, task = heapq.heappop(self._heap)
            if self._pending.get(task.key) is task:
                self._pending.pop(task.key, None)
                return task
        return None

    def step(self, budget_ms: float | None = None) -> WarmupStepResult:
        budget = self.default_budget_ms if budget_ms is None else float(budget_ms)
        budget_ns = max(0, round(budget * 1_000_000))
        started_ns = perf_counter_ns()
        executed = 0
        succeeded = 0
        failed_keys: list[Hashable] = []
        while executed == 0 or perf_counter_ns() - started_ns < budget_ns:
            task = self._pop_next()
            if task is None:
                break
            try:
                if self.probe is None:
                    task.action()
                else:
                    with self.probe.span(
                        "warmup.task", task=task.label,
                        generation=task.generation,
                    ):
                        task.action()
            except Exception as exc:
                self._failures[task.key] = exc
                failed_keys.append(task.key)
            else:
                self._completed.add(task.key)
                succeeded += 1
            executed += 1
        elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000
        return WarmupStepResult(
            executed, succeeded, len(self._pending), elapsed_ms,
            tuple(failed_keys),
        )


__all__ = [
    "AssetWarmupQueue", "BootstrapRunner", "BootstrapStepResult",
    "BootstrapTask", "BootstrapTaskLike", "TaskAction", "WarmupStepResult",
    "WarmupTask",
]
