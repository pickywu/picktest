"""Small opt-in performance probe with a bounded in-memory history.

The disabled path is intentionally a single boolean branch.  Samples are kept
in memory only; callers decide whether and where diagnostics are written.
"""

from __future__ import annotations

from collections import deque
from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from time import perf_counter_ns
from typing import Any


@dataclass(frozen=True, slots=True)
class PerfSample:
    name: str
    started_ns: int
    duration_ns: int
    metadata: tuple[tuple[str, Any], ...] = ()

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000


class _NullSpan(AbstractContextManager[None]):
    __slots__ = ()

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object,
                 traceback: object) -> bool:
        return False


_NULL_SPAN = _NullSpan()


class _ProbeSpan(AbstractContextManager[None]):
    __slots__ = ("_probe", "_name", "_metadata", "_started_ns")

    def __init__(self, probe: "PerfProbe", name: str,
                 metadata: tuple[tuple[str, Any], ...]) -> None:
        self._probe = probe
        self._name = name
        self._metadata = metadata
        self._started_ns = 0

    def __enter__(self) -> None:
        self._started_ns = perf_counter_ns()
        return None

    def __exit__(self, exc_type: object, exc: object,
                 traceback: object) -> bool:
        finished_ns = perf_counter_ns()
        metadata = self._metadata
        if exc_type is not None:
            metadata += (("failed", True),)
        self._probe.record(
            self._name,
            started_ns=self._started_ns,
            duration_ns=finished_ns - self._started_ns,
            metadata=metadata,
        )
        return False


class PerfProbe:
    """Record lightweight milestones and spans in a fixed-size ring buffer.

    The probe is designed for main-thread startup/frame instrumentation.  It is
    not synchronized for concurrent writers.
    """

    __slots__ = ("enabled", "capacity", "_samples")

    def __init__(self, *, enabled: bool = False, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.enabled = bool(enabled)
        self.capacity = int(capacity)
        self._samples: deque[PerfSample] = deque(maxlen=self.capacity)

    @classmethod
    def from_env(cls, variable: str = "EMBER_PERF", *,
                 capacity: int = 256) -> "PerfProbe":
        value = os.environ.get(variable, "").strip().lower()
        return cls(enabled=value in {"1", "true", "yes", "on"},
                   capacity=capacity)

    def mark(self, name: str, **metadata: Any) -> None:
        if not self.enabled:
            return
        now_ns = perf_counter_ns()
        self._samples.append(PerfSample(
            str(name), now_ns, 0, tuple(metadata.items()),
        ))

    def record(self, name: str, *, started_ns: int, duration_ns: int,
               metadata: tuple[tuple[str, Any], ...] = ()) -> None:
        if not self.enabled:
            return
        self._samples.append(PerfSample(
            str(name), int(started_ns), max(0, int(duration_ns)), metadata,
        ))

    def span(self, name: str, **metadata: Any) -> AbstractContextManager[None]:
        if not self.enabled:
            return _NULL_SPAN
        return _ProbeSpan(self, str(name), tuple(metadata.items()))

    def snapshot(self) -> tuple[PerfSample, ...]:
        return tuple(self._samples)

    def clear(self) -> None:
        self._samples.clear()


__all__ = ["PerfProbe", "PerfSample"]
