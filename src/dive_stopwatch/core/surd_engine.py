from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
import math

from .air_o2_profiles import SurfaceProfile, build_surface_profile
from .surd_snapshot import SurfaceSnapshot, build_surd_snapshot

L40_TO_SURFACE_SEC = 60
MAX_SURFACE_INTERVAL_SEC = 5 * 60
UNDRESS_SEC = 60
SURFACE_TO_CHAMBER_50_SEC = MAX_SURFACE_INTERVAL_SEC - L40_TO_SURFACE_SEC - UNDRESS_SEC
CHAMBER_AIR_BREAK_SEC = 5 * 60
SURFACE_INTERVAL_PENALTY_MAX_SEC = 7 * 60
CLEAN_TIME_SEC = 10 * 60


class SurfacePhase(Enum):
    READY = auto()
    SURFACE_INTERVAL = auto()
    CHAMBER_DESCENT = auto()
    CHAMBER_OXYGEN = auto()
    CHAMBER_AIR_BREAK = auto()
    COMPLETE = auto()


class SurfaceIntervalSubphase(Enum):
    ASCENT_TO_SURFACE = auto()
    UNDRESS = auto()
    SURFACE_TO_CHAMBER_50 = auto()


@dataclass(frozen=True)
class SURDChamberPlanSegment:
    segment_index: int
    period_number: int
    depth_fsw: int
    duration_sec: int


@dataclass(frozen=True)
class SURDChamberPlan:
    total_half_periods: int
    segments: tuple[SURDChamberPlanSegment, ...]


class SurfaceIntent(Enum):
    PRIMARY = auto()
    SECONDARY = auto()
    MODE = auto()
    RESET = auto()
    HANDOFF = auto()


class SurfaceEntryKind(Enum):
    L40 = auto()
    DIRECT_ASCENT_NO_40 = auto()
    FROM_30_OR_20 = auto()


@dataclass(frozen=True)
class SurfaceEvent:
    code: str
    timestamp: datetime


@dataclass(frozen=True)
class SurfaceHandoff:
    entry_kind: SurfaceEntryKind
    source_mode: str
    source_profile_schedule_text: str
    surface_profile: SurfaceProfile
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int | None
    table_bottom_time_min: int | None
    current_stop_depth_fsw: int | None
    remaining_stop_sec: float | None
    event_log: tuple[str, ...]
    handed_off_at: datetime


@dataclass(frozen=True)
class SurfaceState:
    phase: SurfacePhase = SurfacePhase.READY
    handoff: SurfaceHandoff | None = None
    events: tuple[SurfaceEvent, ...] = ()
    ui_log: tuple[str, ...] = ()
    phase_started_at: datetime | None = None
    interval_subphase: SurfaceIntervalSubphase | None = None
    interval_subphase_started_at: datetime | None = None
    current_chamber_depth_fsw: int | None = None
    chamber_o2_half_periods: int | None = None
    surd_chamber_plan: SURDChamberPlan | None = None
    current_o2_segment_index: int | None = None
    current_o2_segment_started_at: datetime | None = None
    current_o2_segment_elapsed_before_pause_sec: float = 0.0
    off_o2_started_at: datetime | None = None
    current_air_break_number: int | None = None
    current_air_break_started_at: datetime | None = None
    surface_interval_penalty_half_periods: int = 0
    test_time_offset_sec: float = 0.0


def build_l40_surface_handoff(
    *,
    source_mode: str,
    input_depth_fsw: int,
    input_bottom_time_min: int,
    source_profile_schedule_text: str,
    event_log: tuple[str, ...],
    handed_off_at: datetime,
) -> SurfaceHandoff:
    surface_profile = build_surface_profile(input_depth_fsw, input_bottom_time_min)
    return SurfaceHandoff(
        entry_kind=SurfaceEntryKind.L40,
        source_mode=source_mode,
        source_profile_schedule_text=source_profile_schedule_text,
        surface_profile=surface_profile,
        input_depth_fsw=input_depth_fsw,
        input_bottom_time_min=input_bottom_time_min,
        table_depth_fsw=surface_profile.table_depth_fsw,
        table_bottom_time_min=surface_profile.table_bottom_time_min,
        current_stop_depth_fsw=40,
        remaining_stop_sec=0.0,
        event_log=event_log,
        handed_off_at=handed_off_at,
    )


class SurfaceEngine:
    """Draft SurD runtime scaffold.

    This intentionally provides only a stable module boundary and minimal state
    definitions. The real workflow should be added from the manual outward once
    the first handoff contract is finalized.
    """

    def __init__(self, now_provider=None) -> None:
        self.state = SurfaceState()
        self._now_provider = now_provider or datetime.now

    def _now(self) -> datetime:
        return self._now_provider() + timedelta(seconds=self.state.test_time_offset_sec)

    def start_handoff(self, handoff: SurfaceHandoff) -> None:
        self.state = SurfaceState(
            phase=SurfacePhase.SURFACE_INTERVAL,
            handoff=handoff,
            events=(SurfaceEvent(code="L40", timestamp=handoff.handed_off_at),),
            ui_log=(
                f"SurD start from 40 fsw {handoff.handed_off_at.strftime('%H:%M:%S')}",
                f"Traveling 40 -> Surface {handoff.handed_off_at.strftime('%H:%M:%S')}",
            ),
            phase_started_at=handoff.handed_off_at,
            interval_subphase=SurfaceIntervalSubphase.ASCENT_TO_SURFACE,
            interval_subphase_started_at=handoff.handed_off_at,
            current_chamber_depth_fsw=None,
            chamber_o2_half_periods=handoff.surface_profile.chamber_o2_half_periods,
            surd_chamber_plan=build_surd_chamber_plan(handoff.surface_profile.chamber_o2_half_periods),
            current_o2_segment_index=None,
            current_o2_segment_started_at=None,
            current_o2_segment_elapsed_before_pause_sec=0.0,
            off_o2_started_at=None,
            current_air_break_number=None,
            current_air_break_started_at=None,
            surface_interval_penalty_half_periods=0,
            test_time_offset_sec=self.state.test_time_offset_sec,
        )

    def dispatch(self, intent: SurfaceIntent) -> None:
        now = self._now()
        if intent is SurfaceIntent.RESET:
            self.state = SurfaceState()
            return
        if self.state.handoff is None:
            return
        if intent is SurfaceIntent.SECONDARY:
            if self.state.phase is SurfacePhase.CHAMBER_OXYGEN:
                self._toggle_chamber_o2(now)
            return
        if intent is not SurfaceIntent.PRIMARY:
            return
        if self.state.phase is SurfacePhase.SURFACE_INTERVAL:
            self._advance_surface_interval(now)
            return
        if self.state.phase is SurfacePhase.CHAMBER_OXYGEN:
            self._advance_chamber_o2_segment(now)
            return
        if self.state.phase is SurfacePhase.CHAMBER_AIR_BREAK:
            self._advance_air_break(now)
            return
        if self.state.phase is SurfacePhase.COMPLETE:
            return

    def snapshot(self) -> SurfaceSnapshot:
        now = self._now()
        elapsed_sec = _elapsed_since(self.state.phase_started_at, now)
        return build_surd_snapshot(
            state=self.state,
            elapsed_sec=elapsed_sec,
            format_tenths=format_tenths,
            format_mmss=format_mmss,
            l40_to_surface_sec=L40_TO_SURFACE_SEC,
            max_surface_interval_sec=MAX_SURFACE_INTERVAL_SEC,
            undress_sec=UNDRESS_SEC,
            chamber_air_break_sec=CHAMBER_AIR_BREAK_SEC,
            surface_interval_penalty_max_sec=SURFACE_INTERVAL_PENALTY_MAX_SEC,
            clean_time_sec=CLEAN_TIME_SEC,
            current_surd_o2_segment=_current_surd_o2_segment,
            next_surd_o2_segment=_next_surd_o2_segment,
            current_o2_summary=_current_o2_summary,
            current_o2_elapsed_sec=lambda state, _elapsed_sec: _current_o2_elapsed_sec(state, now),
            off_o2_elapsed_sec=lambda state, _elapsed_sec: _off_o2_elapsed_sec(state, now),
        )

    def recall_lines(self) -> tuple[str, ...]:
        return self.state.ui_log[-30:]

    def advance_test_time(self, delta_seconds: float) -> None:
        self.state = SurfaceState(
            phase=self.state.phase,
            handoff=self.state.handoff,
            events=self.state.events,
            ui_log=self.state.ui_log,
            phase_started_at=self.state.phase_started_at,
            interval_subphase=self.state.interval_subphase,
            interval_subphase_started_at=self.state.interval_subphase_started_at,
            current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
            chamber_o2_half_periods=self.state.chamber_o2_half_periods,
            surd_chamber_plan=self.state.surd_chamber_plan,
            current_o2_segment_index=self.state.current_o2_segment_index,
            current_o2_segment_started_at=self.state.current_o2_segment_started_at,
            current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
            off_o2_started_at=self.state.off_o2_started_at,
            current_air_break_number=self.state.current_air_break_number,
            current_air_break_started_at=self.state.current_air_break_started_at,
            surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
            test_time_offset_sec=max(self.state.test_time_offset_sec + delta_seconds, 0.0),
        )

    def reset_test_time(self) -> None:
        self.state = SurfaceState(
            phase=self.state.phase,
            handoff=self.state.handoff,
            events=self.state.events,
            ui_log=self.state.ui_log,
            phase_started_at=self.state.phase_started_at,
            interval_subphase=self.state.interval_subphase,
            interval_subphase_started_at=self.state.interval_subphase_started_at,
            current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
            chamber_o2_half_periods=self.state.chamber_o2_half_periods,
            surd_chamber_plan=self.state.surd_chamber_plan,
            current_o2_segment_index=self.state.current_o2_segment_index,
            current_o2_segment_started_at=self.state.current_o2_segment_started_at,
            current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
            off_o2_started_at=self.state.off_o2_started_at,
            current_air_break_number=self.state.current_air_break_number,
            current_air_break_started_at=self.state.current_air_break_started_at,
            surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
            test_time_offset_sec=0.0,
        )

    def _advance_surface_interval(self, now: datetime) -> None:
        if self.state.phase is not SurfacePhase.SURFACE_INTERVAL or self.state.interval_subphase is None:
            return
        if self.state.interval_subphase is SurfaceIntervalSubphase.ASCENT_TO_SURFACE:
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="RS", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"RS {now.strftime('%H:%M:%S')}",
                    f"Undress {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=SurfaceIntervalSubphase.UNDRESS,
                interval_subphase_started_at=now,
                current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
                off_o2_started_at=self.state.off_o2_started_at,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        if self.state.interval_subphase is SurfaceIntervalSubphase.UNDRESS:
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="LS", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"LS {now.strftime('%H:%M:%S')}",
                    f"Traveling Surface -> Chamber 50 {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=SurfaceIntervalSubphase.SURFACE_TO_CHAMBER_50,
                interval_subphase_started_at=now,
                current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
                off_o2_started_at=self.state.off_o2_started_at,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        total_surface_interval_sec = _elapsed_since(self.state.phase_started_at, now)
        penalty_half_periods = 1 if MAX_SURFACE_INTERVAL_SEC < total_surface_interval_sec <= SURFACE_INTERVAL_PENALTY_MAX_SEC else 0
        late_log = ()
        if penalty_half_periods:
            late_log = (f"Surface interval penalty (+15 O2 @ 50) {now.strftime('%H:%M:%S')}",)
        elif total_surface_interval_sec > MAX_SURFACE_INTERVAL_SEC:
            late_log = (f"Surface interval exceeded 05:00 {now.strftime('%H:%M:%S')}",)
        self.state = SurfaceState(
            phase=SurfacePhase.CHAMBER_OXYGEN,
            handoff=self.state.handoff,
            events=self.state.events + (SurfaceEvent(code="RB", timestamp=now),),
            ui_log=self.state.ui_log + (
                *late_log,
                f"RB {now.strftime('%H:%M:%S')}",
                f"Chamber 50 {now.strftime('%H:%M:%S')}",
            ),
            phase_started_at=now,
            interval_subphase=None,
            interval_subphase_started_at=None,
            current_chamber_depth_fsw=50,
            chamber_o2_half_periods=self.state.chamber_o2_half_periods,
            surd_chamber_plan=build_surd_chamber_plan(
                self.state.chamber_o2_half_periods,
                surface_interval_penalty_half_periods=penalty_half_periods,
            ),
            current_o2_segment_index=0,
            current_o2_segment_started_at=None,
            current_o2_segment_elapsed_before_pause_sec=0.0,
            off_o2_started_at=None,
            current_air_break_number=None,
            current_air_break_started_at=None,
            surface_interval_penalty_half_periods=penalty_half_periods,
            test_time_offset_sec=self.state.test_time_offset_sec,
        )

    def _advance_chamber_o2_segment(self, now: datetime) -> None:
        current_segment = _current_surd_o2_segment(self.state)
        next_segment = _next_surd_o2_segment(self.state)
        if self.state.phase is not SurfacePhase.CHAMBER_OXYGEN or current_segment is None or self.state.current_o2_segment_started_at is None:
            return
        if self.state.off_o2_started_at is not None:
            return
        segment_elapsed_sec = _current_o2_elapsed_sec(self.state, now)
        segment_duration_sec = current_segment.duration_sec
        if segment_elapsed_sec < segment_duration_sec:
            return
        if (
            next_segment is not None
            and next_segment.depth_fsw != current_segment.depth_fsw
            and next_segment.period_number == current_segment.period_number
        ):
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code=f"C{next_segment.depth_fsw}", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"Chamber {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}",
                    f"{next_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=self.state.interval_subphase,
                current_chamber_depth_fsw=next_segment.depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=next_segment.segment_index,
                current_o2_segment_started_at=now,
                current_o2_segment_elapsed_before_pause_sec=0.0,
                off_o2_started_at=None,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        if next_segment is not None and next_segment.period_number > current_segment.period_number:
            self.state = SurfaceState(
                phase=SurfacePhase.CHAMBER_AIR_BREAK,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="AIR_BREAK_START", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"Air break start {now.strftime('%H:%M:%S')}",
                    f"{self.state.current_chamber_depth_fsw or 40} fsw Air Break {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=self.state.interval_subphase,
                current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
                off_o2_started_at=None,
                current_air_break_number=1,
                current_air_break_started_at=now,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        if next_segment is None:
            self.state = SurfaceState(
                phase=SurfacePhase.COMPLETE,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="RS", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"RS {now.strftime('%H:%M:%S')}",
                    f"Surface {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=now,
                interval_subphase=self.state.interval_subphase,
                current_chamber_depth_fsw=0,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
                off_o2_started_at=None,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=None,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )

    def _advance_air_break(self, now: datetime) -> None:
        if self.state.current_air_break_started_at is None:
            return
        next_segment = _next_surd_o2_segment(self.state)
        air_break_elapsed_sec = _elapsed_since(self.state.current_air_break_started_at, now)
        if air_break_elapsed_sec < CHAMBER_AIR_BREAK_SEC:
            return
        if next_segment is None:
            return
        if next_segment.depth_fsw != self.state.current_chamber_depth_fsw:
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code=f"C{next_segment.depth_fsw}", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"Chamber {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}",
                    f"{next_segment.depth_fsw} fsw Air Break {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=self.state.interval_subphase,
                current_chamber_depth_fsw=next_segment.depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
                off_o2_started_at=self.state.off_o2_started_at,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        self.state = SurfaceState(
            phase=SurfacePhase.CHAMBER_OXYGEN,
            handoff=self.state.handoff,
            events=self.state.events + (SurfaceEvent(code="ON_O2", timestamp=now),),
            ui_log=self.state.ui_log + (
                f"On O2 {next_segment.depth_fsw} {now.strftime('%H:%M:%S')}",
                f"{next_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}",
            ),
            phase_started_at=self.state.phase_started_at,
            interval_subphase=self.state.interval_subphase,
            current_chamber_depth_fsw=next_segment.depth_fsw,
            chamber_o2_half_periods=self.state.chamber_o2_half_periods,
            surd_chamber_plan=self.state.surd_chamber_plan,
            current_o2_segment_index=next_segment.segment_index,
            current_o2_segment_started_at=now,
            current_o2_segment_elapsed_before_pause_sec=0.0,
            off_o2_started_at=None,
            current_air_break_number=self.state.current_air_break_number,
            current_air_break_started_at=None,
            surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
            test_time_offset_sec=self.state.test_time_offset_sec,
        )

    def _toggle_chamber_o2(self, now: datetime) -> None:
        current_segment = _current_surd_o2_segment(self.state)
        if self.state.phase is not SurfacePhase.CHAMBER_OXYGEN or current_segment is None:
            return
        if self.state.current_o2_segment_started_at is None:
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="ON_O2", timestamp=now),),
                ui_log=self.state.ui_log + (
                    f"On O2 {current_segment.depth_fsw} {now.strftime('%H:%M:%S')}",
                    f"{current_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}",
                ),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=self.state.interval_subphase,
                interval_subphase_started_at=self.state.interval_subphase_started_at,
                current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=now,
                current_o2_segment_elapsed_before_pause_sec=0.0,
                off_o2_started_at=None,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        if self.state.off_o2_started_at is None:
            self.state = SurfaceState(
                phase=self.state.phase,
                handoff=self.state.handoff,
                events=self.state.events + (SurfaceEvent(code="OFF_O2", timestamp=now),),
                ui_log=self.state.ui_log + (f"Off O2 {now.strftime('%H:%M:%S')}",),
                phase_started_at=self.state.phase_started_at,
                interval_subphase=self.state.interval_subphase,
                current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
                chamber_o2_half_periods=self.state.chamber_o2_half_periods,
                surd_chamber_plan=self.state.surd_chamber_plan,
                current_o2_segment_index=self.state.current_o2_segment_index,
                current_o2_segment_started_at=self.state.current_o2_segment_started_at,
                current_o2_segment_elapsed_before_pause_sec=_current_o2_elapsed_sec(self.state, now),
                off_o2_started_at=now,
                current_air_break_number=self.state.current_air_break_number,
                current_air_break_started_at=self.state.current_air_break_started_at,
                surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
                test_time_offset_sec=self.state.test_time_offset_sec,
            )
            return
        self.state = SurfaceState(
            phase=self.state.phase,
            handoff=self.state.handoff,
            events=self.state.events + (SurfaceEvent(code="ON_O2", timestamp=now),),
            ui_log=self.state.ui_log + (
                f"On O2 {current_segment.depth_fsw} {now.strftime('%H:%M:%S')}",
                f"{current_segment.depth_fsw} fsw O2 {now.strftime('%H:%M:%S')}",
            ),
            phase_started_at=self.state.phase_started_at,
            interval_subphase=self.state.interval_subphase,
            current_chamber_depth_fsw=self.state.current_chamber_depth_fsw,
            chamber_o2_half_periods=self.state.chamber_o2_half_periods,
            surd_chamber_plan=self.state.surd_chamber_plan,
            current_o2_segment_index=self.state.current_o2_segment_index,
            current_o2_segment_started_at=now,
            current_o2_segment_elapsed_before_pause_sec=self.state.current_o2_segment_elapsed_before_pause_sec,
            off_o2_started_at=None,
            current_air_break_number=self.state.current_air_break_number,
            current_air_break_started_at=self.state.current_air_break_started_at,
            surface_interval_penalty_half_periods=self.state.surface_interval_penalty_half_periods,
            test_time_offset_sec=self.state.test_time_offset_sec,
        )


def format_tenths(seconds: float) -> str:
    clamped = max(seconds, 0.0)
    total_tenths = math.floor((clamped * 10) + 1e-9)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"


def format_mmss(seconds: float) -> str:
    whole_seconds = max(int(math.ceil(seconds)), 0)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def _elapsed_since(started_at: datetime | None, now: datetime) -> float:
    if started_at is None:
        return 0.0
    return max((now - started_at).total_seconds(), 0.0)


def _current_o2_elapsed_sec(state: SurfaceState, now: datetime) -> float:
    if state.phase is not SurfacePhase.CHAMBER_OXYGEN:
        return 0.0
    active_elapsed = 0.0 if state.current_o2_segment_started_at is None else _elapsed_since(state.current_o2_segment_started_at, now)
    if state.off_o2_started_at is not None:
        active_elapsed = 0.0
    return max(state.current_o2_segment_elapsed_before_pause_sec + active_elapsed, 0.0)


def _off_o2_elapsed_sec(state: SurfaceState, now: datetime) -> float:
    if state.off_o2_started_at is None:
        return 0.0
    return _elapsed_since(state.off_o2_started_at, now)


def _surface_period_detail(chamber_o2_half_periods: int | None) -> str:
    if chamber_o2_half_periods is None:
        return ""
    periods = chamber_o2_half_periods / 2
    return f"Chamber O2: {periods:g} periods total"


def _current_o2_summary(
    segment: SURDChamberPlanSegment | None,
) -> str:
    if segment is None:
        return "Chamber O2"
    if segment.period_number == 1 and segment.depth_fsw == 50:
        return "First O2 period: 50 fsw segment"
    if segment.period_number == 1 and segment.depth_fsw == 40:
        return "First O2 period: 40 fsw segment"
    return f"O2 period {segment.period_number}"


def build_surd_chamber_plan(
    chamber_o2_half_periods: int | None,
    *,
    surface_interval_penalty_half_periods: int = 0,
) -> SURDChamberPlan | None:
    total_half_periods = None if chamber_o2_half_periods is None else chamber_o2_half_periods + max(surface_interval_penalty_half_periods, 0)
    if total_half_periods is None or total_half_periods <= 0:
        return None
    remaining_half_periods = total_half_periods
    segments: list[SURDChamberPlanSegment] = []
    segment_index = 0

    first_50_half_periods = min(remaining_half_periods, 1 + max(surface_interval_penalty_half_periods, 0))
    if first_50_half_periods:
        segments.append(
            SURDChamberPlanSegment(
                segment_index=segment_index,
                period_number=1,
                depth_fsw=50,
                duration_sec=first_50_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= first_50_half_periods

    first_40_half_periods = min(remaining_half_periods, 1)
    if first_40_half_periods:
        segments.append(
            SURDChamberPlanSegment(
                segment_index=segment_index,
                period_number=1,
                depth_fsw=40,
                duration_sec=first_40_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= first_40_half_periods

    period_number = 2
    while remaining_half_periods > 0:
        period_half_periods = min(remaining_half_periods, 2)
        depth_fsw = 40 if period_number <= 4 else 30
        segments.append(
            SURDChamberPlanSegment(
                segment_index=segment_index,
                period_number=period_number,
                depth_fsw=depth_fsw,
                duration_sec=period_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= period_half_periods
        period_number += 1

    return SURDChamberPlan(
        total_half_periods=total_half_periods,
        segments=tuple(segments),
    )


def _current_surd_o2_segment(state: SurfaceState) -> SURDChamberPlanSegment | None:
    if state.surd_chamber_plan is None or state.current_o2_segment_index is None:
        return None
    if state.current_o2_segment_index < 0 or state.current_o2_segment_index >= len(state.surd_chamber_plan.segments):
        return None
    return state.surd_chamber_plan.segments[state.current_o2_segment_index]


def _next_surd_o2_segment(state: SurfaceState) -> SURDChamberPlanSegment | None:
    current_segment = _current_surd_o2_segment(state)
    if state.surd_chamber_plan is None or current_segment is None:
        return None
    next_index = current_segment.segment_index + 1
    if next_index >= len(state.surd_chamber_plan.segments):
        return None
    return state.surd_chamber_plan.segments[next_index]
