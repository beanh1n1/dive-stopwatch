"""Dive mode state machine and clean-time tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Literal

from dive_stopwatch.v2.dive_session import DiveSession

__all__ = [
    "CleanTimeTimer",
    "DescentHoldEvent",
    "AscentStopEvent",
    "AscentDelayEvent",
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
class DescentHoldEvent:
    """A descent hold start/end marker."""

    kind: Literal["start", "end"]
    index: int
    timestamp: datetime
    depth_fsw: int | None = None


@dataclass(frozen=True)
class AscentStopEvent:
    """A reached/left decompression-stop marker during ascent."""

    kind: Literal["reach", "leave"]
    index: int
    timestamp: datetime
    depth_fsw: int | None = None

    @property
    def stop_number(self) -> int:
        return self.index


@dataclass(frozen=True)
class AscentDelayEvent:
    """A flagged ascent-delay marker."""

    kind: Literal["start", "end"]
    index: int
    timestamp: datetime
    depth_fsw: int | None = None


class DiveController:
    """Interpret stopwatch-style button presses as dive events."""

    def __init__(self) -> None:
        self.session = DiveSession()
        self.phase = DivePhase.READY
        self.clean_time: CleanTimeTimer | None = None
        self.descent_hold_events: list[DescentHoldEvent] = []
        self.ascent_stop_events: list[AscentStopEvent] = []
        self.ascent_delay_events: list[AscentDelayEvent] = []
        self._awaiting_leave_stop = False
        self._at_stop = False
        self.delay_to_first_stop_flagged = False

    def start(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is DivePhase.READY:
            event = self.session.leave_surface(at)
            self.phase = DivePhase.DESCENT
            return {
                "event": event.code,
                "clock": event.timestamp.strftime("%H:%M:%S"),
                "phase": self.phase.name,
            }

        if self.phase is DivePhase.DESCENT:
            if self._awaiting_leave_stop:
                raise RuntimeError("End the current hold before reaching bottom.")
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
            if self._at_stop:
                raise RuntimeError("Leave the current stop before progressing to the next stop.")
            return self._record_stop_arrival(at)

        raise RuntimeError("Start is only available for dive phase transitions.")

    def lap(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is DivePhase.DESCENT:
            return self._toggle_hold(at)

        if self.phase is DivePhase.BOTTOM:
            raise RuntimeError("Lap has no bottom-phase action.")

        if self.phase is DivePhase.ASCENT:
            if not self._at_stop:
                raise RuntimeError("Lap is only available to leave the current stop during ascent.")
            return self._record_stop_departure(at)

        raise RuntimeError("Lap is only available for hold timing during dive mode.")

    def stop(self, at: datetime | None = None) -> dict[str, str | int]:
        if self.phase is not DivePhase.ASCENT:
            raise RuntimeError("Stop is only available when surfacing from the dive.")
        if self._awaiting_leave_stop:
            raise RuntimeError("Record L before surfacing from the current stop.")
        if self._at_stop:
            raise RuntimeError("Start hold with Lap before surfacing from the current stop.")

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
        self.descent_hold_events.clear()
        self.ascent_stop_events.clear()
        self.ascent_delay_events.clear()
        self._awaiting_leave_stop = False
        self._at_stop = False
        self.delay_to_first_stop_flagged = False

    def clean_time_status(self, now: datetime | None = None) -> dict[str, str | bool]:
        if self.clean_time is None:
            raise RuntimeError("Clean time has not started yet.")

        return {
            "CT": self.clean_time.remaining_display(now),
            "complete": self.clean_time.complete(now),
        }

    def latest_stop_event(self) -> DescentHoldEvent | None:
        if not self.descent_hold_events:
            return None
        return self.descent_hold_events[-1]

    def latest_arrival_event(self) -> AscentStopEvent | None:
        for event in reversed(self.ascent_stop_events):
            if event.kind == "reach":
                return event
        return None

    def latest_stop_departure_event(self) -> AscentStopEvent | None:
        for event in reversed(self.ascent_stop_events):
            if event.kind == "leave":
                return event
        return None

    def latest_ascent_delay_event(self) -> AscentDelayEvent | None:
        if not self.ascent_delay_events:
            return None
        return self.ascent_delay_events[-1]

    def _toggle_hold(self, at: datetime | None = None) -> dict[str, str | int]:
        timestamp = at or datetime.now()
        kind: Literal["start", "end"] = "end" if self._awaiting_leave_stop else "start"
        hold_number = (len(self.descent_hold_events) // 2) + 1
        hold_event = DescentHoldEvent(
            kind=kind,
            index=hold_number,
            timestamp=timestamp,
        )
        self.descent_hold_events.append(hold_event)
        self._awaiting_leave_stop = not self._awaiting_leave_stop
        return {
            "event": "L" if kind == "end" else "R",
            "clock": hold_event.timestamp.strftime("%H:%M:%S"),
            "stop_number": hold_event.index,
            "phase": self.phase.name,
        }

    def _record_stop_arrival(self, at: datetime | None = None) -> dict[str, str | int]:
        timestamp = at or datetime.now()
        stop_number = sum(1 for event in self.ascent_stop_events if event.kind == "reach") + 1
        arrival_event = AscentStopEvent(kind="reach", index=stop_number, timestamp=timestamp)
        self.ascent_stop_events.append(arrival_event)
        self._at_stop = True
        self._close_active_ascent_delay(timestamp)
        return {
            "event": "R",
            "clock": arrival_event.timestamp.strftime("%H:%M:%S"),
            "stop_number": arrival_event.index,
            "phase": self.phase.name,
        }

    def _record_stop_departure(self, at: datetime | None = None) -> dict[str, str | int]:
        timestamp = at or datetime.now()
        latest_arrival = self.latest_arrival_event()
        if latest_arrival is None:
            raise RuntimeError("Cannot leave a stop before reaching one.")
        departure_event = AscentStopEvent(kind="leave", index=latest_arrival.index, timestamp=timestamp)
        self.ascent_stop_events.append(departure_event)
        self._at_stop = False
        self._close_active_ascent_delay(timestamp)
        return {
            "event": "L",
            "clock": departure_event.timestamp.strftime("%H:%M:%S"),
            "stop_number": departure_event.index,
            "phase": self.phase.name,
        }

    def first_stop_arrival_event(self) -> AscentStopEvent | None:
        for event in self.ascent_stop_events:
            if event.kind == "reach":
                return event
        return None

    def mark_ascent_delay_start(
        self,
        depth_fsw: int,
        at: datetime | None = None,
    ) -> AscentDelayEvent:
        if self.phase is not DivePhase.ASCENT or self._at_stop:
            raise RuntimeError("Delay can only be marked during ascent travel.")
        latest = self.latest_ascent_delay_event()
        if latest is not None and latest.kind == "start":
            return latest
        timestamp = at or datetime.now()
        delay_event = AscentDelayEvent(
            kind="start",
            index=(len([event for event in self.ascent_delay_events if event.kind == "start"]) + 1),
            timestamp=timestamp,
            depth_fsw=depth_fsw,
        )
        self.ascent_delay_events.append(delay_event)
        return delay_event

    def end_ascent_delay(
        self,
        at: datetime | None = None,
    ) -> AscentDelayEvent | None:
        timestamp = at or datetime.now()
        latest = self.latest_ascent_delay_event()
        if latest is None or latest.kind != "start":
            return None
        end_event = AscentDelayEvent(
            kind="end",
            index=latest.index,
            timestamp=timestamp,
            depth_fsw=latest.depth_fsw,
        )
        self.ascent_delay_events.append(end_event)
        return end_event

    def _close_active_ascent_delay(self, at: datetime) -> None:
        self.end_ascent_delay(at)

    def flag_delay_to_first_stop(self) -> dict[str, str]:
        if self.phase is not DivePhase.ASCENT:
            raise RuntimeError("Delay can only be flagged during ascent.")
        if self.first_stop_arrival_event() is not None:
            raise RuntimeError("Delay-to-first-stop prompt is only available before R1.")
        if self._at_stop:
            raise RuntimeError("Delay-to-first-stop prompt is not available while at a stop.")

        self.delay_to_first_stop_flagged = True
        return {"event": "DELAY_PROMPT", "phase": self.phase.name}
