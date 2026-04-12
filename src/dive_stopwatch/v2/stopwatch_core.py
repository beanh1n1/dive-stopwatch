"""Core stopwatch models and helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto

__all__ = [
    "DeviceMode",
    "Mark",
    "Stopwatch",
    "StopwatchManager",
    "format_hhmmss",
]


class DeviceMode(Enum):
    """High-level device state for the prototype."""

    STOPWATCH = auto()
    DIVE = auto()


@dataclass(frozen=True)
class Mark:
    """A recorded lap or split event."""

    index: int
    kind: str
    lap_seconds: float
    total_seconds: float


@dataclass
class Stopwatch:
    """Seiko-style stopwatch with lap and split behavior."""

    running: bool = False
    _start_mark: float | None = None
    _elapsed_before_start: float = 0.0
    _lap_base_total: float = 0.0
    _frozen_display_total: float | None = None
    marks: list[Mark] = field(default_factory=list)

    def start_stop(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.running:
            return
        self._start_mark = time.monotonic()
        self.running = True

    def stop(self) -> None:
        if not self.running:
            return
        now = time.monotonic()
        self._elapsed_before_start += now - (self._start_mark or now)
        self._start_mark = None
        self.running = False

    def reset(self) -> None:
        if self.running:
            raise RuntimeError("Cannot reset while running. Stop first.")
        self._start_mark = None
        self._elapsed_before_start = 0.0
        self._lap_base_total = 0.0
        self._frozen_display_total = None
        self.marks.clear()

    def total_elapsed(self) -> float:
        if not self.running:
            return self._elapsed_before_start
        now = time.monotonic()
        return self._elapsed_before_start + (now - (self._start_mark or now))

    def display_time(self) -> float:
        if self._frozen_display_total is not None:
            return self._frozen_display_total
        return self.total_elapsed()

    def split(self) -> Mark:
        total = self.total_elapsed()
        lap = total - self._lap_base_total

        if self._frozen_display_total is None:
            self._frozen_display_total = total
            kind = "SPLIT"
        else:
            self._frozen_display_total = None
            kind = "SPLIT_RELEASE"

        mark = Mark(
            index=len(self.marks) + 1,
            kind=kind,
            lap_seconds=lap,
            total_seconds=total,
        )
        self.marks.append(mark)
        return mark

    def lap(self) -> Mark:
        total = self.total_elapsed()
        lap = total - self._lap_base_total
        self._lap_base_total = total
        mark = Mark(
            index=len(self.marks) + 1,
            kind="LAP",
            lap_seconds=lap,
            total_seconds=total,
        )
        self.marks.append(mark)
        return mark


class StopwatchManager:
    """Manage multiple named stopwatches."""

    def __init__(self) -> None:
        self.timers: dict[str, Stopwatch] = {}

    def get(self, name: str) -> Stopwatch:
        if name not in self.timers:
            self.timers[name] = Stopwatch()
        return self.timers[name]

    def names(self) -> list[str]:
        return sorted(self.timers.keys())


def format_hhmmss(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""

    total_milliseconds = max(int(round(seconds * 1000)), 0)
    whole_seconds, milliseconds = divmod(total_milliseconds, 1000)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
