"""Dive mode state machine and clean-time tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto

from dive_stopwatch.dive_session import DiveSession

__all__ = [
    "CleanTimeTimer",
    "DiveController",
    "DivePhase",
]


class DivePhase(Enum):
    """High-level no-decompression dive phases."""

    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    ASCENT = auto()
    CLEAN_TIME = auto()


@dataclass(frozen=True)
class CleanTimeTimer:
    """Ten-minute post-dive observation window."""

    started_at: datetime
    duration: timedelta = timedelta(minutes=10)

    @property
    def ends_at(self) -> datetime:
        return self.started_at + self.duration

    def remaining_seconds(self, now: datetime | None = None) -> int:
        current_time = now or datetime.now()
        delta = self.ends_at - current_time
        return max(int(delta.total_seconds()), 0)

    def remaining_display(self, now: datetime | None = None) -> str:
        total_seconds = self.remaining_seconds(now)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def complete(self, now: datetime | None = None) -> bool:
        return self.remaining_seconds(now) == 0


@dataclass(frozen=True)
class StopEvent:
    """An ascent stop arrival/departure marker."""

    code: str
    timestamp: datetime
    stop_number: int


class DiveController:
    """Interpret stopwatch-style button presses as dive events."""

    def __init__(self) -> None:
        self.session = DiveSession()
        self.phase = DivePhase.READY
        self.clean_time: CleanTimeTimer | None = None
        self.stop_events: list[StopEvent] = []
        self._awaiting_leave_stop = False

    def start(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is not DivePhase.READY:
            raise RuntimeError("Start is only available before the dive begins.")

        event = self.session.leave_surface(at)
        self.phase = DivePhase.DESCENT
        return {
            "event": event.code,
            "clock": event.timestamp.strftime("%H:%M:%S"),
            "phase": self.phase.name,
        }

    def lap(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is DivePhase.DESCENT:
            event = self.session.reach_bottom(at)
            self.phase = DivePhase.BOTTOM
            metrics = self.session.summary()
            return {
                "event": event.code,
                "clock": metrics["RB"],
                "DT": metrics["DT"],
                "phase": self.phase.name,
            }

        if self.phase is DivePhase.BOTTOM:
            event = self.session.leave_bottom(at)
            self.phase = DivePhase.ASCENT
            metrics = self.session.summary()
            return {
                "event": event.code,
                "clock": metrics["LB"],
                "BT": metrics["BT"],
                "phase": self.phase.name,
            }

        if self.phase is DivePhase.ASCENT:
            timestamp = at or datetime.now()
            code = "L" if self._awaiting_leave_stop else "R"
            stop_number = (len(self.stop_events) // 2) + 1
            stop_event = StopEvent(code=code, timestamp=timestamp, stop_number=stop_number)
            self.stop_events.append(stop_event)
            self._awaiting_leave_stop = not self._awaiting_leave_stop
            return {
                "event": stop_event.code,
                "clock": stop_event.timestamp.strftime("%H:%M:%S"),
                "stop_number": stop_event.stop_number,
                "phase": self.phase.name,
            }

        raise RuntimeError("Lap is only available at RB, LB, and ascent stop transitions during dive mode.")

    def stop(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is not DivePhase.ASCENT:
            raise RuntimeError("Stop is only available when surfacing from the dive.")
        if self._awaiting_leave_stop:
            raise RuntimeError("Record L before surfacing from the current stop.")

        event = self.session.reach_surface(at)
        self.phase = DivePhase.CLEAN_TIME
        self.clean_time = CleanTimeTimer(started_at=event.timestamp)
        metrics = self.session.summary()
        return {
            "event": event.code,
            "clock": metrics["RS"],
            "AT": metrics["AT"],
            "TDT": metrics["TDT"],
            "TTD": metrics["TTD"],
            "CT": self.clean_time.remaining_display(event.timestamp),
            "phase": self.phase.name,
        }

    def reset(self) -> None:
        if self.phase not in {DivePhase.READY, DivePhase.CLEAN_TIME}:
            raise RuntimeError("Cannot reset during an active dive.")
        self.session = DiveSession()
        self.phase = DivePhase.READY
        self.clean_time = None
        self.stop_events.clear()
        self._awaiting_leave_stop = False

    def clean_time_status(self, now: datetime | None = None) -> dict[str, str | bool]:
        if self.clean_time is None:
            raise RuntimeError("Clean time has not started yet.")

        return {
            "CT": self.clean_time.remaining_display(now),
            "complete": self.clean_time.complete(now),
        }

    def latest_stop_event(self) -> StopEvent | None:
        if not self.stop_events:
            return None
        return self.stop_events[-1]
