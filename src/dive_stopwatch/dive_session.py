"""Dive session models for no-decompression dive flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

__all__ = [
    "DiveEvent",
    "DiveMetrics",
    "DiveSession",
    "ceil_minutes",
    "format_clock_time",
    "format_minutes_seconds",
]


def ceil_minutes(seconds: float) -> int:
    """Round a duration up to the next whole minute."""

    return max(math.ceil(seconds / 60), 0)


def format_minutes_seconds(seconds: float) -> str:
    """Format a duration as MM:SS, rounded up to the next whole second."""

    total_seconds = max(math.ceil(seconds), 0)
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_clock_time(timestamp: datetime) -> str:
    """Format a wall-clock event time as HH:MM:SS."""

    return timestamp.strftime("%H:%M:%S")


@dataclass(frozen=True)
class DiveEvent:
    """A logged dive event such as LS, RB, LB, or RS."""

    code: str
    timestamp: datetime


@dataclass(frozen=True)
class DiveMetrics:
    """Derived dive metrics based on clock timestamps."""

    dt_minutes: int
    bt_minutes: int
    at_minutes_seconds: str
    tdt_minutes: int
    ttd_minutes: int


class DiveSession:
    """Track a no-decompression dive using wall-clock events."""

    def __init__(self) -> None:
        self.events: dict[str, DiveEvent] = {}

    def leave_surface(self, at: datetime | None = None) -> DiveEvent:
        event = self._record_event("LS", at)
        return event

    def reach_bottom(self, at: datetime | None = None) -> DiveEvent:
        self._require_event("LS")
        event = self._record_event("RB", at)
        return event

    def leave_bottom(self, at: datetime | None = None) -> DiveEvent:
        self._require_event("RB")
        event = self._record_event("LB", at)
        return event

    def reach_surface(self, at: datetime | None = None) -> DiveEvent:
        self._require_event("LB")
        event = self._record_event("RS", at)
        return event

    def metrics(self) -> DiveMetrics:
        ls = self._require_event("LS").timestamp
        rb = self._require_event("RB").timestamp
        lb = self._require_event("LB").timestamp
        rs = self._require_event("RS").timestamp

        descent_seconds = (rb - ls).total_seconds()
        bottom_seconds = (lb - ls).total_seconds()
        ascent_seconds = (rs - lb).total_seconds()
        total_seconds = (rs - ls).total_seconds()

        return DiveMetrics(
            dt_minutes=ceil_minutes(descent_seconds),
            bt_minutes=ceil_minutes(bottom_seconds),
            at_minutes_seconds=format_minutes_seconds(ascent_seconds),
            tdt_minutes=ceil_minutes(ascent_seconds),
            ttd_minutes=ceil_minutes(total_seconds),
        )

    def summary(self) -> dict[str, str | int]:
        data: dict[str, str | int] = {}

        for code in ("LS", "RB", "LB", "RS"):
            event = self.events.get(code)
            if event is not None:
                data[code] = format_clock_time(event.timestamp)

        if all(code in self.events for code in ("LS", "RB")):
            data["DT"] = self.descent_time_minutes()

        if all(code in self.events for code in ("LS", "LB")):
            data["BT"] = self.bottom_time_minutes()

        if all(code in self.events for code in ("LB", "RS")):
            data["AT"] = self.ascent_time_display()
            data["TDT"] = self.total_decompression_time_minutes()

        if all(code in self.events for code in ("LS", "RS")):
            data["TTD"] = self.total_dive_time_minutes()

        if all(code in self.events for code in ("LS", "RB", "LB", "RS")):
            metrics = self.metrics()
            data["DT"] = metrics.dt_minutes
            data["BT"] = metrics.bt_minutes
            data["AT"] = metrics.at_minutes_seconds
            data["TDT"] = metrics.tdt_minutes
            data["TTD"] = metrics.ttd_minutes

        return data

    def descent_time_minutes(self) -> int:
        ls = self._require_event("LS").timestamp
        rb = self._require_event("RB").timestamp
        return ceil_minutes((rb - ls).total_seconds())

    def bottom_time_minutes(self) -> int:
        ls = self._require_event("LS").timestamp
        lb = self._require_event("LB").timestamp
        return ceil_minutes((lb - ls).total_seconds())

    def ascent_time_display(self) -> str:
        lb = self._require_event("LB").timestamp
        rs = self._require_event("RS").timestamp
        return format_minutes_seconds((rs - lb).total_seconds())

    def total_decompression_time_minutes(self) -> int:
        lb = self._require_event("LB").timestamp
        rs = self._require_event("RS").timestamp
        return ceil_minutes((rs - lb).total_seconds())

    def total_dive_time_minutes(self) -> int:
        ls = self._require_event("LS").timestamp
        rs = self._require_event("RS").timestamp
        return ceil_minutes((rs - ls).total_seconds())

    def _record_event(self, code: str, at: datetime | None) -> DiveEvent:
        if code in self.events:
            raise RuntimeError(f"{code} has already been recorded.")

        timestamp = at or datetime.now()
        previous_time = self._latest_timestamp()
        if previous_time is not None and timestamp < previous_time:
            raise RuntimeError("Dive events must be recorded in chronological order.")

        event = DiveEvent(code=code, timestamp=timestamp)
        self.events[code] = event
        return event

    def _latest_timestamp(self) -> datetime | None:
        if not self.events:
            return None
        return max(event.timestamp for event in self.events.values())

    def _require_event(self, code: str) -> DiveEvent:
        event = self.events.get(code)
        if event is None:
            raise RuntimeError(f"{code} must be recorded first.")
        return event
