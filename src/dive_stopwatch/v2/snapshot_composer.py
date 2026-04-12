from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .depth_estimation import descent_hold_depth_for_display, estimate_current_depth
from .dive_controller import DivePhase
from .dive_session import format_minutes_seconds
from .models import ModeV2, StateV2
from .presenter import format_tenths, stopwatch_primary_text


@dataclass(frozen=True)
class SnapshotFields:
    primary_text: str
    depth_text: str
    remaining_text: str
    detail_text: str


class _SnapshotOps(Protocol):
    def _active_air_break(self): ...
    def _active_air_break_elapsed(self) -> float: ...
    def _current_stop_anchor(self, profile) -> datetime | None: ...
    def _show_tsv(self, profile) -> bool: ...
    def _first_oxygen_shift_anchor(self, profile) -> datetime | None: ...
    def _stop_depth_for_number(self, stop_depths: list[int], stop_number: int) -> int | None: ...


class SnapshotComposer:
    def compose(self, engine: _SnapshotOps, *, state: StateV2, now: datetime, profile) -> SnapshotFields:
        # Builds the four display-heavy text fields shown in the shell GUI.
        return SnapshotFields(
            primary_text=self._primary_text(engine, state=state, now=now, profile=profile),
            depth_text=self._depth_text(engine, state=state, now=now, profile=profile),
            remaining_text=self._remaining_text(engine, state=state, now=now, profile=profile),
            detail_text=self._detail_text(engine, state=state, now=now, profile=profile),
        )

    def _remaining_text(self, engine: _SnapshotOps, *, state: StateV2, now: datetime, profile) -> str:
        # Remaining line shows the currently relevant countdown:
        # air-break countdown, bottom countdown, or stop countdown.
        if state.mode is not ModeV2.DIVE:
            return ""

        dive = state.dive
        if engine._active_air_break() is not None:
            left = max(300.0 - engine._active_air_break_elapsed(), 0.0)
            return f"Air Break: {format_minutes_seconds(left)} left"

        if dive.phase is DivePhase.BOTTOM:
            ls = dive.session.events.get("LS")
            if ls is None or profile is None or profile.table_bottom_time_min is None:
                return ""
            elapsed = max((now - ls.timestamp).total_seconds(), 0.0)
            left = max((profile.table_bottom_time_min * 60) - elapsed, 0.0)
            return f"Bottom: {format_minutes_seconds(left)} left"

        if dive.phase is DivePhase.ASCENT and dive._at_stop and profile is not None:
            latest = dive.latest_arrival_event()
            if latest is None:
                return ""
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = engine._stop_depth_for_number(stop_depths, latest.stop_number)
            required_min = profile.stops_fsw.get(current_depth) if current_depth is not None else None
            anchor = engine._current_stop_anchor(profile)
            if required_min is None or anchor is None:
                return ""
            remaining = (required_min * 60) - max((now - anchor).total_seconds(), 0.0)
            if remaining >= 0:
                return f"Stop: {format_minutes_seconds(remaining)} left"
            return f"Stop: +{format_minutes_seconds(abs(remaining))}"

        return ""

    def _detail_text(self, engine: _SnapshotOps, *, state: StateV2, now: datetime, profile) -> str:
        # Detail line shows active sub-timers (descent hold, delay, air break).
        if state.mode is not ModeV2.DIVE:
            return ""
        dive = state.dive
        latest_hold = dive.latest_stop_event()
        if (
            dive.phase is DivePhase.DESCENT
            and dive._awaiting_leave_stop
            and latest_hold is not None
            and latest_hold.kind == "start"
        ):
            depth = descent_hold_depth_for_display(
                controller=dive,
                start_time=latest_hold.timestamp,
                max_depth_fsw=state.parsed_depth(),
            )
            depth_text = f" ({depth} fsw)" if depth is not None else ""
            elapsed = (now - latest_hold.timestamp).total_seconds()
            return f"H{latest_hold.index}{depth_text}   {format_minutes_seconds(elapsed)}"
        latest_delay = state.dive.latest_ascent_delay_event()
        if latest_delay is not None and latest_delay.kind == "start":
            elapsed = (now - latest_delay.timestamp).total_seconds()
            depth_text = f" ({latest_delay.depth_fsw} fsw)" if latest_delay.depth_fsw is not None else ""
            return f"D{latest_delay.index}{depth_text}   {format_minutes_seconds(elapsed)}"
        if engine._active_air_break() is not None:
            elapsed = engine._active_air_break_elapsed()
            return f"Air Break {format_tenths(elapsed)}"
        return ""

    def _primary_text(self, engine: _SnapshotOps, *, state: StateV2, now: datetime, profile) -> str:
        # Primary line is the main live timer for the current state.
        if state.mode is ModeV2.STOPWATCH:
            return stopwatch_primary_text(state)

        dive = state.dive
        if dive.phase is DivePhase.READY:
            return "00:00.0"
        if dive.phase is DivePhase.CLEAN_TIME:
            status = dive.clean_time_status(now)
            return status["CT"]
        if dive.phase is DivePhase.DESCENT:
            ls = dive.session.events.get("LS")
            if ls is None:
                return "--:--.-"
            return format_tenths((now - ls.timestamp).total_seconds())
        if dive.phase is DivePhase.BOTTOM:
            ls = dive.session.events.get("LS")
            if ls is None:
                return "--:--.-"
            return format_tenths((now - ls.timestamp).total_seconds())
        if dive.phase is DivePhase.ASCENT and engine._show_tsv(profile):
            anchor = engine._first_oxygen_shift_anchor(profile)
            if anchor is None:
                return "00:00 TSV"
            elapsed = max((now - anchor).total_seconds(), 0.0)
            return f"{format_minutes_seconds(elapsed)} TSV"
        if dive.phase is DivePhase.ASCENT and dive._at_stop:
            anchor = engine._current_stop_anchor(profile)
            if anchor is None:
                return "--:--.-"
            return format_tenths((now - anchor).total_seconds())
        lb = dive.session.events.get("LB")
        if lb is None:
            return "--:--.-"
        return format_tenths((now - lb.timestamp).total_seconds())

    def _depth_text(self, engine: _SnapshotOps, *, state: StateV2, now: datetime, profile) -> str:
        # Depth line is estimated during travel and fixed when at bottom/stop.
        if state.mode is ModeV2.STOPWATCH:
            return ""
        depth = state.parsed_depth()
        dive = state.dive
        if dive.phase is DivePhase.DESCENT:
            estimate = estimate_current_depth(
                controller=dive,
                now=now,
                max_depth_fsw=depth,
                active_profile=profile,
            )
            return f"{estimate if estimate is not None else 0} fsw"
        if depth is None:
            return "Max -- fsw"
        if dive.phase is DivePhase.BOTTOM:
            return f"{depth} fsw"
        if dive.phase is DivePhase.ASCENT and dive._at_stop and profile is not None:
            latest = dive.latest_arrival_event()
            if latest is not None:
                stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
                current_depth = engine._stop_depth_for_number(stop_depths, latest.stop_number)
                if current_depth is not None:
                    return f"{current_depth} fsw"
        if dive.phase is DivePhase.ASCENT:
            estimate = estimate_current_depth(
                controller=dive,
                now=now,
                max_depth_fsw=depth,
                active_profile=profile,
            )
            return f"{estimate} fsw" if estimate is not None else "--"
        return f"{depth} fsw"
