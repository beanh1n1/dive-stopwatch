from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum, auto
import math

from ..air_o2_profiles import SurfaceProfile, build_surface_profile
from ..air_o2_snapshot import Snapshot
from ..surd_engine import SURDChamberPlan, SURDChamberPlanSegment, build_surd_chamber_plan
from .protocol import OperatorAction
from .snapshot_projection import SnapshotProjection


SURD_SURFACE_INTERVAL_SEC = 5 * 60
SURD_ASCENT_TO_SURFACE_SEC = 60
SURD_UNDRESS_SEC = 60
SURD_AIR_BREAK_SEC = 5 * 60
SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC = 7 * 60
SURD_CLEAN_TIME_SEC = 10 * 60

class RedesignSURDPhase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL_TO_WATER_STOP = auto()
    AT_WATER_STOP = auto()
    SURFACE_ASCENT = auto()
    UNDRESS = auto()
    SURFACE_TO_CHAMBER_50 = auto()
    CHAMBER_WAITING_ON_O2 = auto()
    CHAMBER_ON_O2 = auto()
    CHAMBER_OFF_O2 = auto()
    CHAMBER_AIR_BREAK = auto()
    COMPLETE = auto()


class RedesignSURDEntryKind(Enum):
    L40_NORMAL = auto()


@dataclass(frozen=True)
class RedesignSURDHandoff:
    entry_kind: RedesignSURDEntryKind
    source_mode_text: str
    input_depth_fsw: int
    input_bottom_time_min: int
    source_profile_schedule_text: str
    source_table_depth_fsw: int | None
    source_table_bottom_time_min: int | None
    left_water_stop_depth_fsw: int | None
    remaining_in_water_obligation_sec: float | None
    handed_off_at: datetime
    audit_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class SURDAuditEntry:
    code: str
    at: datetime
    message: str


@dataclass(frozen=True)
class WaterStop:
    index: int
    depth_fsw: int
    duration_min: int


@dataclass(frozen=True)
class WaterPlan:
    surface_profile: SurfaceProfile
    stops: tuple[WaterStop, ...]
    current_stop_index: int | None = None


@dataclass(frozen=True)
class RedesignSURDState:
    depth_input_fsw: int | None = None
    handoff: RedesignSURDHandoff | None = None
    source_profile_schedule_text: str = ""
    phase: RedesignSURDPhase = RedesignSURDPhase.READY
    bottom_started_at: datetime | None = None
    water_travel_started_at: datetime | None = None
    water_stop_started_at: datetime | None = None
    water_plan: WaterPlan | None = None
    surface_interval_started_at: datetime | None = None
    phase_started_at: datetime | None = None
    surface_penalty_half_periods: int = 0
    chamber_plan: SURDChamberPlan | None = None
    chamber_depth_fsw: int | None = None
    current_segment_index: int | None = None
    segment_started_at: datetime | None = None
    segment_elapsed_before_pause_sec: float = 0.0
    off_o2_started_at: datetime | None = None
    air_break_started_at: datetime | None = None
    audit: tuple[SURDAuditEntry, ...] = ()
    test_time_offset_sec: float = 0.0


def _format_tenths(seconds: float) -> str:
    total_tenths = max(int(round(seconds * 10)), 0)
    minutes, tenths_total = divmod(total_tenths, 600)
    seconds_whole, tenths = divmod(tenths_total, 10)
    return f"{minutes:02d}:{seconds_whole:02d}.{tenths}"


def _format_mmss(seconds: float) -> str:
    whole = max(int(math.ceil(seconds)), 0)
    minutes, secs = divmod(whole, 60)
    return f"{minutes:02d}:{secs:02d}"


def _audit(code: str, at: datetime, message: str) -> SURDAuditEntry:
    return SURDAuditEntry(code=code, at=at, message=message)


class RedesignSURDEngine:
    def __init__(self, *, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self.state = RedesignSURDState()

    def _now(self) -> datetime:
        return self._now_provider() + timedelta(seconds=self.state.test_time_offset_sec)

    def set_depth_text(self, raw: str) -> None:
        stripped = raw.strip()
        if not stripped:
            self.state = replace(self.state, depth_input_fsw=None)
            return
        try:
            depth = int(stripped)
        except ValueError:
            depth = None
        self.state = replace(self.state, depth_input_fsw=depth if depth and depth > 0 else None)

    def advance_test_time(self, delta_seconds: float) -> None:
        self.state = replace(
            self.state,
            test_time_offset_sec=max(self.state.test_time_offset_sec + delta_seconds, 0.0),
        )

    def reset_test_time(self) -> None:
        self.state = replace(self.state, test_time_offset_sec=0.0)

    def recall_lines(self) -> tuple[str, ...]:
        return tuple(entry.message for entry in self.state.audit[-30:])

    def dispatch(self, action: OperatorAction) -> None:
        now = self._now()
        if action is OperatorAction.RESET:
            self.state = RedesignSURDState(depth_input_fsw=self.state.depth_input_fsw, test_time_offset_sec=self.state.test_time_offset_sec)
            return
        if action is OperatorAction.LEAVE_SURFACE:
            self._leave_surface(now)
            return
        if action is OperatorAction.REACH_BOTTOM:
            self._reach_bottom(now)
            return
        if action is OperatorAction.LEAVE_BOTTOM:
            self._leave_bottom(now)
            return
        if action is OperatorAction.REACH_STOP:
            self._reach_water_stop(now)
            return
        if action is OperatorAction.LEAVE_STOP:
            self._leave_water_stop(now)
            return
        if action is OperatorAction.REACH_SURFACE:
            self._reach_surface(now)
            return
        if action is OperatorAction.LEAVE_SURFACE_INTERVAL:
            self._leave_surface_interval(now)
            return
        if action is OperatorAction.REACH_CHAMBER_50:
            self._reach_chamber_50(now)
            return
        if action is OperatorAction.TOGGLE_CHAMBER_O2:
            self._toggle_o2(now)
            return
        if action is OperatorAction.ADVANCE_CHAMBER:
            self._advance_chamber(now)
            return

    def snapshot(self) -> Snapshot:
        now = self._now()
        return self._snapshot(now)

    def start_handoff(self, handoff: RedesignSURDHandoff) -> None:
        surface_profile = build_surface_profile(handoff.input_depth_fsw, handoff.input_bottom_time_min)
        stops = tuple(WaterStop(index=i, depth_fsw=stop.depth_fsw, duration_min=stop.duration_min) for i, stop in enumerate(surface_profile.in_water_stops, start=1))
        self.state = RedesignSURDState(
            depth_input_fsw=handoff.input_depth_fsw,
            handoff=handoff,
            source_profile_schedule_text=handoff.source_profile_schedule_text,
            phase=RedesignSURDPhase.SURFACE_ASCENT,
            water_plan=WaterPlan(surface_profile=surface_profile, stops=stops, current_stop_index=len(stops)),
            surface_interval_started_at=handoff.handed_off_at,
            phase_started_at=handoff.handed_off_at,
            audit=tuple(_audit("HANDOFF_LOG", handoff.handed_off_at, line) for line in handoff.audit_lines)
            + (
                _audit("SURD_START", handoff.handed_off_at, f"SurD start from 40 fsw {handoff.handed_off_at.strftime('%H:%M:%S')}"),
                _audit("TRAVEL_40_SURFACE", handoff.handed_off_at, f"Traveling 40 -> Surface {handoff.handed_off_at.strftime('%H:%M:%S')}"),
            ),
            test_time_offset_sec=self.state.test_time_offset_sec,
        )

    def _leave_surface(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.READY:
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.DESCENT,
            bottom_started_at=now,
            audit=self.state.audit + (_audit("LS", now, f"LS {now.strftime('%H:%M:%S')}"),),
        )

    def _reach_bottom(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.DESCENT:
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.BOTTOM,
            audit=self.state.audit + (_audit("RB", now, f"RB {now.strftime('%H:%M:%S')}"),),
        )

    def _leave_bottom(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.BOTTOM or self.state.bottom_started_at is None or self.state.depth_input_fsw is None:
            return
        bottom_time_min = max(math.ceil((now - self.state.bottom_started_at).total_seconds() / 60), 1)
        surface_profile = build_surface_profile(self.state.depth_input_fsw, bottom_time_min)
        stops = tuple(WaterStop(index=i, depth_fsw=stop.depth_fsw, duration_min=stop.duration_min) for i, stop in enumerate(surface_profile.in_water_stops, start=1))
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.TRAVEL_TO_WATER_STOP,
            water_plan=WaterPlan(surface_profile=surface_profile, stops=stops),
            water_travel_started_at=now,
            audit=self.state.audit + (_audit("LB", now, f"LB {now.strftime('%H:%M:%S')}"),),
        )

    def _reach_water_stop(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.TRAVEL_TO_WATER_STOP or self.state.water_plan is None:
            return
        next_index = 1 if self.state.water_plan.current_stop_index is None else self.state.water_plan.current_stop_index + 1
        if next_index > len(self.state.water_plan.stops):
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.AT_WATER_STOP,
            water_plan=replace(self.state.water_plan, current_stop_index=next_index),
            water_stop_started_at=now,
            audit=self.state.audit + (_audit(f"R{next_index}", now, f"R{next_index} {now.strftime('%H:%M:%S')}"),),
        )

    def _leave_water_stop(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.AT_WATER_STOP or self.state.water_plan is None:
            return
        current_index = self.state.water_plan.current_stop_index
        if current_index is None:
            return
        current_stop = self.state.water_plan.stops[current_index - 1]
        if current_index == len(self.state.water_plan.stops):
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.SURFACE_ASCENT,
                surface_interval_started_at=now,
                phase_started_at=now,
                audit=self.state.audit
                + (
                    _audit(f"L{current_index}", now, f"L{current_index} {now.strftime('%H:%M:%S')}"),
                    _audit("SURD_START", now, f"SurD start from 40 fsw {now.strftime('%H:%M:%S')}"),
                    _audit("TRAVEL_40_SURFACE", now, f"Traveling 40 -> Surface {now.strftime('%H:%M:%S')}"),
                ),
            )
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.TRAVEL_TO_WATER_STOP,
            water_travel_started_at=now,
            audit=self.state.audit + (_audit(f"L{current_index}", now, f"L{current_index} {now.strftime('%H:%M:%S')}"),),
        )

    def _reach_surface(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.SURFACE_ASCENT:
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.UNDRESS,
            phase_started_at=now,
            audit=self.state.audit
            + (
                _audit("RS", now, f"RS {now.strftime('%H:%M:%S')}"),
                _audit("UNDRESS", now, f"Undress {now.strftime('%H:%M:%S')}"),
            ),
        )

    def _leave_surface_interval(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.UNDRESS:
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.SURFACE_TO_CHAMBER_50,
            phase_started_at=now,
            audit=self.state.audit
            + (
                _audit("LS", now, f"LS {now.strftime('%H:%M:%S')}"),
                _audit("TRAVEL_SURFACE_50", now, f"Traveling Surface -> Chamber 50 {now.strftime('%H:%M:%S')}"),
            ),
        )

    def _reach_chamber_50(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.SURFACE_TO_CHAMBER_50 or self.state.water_plan is None or self.state.surface_interval_started_at is None:
            return
        interval_elapsed = max((now - self.state.surface_interval_started_at).total_seconds(), 0.0)
        penalty = 1 if SURD_SURFACE_INTERVAL_SEC < interval_elapsed <= SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC else 0
        extra_logs: tuple[SURDAuditEntry, ...] = ()
        if penalty:
            extra_logs = (_audit("SURFACE_INTERVAL_PENALTY", now, f"Surface interval penalty (+15 O2 @ 50) {now.strftime('%H:%M:%S')}"),)
        elif interval_elapsed > SURD_SURFACE_INTERVAL_SEC:
            extra_logs = (_audit("SURFACE_INTERVAL_EXCEEDED", now, f"Surface interval exceeded 05:00 {now.strftime('%H:%M:%S')}"),)
        chamber_plan = build_surd_chamber_plan(
            self.state.water_plan.surface_profile.chamber_o2_half_periods,
            surface_interval_penalty_half_periods=penalty,
        )
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.CHAMBER_WAITING_ON_O2,
            phase_started_at=now,
            surface_penalty_half_periods=penalty,
            chamber_plan=chamber_plan,
            chamber_depth_fsw=50,
            current_segment_index=0,
            segment_started_at=None,
            segment_elapsed_before_pause_sec=0.0,
            off_o2_started_at=None,
            air_break_started_at=None,
            audit=self.state.audit
            + extra_logs
            + (
                _audit("RB", now, f"RB {now.strftime('%H:%M:%S')}"),
                _audit("CHAMBER_50", now, f"Chamber 50 {now.strftime('%H:%M:%S')}"),
            ),
        )

    def _toggle_o2(self, now: datetime) -> None:
        segment = self._current_segment()
        if segment is None:
            return
        if self.state.phase is RedesignSURDPhase.CHAMBER_WAITING_ON_O2:
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.CHAMBER_ON_O2,
                segment_started_at=now,
                segment_elapsed_before_pause_sec=0.0,
                off_o2_started_at=None,
                audit=self.state.audit
                + (
                    _audit("ON_O2", now, f"On O2 {segment.depth_fsw} {now.strftime('%H:%M:%S')}"),
                    _audit("CHAMBER_O2", now, f"{segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}"),
                ),
            )
            return
        if self.state.phase is RedesignSURDPhase.CHAMBER_ON_O2 and self.state.segment_started_at is not None:
            elapsed = self._segment_elapsed(now)
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.CHAMBER_OFF_O2,
                segment_elapsed_before_pause_sec=elapsed,
                off_o2_started_at=now,
                audit=self.state.audit + (_audit("OFF_O2", now, f"Off O2 {now.strftime('%H:%M:%S')}"),),
            )
            return
        if self.state.phase is RedesignSURDPhase.CHAMBER_OFF_O2:
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.CHAMBER_ON_O2,
                segment_started_at=now,
                off_o2_started_at=None,
                audit=self.state.audit
                + (
                    _audit("ON_O2", now, f"On O2 {segment.depth_fsw} {now.strftime('%H:%M:%S')}"),
                    _audit("CHAMBER_O2", now, f"{segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}"),
                ),
            )

    def _advance_chamber(self, now: datetime) -> None:
        if self.state.phase is RedesignSURDPhase.CHAMBER_AIR_BREAK:
            self._advance_air_break(now)
            return
        if self.state.phase not in {RedesignSURDPhase.CHAMBER_ON_O2, RedesignSURDPhase.CHAMBER_WAITING_ON_O2}:
            return
        segment = self._current_segment()
        if segment is None:
            return
        if self.state.phase is RedesignSURDPhase.CHAMBER_WAITING_ON_O2:
            return
        if self._segment_elapsed(now) < segment.duration_sec:
            return
        next_segment = self._next_segment()
        if next_segment is None:
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.COMPLETE,
                phase_started_at=now,
                chamber_depth_fsw=0,
                air_break_started_at=None,
                audit=self.state.audit
                + (
                    _audit("RS", now, f"RS {now.strftime('%H:%M:%S')}"),
                    _audit("SURFACE", now, f"Surface {now.strftime('%H:%M:%S')}"),
                ),
            )
            return
        if next_segment.period_number == segment.period_number and next_segment.depth_fsw != segment.depth_fsw:
            self.state = replace(
                self.state,
                phase=RedesignSURDPhase.CHAMBER_ON_O2,
                chamber_depth_fsw=next_segment.depth_fsw,
                current_segment_index=next_segment.segment_index,
                segment_started_at=now,
                segment_elapsed_before_pause_sec=0.0,
                off_o2_started_at=None,
                audit=self.state.audit
                + (
                    _audit(f"CHAMBER_{next_segment.depth_fsw}", now, f"Chamber {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}"),
                    _audit("CHAMBER_O2", now, f"{next_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}"),
                ),
            )
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.CHAMBER_AIR_BREAK,
            air_break_started_at=now,
            audit=self.state.audit
            + (
                _audit("AIR_BREAK_START", now, f"Air break start {now.strftime('%H:%M:%S')}"),
                _audit("CHAMBER_AIR_BREAK", now, f"{self.state.chamber_depth_fsw or 40} fsw Air Break {now.strftime('%H:%M:%S')}"),
            ),
        )

    def _advance_air_break(self, now: datetime) -> None:
        if self.state.phase is not RedesignSURDPhase.CHAMBER_AIR_BREAK or self.state.air_break_started_at is None:
            return
        if (now - self.state.air_break_started_at).total_seconds() < SURD_AIR_BREAK_SEC:
            return
        next_segment = self._next_segment()
        if next_segment is None:
            return
        if next_segment.depth_fsw != self.state.chamber_depth_fsw:
            self.state = replace(
                self.state,
                chamber_depth_fsw=next_segment.depth_fsw,
                audit=self.state.audit + (_audit(f"CHAMBER_{next_segment.depth_fsw}", now, f"Chamber {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}"),),
            )
            return
        self.state = replace(
            self.state,
            phase=RedesignSURDPhase.CHAMBER_ON_O2,
            current_segment_index=next_segment.segment_index,
            segment_started_at=now,
            segment_elapsed_before_pause_sec=0.0,
            off_o2_started_at=None,
            air_break_started_at=None,
            audit=self.state.audit
            + (
                _audit("ON_O2", now, f"On O2 {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}"),
                _audit("CHAMBER_O2", now, f"{next_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}"),
            ),
        )

    def _current_segment(self) -> SURDChamberPlanSegment | None:
        if self.state.chamber_plan is None or self.state.current_segment_index is None:
            return None
        if self.state.current_segment_index < 0 or self.state.current_segment_index >= len(self.state.chamber_plan.segments):
            return None
        return self.state.chamber_plan.segments[self.state.current_segment_index]

    def _next_segment(self) -> SURDChamberPlanSegment | None:
        current = self._current_segment()
        if current is None or self.state.chamber_plan is None:
            return None
        next_index = current.segment_index + 1
        if next_index >= len(self.state.chamber_plan.segments):
            return None
        return self.state.chamber_plan.segments[next_index]

    def _segment_elapsed(self, now: datetime) -> float:
        if self.state.phase not in {RedesignSURDPhase.CHAMBER_ON_O2, RedesignSURDPhase.CHAMBER_OFF_O2}:
            return 0.0
        elapsed = self.state.segment_elapsed_before_pause_sec
        if self.state.phase is RedesignSURDPhase.CHAMBER_ON_O2 and self.state.segment_started_at is not None:
            elapsed += max((now - self.state.segment_started_at).total_seconds(), 0.0)
        return elapsed

    def _snapshot(self, now: datetime) -> Snapshot:
        phase = self.state.phase
        projection = SnapshotProjection(mode_text="SURD", depth_text="Surface")

        if phase is RedesignSURDPhase.READY:
            projection.status_text = "READY"
            projection.status_value_text = "Ready"
            projection.depth_text = f"{self.state.depth_input_fsw} fsw" if self.state.depth_input_fsw is not None else "Max -- fsw"
            projection.primary_button_label = "Leave Surface"
        elif phase is RedesignSURDPhase.DESCENT:
            projection.status_text = "DESCENT"
            projection.status_value_text = "Descent"
            projection.primary_text = _format_tenths(max((now - self.state.bottom_started_at).total_seconds(), 0.0)) if self.state.bottom_started_at else "00:00.0"
            projection.depth_text = f"{self.state.depth_input_fsw} fsw" if self.state.depth_input_fsw is not None else "--"
            projection.primary_button_label = "Reach Bottom"
        elif phase is RedesignSURDPhase.BOTTOM:
            projection.status_text = "BOTTOM"
            projection.status_value_text = "Bottom"
            projection.primary_text = _format_tenths(max((now - self.state.bottom_started_at).total_seconds(), 0.0)) if self.state.bottom_started_at else "00:00.0"
            projection.depth_text = f"{self.state.depth_input_fsw} fsw" if self.state.depth_input_fsw is not None else "--"
            projection.primary_button_label = "Leave Bottom"
        elif phase is RedesignSURDPhase.TRAVEL_TO_WATER_STOP:
            projection.status_text = "TRAVELING"
            projection.status_value_text = "Traveling"
            projection.primary_text = _format_tenths(max((now - self.state.water_travel_started_at).total_seconds(), 0.0)) if self.state.water_travel_started_at else "00:00.0"
            next_stop = self._next_water_stop()
            projection.depth_text = f"{next_stop.depth_fsw} fsw" if next_stop is not None else "Surface"
            projection.summary_text = f"Next: {next_stop.depth_fsw} fsw for {next_stop.duration_min} min" if next_stop is not None else "Next: Surface"
            projection.primary_button_label = "Reach Stop"
        elif phase is RedesignSURDPhase.AT_WATER_STOP:
            projection.status_text = "AT STOP"
            projection.status_value_text = "At Stop"
            current_stop = self._current_water_stop()
            if current_stop is not None and self.state.water_stop_started_at is not None:
                elapsed = max((now - self.state.water_stop_started_at).total_seconds(), 0.0)
                projection.primary_text = _format_tenths(elapsed)
                remaining = max((current_stop.duration_min * 60) - elapsed, 0.0)
                projection.depth_text = f"{current_stop.depth_fsw} fsw"
                projection.depth_timer_text = f"{_format_mmss(remaining)} left"
                if current_stop.index == len(self.state.water_plan.stops):
                    projection.summary_text = "Next: 40 fsw -> Surface"
                else:
                    next_stop = self._next_water_stop()
                    projection.summary_text = f"Next: {next_stop.depth_fsw} fsw for {next_stop.duration_min} min" if next_stop is not None else "Next: Surface"
            projection.primary_button_label = "Leave Stop"
        elif phase in {RedesignSURDPhase.SURFACE_ASCENT, RedesignSURDPhase.UNDRESS, RedesignSURDPhase.SURFACE_TO_CHAMBER_50}:
            interval_elapsed = self._surface_interval_elapsed(now)
            overtime = max(interval_elapsed - SURD_SURFACE_INTERVAL_SEC, 0.0)
            projection.primary_text = _format_tenths(self._phase_elapsed(now))
            if overtime > 0:
                projection.depth_timer_text = f"+{_format_mmss(overtime)}"
                projection.depth_timer_kind = "warning" if interval_elapsed <= SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC else "air_break"
                projection.primary_value_kind = projection.depth_timer_kind
            else:
                projection.depth_timer_text = f"{_format_mmss(SURD_SURFACE_INTERVAL_SEC - interval_elapsed)} left"
            if phase is RedesignSURDPhase.SURFACE_ASCENT:
                projection.status_text = "40 -> Surface"
                projection.status_value_text = "40 -> Surface"
                ascent_elapsed = self._phase_elapsed(now)
                current_depth = max(int(round(40 - ((40 / max(SURD_ASCENT_TO_SURFACE_SEC, 1)) * min(ascent_elapsed, SURD_ASCENT_TO_SURFACE_SEC)))), 0)
                projection.depth_text = "Surface" if current_depth <= 0 else f"{current_depth} fsw"
                projection.summary_text = "Next: Undress"
                projection.primary_button_label = "Reach Surface"
            elif phase is RedesignSURDPhase.UNDRESS:
                projection.status_text = "Undress"
                projection.status_value_text = "Undress"
                projection.depth_text = "Surface"
                projection.summary_text = "Next: Surface -> 50 fsw"
                projection.primary_button_label = "Leave Surface"
            else:
                projection.status_text = "Surface -> 50 fsw"
                projection.status_value_text = "Surface -> 50 fsw"
                projection.depth_text = "50 fsw"
                projection.summary_text = "Next: 50 fsw"
                projection.primary_button_label = "Reach Bottom"
            if SURD_SURFACE_INTERVAL_SEC < interval_elapsed <= SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC:
                projection.summary_text = "Next: Chamber 50 with penalty"
                projection.summary_value_kind = "warning"
            elif interval_elapsed > SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC:
                projection.summary_text = "Surface interval exceeded"
                projection.summary_value_kind = "air_break"
        elif phase is RedesignSURDPhase.CHAMBER_WAITING_ON_O2:
            segment = self._current_segment()
            projection.status_text = f"{self.state.chamber_depth_fsw or 50} fsw"
            projection.status_value_text = projection.status_text
            projection.depth_text = projection.status_text
            if segment is not None:
                projection.summary_text = f"Next: {segment.depth_fsw} fsw for {int(segment.duration_sec / 60)} min"
            projection.secondary_button_label = "On O2"
        elif phase in {RedesignSURDPhase.CHAMBER_ON_O2, RedesignSURDPhase.CHAMBER_OFF_O2}:
            segment = self._current_segment()
            if segment is not None:
                segment_elapsed = self._segment_elapsed(now)
                segment_remaining = max(segment.duration_sec - segment_elapsed, 0.0)
                projection.depth_text = f"{self.state.chamber_depth_fsw or segment.depth_fsw} fsw"
                if phase is RedesignSURDPhase.CHAMBER_OFF_O2:
                    off_elapsed = max((now - self.state.off_o2_started_at).total_seconds(), 0.0) if self.state.off_o2_started_at else 0.0
                    projection.status_text = "OFF O2"
                    projection.status_value_text = "Off O2"
                    projection.status_value_kind = "off_o2"
                    projection.primary_text = _format_tenths(off_elapsed)
                    projection.primary_value_kind = "off_o2"
                    projection.summary_text = "Next: On O2"
                    projection.summary_value_kind = "o2"
                    projection.detail_text = f"Off O2 {_format_mmss(off_elapsed)} | {_format_mmss(segment_remaining)} left"
                    projection.secondary_button_label = "On O2"
                else:
                    projection.status_text = f"{segment.depth_fsw} fsw O2"
                    projection.status_value_text = "On O2"
                    projection.status_value_kind = "o2"
                    projection.primary_value_kind = "o2"
                    projection.depth_timer_text = f"{_format_mmss(segment_remaining)} left"
                    projection.depth_timer_kind = "o2"
                    projection.secondary_button_label = "Off O2"
                    next_segment = self._next_segment()
                    if segment.period_number == 1 and segment.depth_fsw == 50:
                        projection.summary_text = f"Next: {next_segment.depth_fsw} fsw for {int(next_segment.duration_sec / 60)} min" if next_segment is not None else "Next: Surface"
                    elif segment.period_number == 1 and segment.depth_fsw == 40:
                        projection.summary_text = "First O2 period: 40 fsw segment"
                    else:
                        projection.summary_text = f"O2 period {segment.period_number}"
                    if segment_elapsed >= segment.duration_sec:
                        if next_segment is None:
                            projection.summary_text = "Next: Surface"
                            projection.primary_button_label = "Reach Surface"
                        elif next_segment.period_number == segment.period_number and next_segment.depth_fsw != segment.depth_fsw:
                            projection.summary_text = f"Next: Move chamber to {next_segment.depth_fsw} fsw"
                            projection.primary_button_label = f"Chamber {next_segment.depth_fsw}"
                        elif next_segment.period_number > segment.period_number:
                            projection.summary_text = "Next: Start air break"
                            projection.primary_button_label = "Start Air Break"
                        else:
                            projection.summary_text = f"O2 period {segment.period_number}"
            else:
                projection.status_text = "CHAMBER"
                projection.status_value_text = "Chamber"
        elif phase is RedesignSURDPhase.CHAMBER_AIR_BREAK:
            projection.status_text = f"{self.state.chamber_depth_fsw or 40} fsw Air Break"
            projection.status_value_text = "Air Break"
            projection.status_value_kind = "air_break"
            projection.primary_value_kind = "air_break"
            projection.depth_text = f"{self.state.chamber_depth_fsw or 40} fsw"
            air_elapsed = max((now - self.state.air_break_started_at).total_seconds(), 0.0) if self.state.air_break_started_at else 0.0
            remaining = max(SURD_AIR_BREAK_SEC - air_elapsed, 0.0)
            projection.primary_text = _format_tenths(air_elapsed)
            projection.depth_timer_text = f"{_format_mmss(remaining)} left"
            projection.depth_timer_kind = "air_break"
            projection.summary_text = "Chamber air break"
            if air_elapsed >= SURD_AIR_BREAK_SEC:
                next_segment = self._next_segment()
                if next_segment is not None and next_segment.depth_fsw != self.state.chamber_depth_fsw:
                    projection.summary_text = f"Next: Move chamber to {next_segment.depth_fsw} fsw"
                    projection.primary_button_label = f"Chamber {next_segment.depth_fsw}"
                elif next_segment is not None:
                    projection.summary_text = f"Next: Resume O2 period {next_segment.period_number}"
                    projection.primary_button_label = "Resume O2"
        elif phase is RedesignSURDPhase.COMPLETE:
            projection.status_text = "CLEAN TIME"
            projection.status_value_text = "Clean Time"
            remaining = max(SURD_CLEAN_TIME_SEC - self._phase_elapsed(now), 0.0)
            projection.primary_text = _format_mmss(remaining)
            projection.depth_text = "Surface"
            projection.depth_timer_text = f"{_format_mmss(remaining)} left"

        projection.profile_schedule_text = self.state.source_profile_schedule_text or (_surface_schedule_text(self.state.water_plan.surface_profile) if self.state.water_plan is not None else "")
        return projection.to_snapshot()

    def _phase_elapsed(self, now: datetime) -> float:
        if self.state.phase_started_at is None:
            return 0.0
        return max((now - self.state.phase_started_at).total_seconds(), 0.0)

    def _surface_interval_elapsed(self, now: datetime) -> float:
        if self.state.surface_interval_started_at is None:
            return 0.0
        return max((now - self.state.surface_interval_started_at).total_seconds(), 0.0)

    def _current_water_stop(self) -> WaterStop | None:
        if self.state.water_plan is None or self.state.water_plan.current_stop_index is None:
            return None
        return self.state.water_plan.stops[self.state.water_plan.current_stop_index - 1]

    def _next_water_stop(self) -> WaterStop | None:
        if self.state.water_plan is None:
            return None
        next_index = 1 if self.state.water_plan.current_stop_index is None else self.state.water_plan.current_stop_index + 1
        if next_index < 1 or next_index > len(self.state.water_plan.stops):
            return None
        return self.state.water_plan.stops[next_index - 1]


def _surface_schedule_text(profile: SurfaceProfile) -> str:
    repeat = f" {profile.repeat_group}" if profile.repeat_group else ""
    return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}{repeat}"
