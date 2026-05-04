from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum, auto
import math

from ..air_o2_profiles import DelayOutcome, DelayResult, apply_delay, convert_remaining_o2_to_air, DecoMode, DiveProfile, next_stop_after, stop_by_index, build_profile, no_decompression_limit
from ..air_o2_snapshot import Snapshot
from .protocol import OperatorAction
from .snapshot_projection import SnapshotProjection


class RedesignDivePhase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    AT_AIR_STOP = auto()
    AT_O2_STOP_WAITING = auto()
    AT_O2_STOP_ON_O2 = auto()
    AT_O2_STOP_OFF_O2 = auto()
    AT_O2_STOP_AIR_BREAK = auto()
    SURFACE_CLEAN_TIME = auto()
    SURFACE_COMPLETE = auto()


class AnchorKind(Enum):
    BOTTOM_TIME = auto()
    TRAVEL = auto()
    AIR_STOP = auto()
    TSV_WAIT = auto()
    O2_SEGMENT = auto()
    OFF_O2 = auto()
    AIR_BREAK = auto()
    DELAY = auto()
    CLEAN_TIME = auto()


@dataclass(frozen=True)
class TimerAnchor:
    kind: AnchorKind
    started_at: datetime
    carried_elapsed_sec: float = 0.0


@dataclass(frozen=True)
class DepthInputState:
    raw_text: str = ""
    parsed_depth_fsw: int | None = None


@dataclass(frozen=True)
class PlanState:
    profile: DiveProfile
    current_stop_index: int | None = None


@dataclass(frozen=True)
class AuditEntry:
    code: str
    at: datetime
    message: str


@dataclass(frozen=True)
class DelayState:
    delay_index: int
    anchor: TimerAnchor
    delay_depth_fsw: int


@dataclass(frozen=True)
class RedesignDiveState:
    mode: DecoMode
    depth_input: DepthInputState = field(default_factory=DepthInputState)
    phase: RedesignDivePhase = RedesignDivePhase.READY
    plan: PlanState | None = None
    bottom_anchor: TimerAnchor | None = None
    travel_anchor: TimerAnchor | None = None
    stop_anchor: TimerAnchor | None = None
    tsv_anchor: TimerAnchor | None = None
    o2_anchor: TimerAnchor | None = None
    off_o2_anchor: TimerAnchor | None = None
    air_break_anchor: TimerAnchor | None = None
    delay_state: DelayState | None = None
    last_delay_result: DelayResult | None = None
    travel_display_delay_sec: float = 0.0
    clean_time_anchor: TimerAnchor | None = None
    audit: tuple[AuditEntry, ...] = ()
    test_time_offset_sec: float = 0.0


def _format_tenths(seconds: float) -> str:
    total_tenths = max(int(round(seconds * 10)), 0)
    minutes, tenths = divmod(total_tenths, 600)
    seconds_whole, tenths = divmod(tenths, 10)
    return f"{minutes:02d}:{seconds_whole:02d}.{tenths}"


def _format_mmss(seconds: float) -> str:
    total = max(int(round(seconds)), 0)
    minutes, seconds = divmod(total, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _parse_depth(raw: str) -> int | None:
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        depth = int(stripped)
    except ValueError:
        return None
    return depth if depth > 0 else None


class RedesignDiveEngine:
    """Explicit-state parallel AIR/AIR-O2 runtime.

    This is the current redesign slice. It supports:

    - READY / DESCENT / BOTTOM
    - no-decompression ascent to clean time
    - simple AIR stop progression
    - first O2 waiting states
    - explicit On O2 confirmation
    - continuous O2 carry between O2 stops
    """

    def __init__(self, *, mode: DecoMode = DecoMode.AIR, now_provider=None) -> None:
        if mode not in {DecoMode.AIR, DecoMode.AIR_O2}:
            raise ValueError(f"Unsupported redesign mode: {mode}")
        self._now_provider = now_provider or datetime.now
        self.state = RedesignDiveState(mode=mode)

    def _now(self) -> datetime:
        return self._now_provider() + timedelta(seconds=self.state.test_time_offset_sec)

    def set_depth_text(self, raw: str) -> None:
        if raw == self.state.depth_input.raw_text:
            return
        self.state = replace(
            self.state,
            depth_input=DepthInputState(raw_text=raw, parsed_depth_fsw=_parse_depth(raw)),
        )

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
            self.state = RedesignDiveState(mode=self.state.mode, depth_input=self.state.depth_input, test_time_offset_sec=self.state.test_time_offset_sec)
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
            self._reach_stop(now)
            return
        if action is OperatorAction.LEAVE_STOP:
            self._leave_stop(now)
            return
        if action is OperatorAction.CONFIRM_ON_O2:
            self._confirm_on_o2(now)
            return
        if action is OperatorAction.TOGGLE_OFF_O2:
            self._toggle_off_o2(now)
            return
        if action is OperatorAction.TOGGLE_DELAY:
            self._toggle_delay(now)
            return
        if action is OperatorAction.CONVERT_TO_AIR:
            self.convert_to_air(now)
            return

    def snapshot(self) -> Snapshot:
        now = self._now()
        if self.state.phase is RedesignDivePhase.SURFACE_CLEAN_TIME and self.state.clean_time_anchor is not None:
            elapsed = (now - self.state.clean_time_anchor.started_at).total_seconds()
            if elapsed >= 10 * 60:
                self.state = replace(self.state, phase=RedesignDivePhase.SURFACE_COMPLETE)
        return self._project_snapshot(now)

    def _leave_surface(self, now: datetime) -> None:
        if self.state.phase is not RedesignDivePhase.READY:
            return
        self.state = replace(
            self.state,
            phase=RedesignDivePhase.DESCENT,
            bottom_anchor=TimerAnchor(kind=AnchorKind.BOTTOM_TIME, started_at=now),
            audit=self.state.audit + (_entry("LS", now),),
        )

    def _reach_bottom(self, now: datetime) -> None:
        if self.state.phase is not RedesignDivePhase.DESCENT:
            return
        self.state = replace(
            self.state,
            phase=RedesignDivePhase.BOTTOM,
            audit=self.state.audit + (_entry("RB", now),),
        )

    def _leave_bottom(self, now: datetime) -> None:
        if self.state.phase is not RedesignDivePhase.BOTTOM or self.state.bottom_anchor is None:
            return
        depth = self.state.depth_input.parsed_depth_fsw
        if depth is None:
            return
        bottom_elapsed_sec = max((now - self.state.bottom_anchor.started_at).total_seconds(), 0.0)
        bottom_time_min = max(math.ceil(bottom_elapsed_sec / 60), 1)
        profile = build_profile(self.state.mode, depth, bottom_time_min)
        next_stop = next_stop_after(profile, None)
        phase = RedesignDivePhase.TRAVEL_TO_SURFACE if profile.is_no_decompression or next_stop is None else RedesignDivePhase.TRAVEL_TO_FIRST_STOP
        self.state = replace(
            self.state,
            phase=phase,
            plan=PlanState(profile=profile, current_stop_index=None),
            travel_anchor=TimerAnchor(kind=AnchorKind.TRAVEL, started_at=now),
            travel_display_delay_sec=0.0,
            stop_anchor=None,
            audit=self.state.audit + (_entry("LB", now),),
        )

    def _reach_stop(self, now: datetime) -> None:
        if self.state.phase is RedesignDivePhase.TRAVEL_TO_SURFACE:
            self.state = replace(
                self.state,
                phase=RedesignDivePhase.SURFACE_CLEAN_TIME,
                clean_time_anchor=TimerAnchor(kind=AnchorKind.CLEAN_TIME, started_at=now),
                travel_anchor=None,
                travel_display_delay_sec=0.0,
                audit=self.state.audit + _arrival_audit_entries(self.state, now, code="RS"),
            )
            return
        if self.state.phase is not RedesignDivePhase.TRAVEL_TO_FIRST_STOP or self.state.plan is None:
            return
        next_stop = next_stop_after(self.state.plan.profile, self.state.plan.current_stop_index)
        if next_stop is None:
            return
        carried_elapsed_sec = max((now - self.state.travel_anchor.started_at).total_seconds(), 0.0) if self.state.travel_anchor is not None else 0.0
        if next_stop.gas == "o2":
            tsv_started_at = now
            if self.state.o2_anchor is not None:
                phase = RedesignDivePhase.AT_O2_STOP_ON_O2
                stop_anchor = TimerAnchor(
                    kind=AnchorKind.O2_SEGMENT,
                    started_at=now,
                    carried_elapsed_sec=carried_elapsed_sec,
                )
                tsv_anchor = None
            else:
                phase = RedesignDivePhase.AT_O2_STOP_WAITING
                if self.state.plan.current_stop_index is not None and self.state.travel_anchor is not None:
                    tsv_started_at = self.state.travel_anchor.started_at
                stop_anchor = TimerAnchor(
                    kind=AnchorKind.O2_SEGMENT,
                    started_at=now,
                    carried_elapsed_sec=0.0,
                )
                tsv_anchor = TimerAnchor(kind=AnchorKind.TSV_WAIT, started_at=tsv_started_at)
            self.state = replace(
                self.state,
                phase=phase,
                plan=replace(self.state.plan, current_stop_index=next_stop.index),
                stop_anchor=stop_anchor,
                travel_anchor=None,
                travel_display_delay_sec=0.0,
                tsv_anchor=tsv_anchor,
                audit=self.state.audit + _arrival_audit_entries(self.state, now, code=f"R{next_stop.index}"),
            )
            return
        self.state = replace(
            self.state,
            phase=RedesignDivePhase.AT_AIR_STOP,
            plan=replace(self.state.plan, current_stop_index=next_stop.index),
            stop_anchor=TimerAnchor(
                kind=AnchorKind.AIR_STOP,
                started_at=now,
                carried_elapsed_sec=0.0 if next_stop.index == 1 else carried_elapsed_sec,
            ),
            travel_anchor=None,
            travel_display_delay_sec=0.0,
            audit=self.state.audit + _arrival_audit_entries(self.state, now, code=f"R{next_stop.index}"),
        )

    def _leave_stop(self, now: datetime) -> None:
        if self.state.phase not in {
            RedesignDivePhase.AT_AIR_STOP,
            RedesignDivePhase.AT_O2_STOP_WAITING,
            RedesignDivePhase.AT_O2_STOP_ON_O2,
        } or self.state.plan is None:
            return
        current_index = self.state.plan.current_stop_index
        current_stop = stop_by_index(self.state.plan.profile, current_index)
        if current_stop is None:
            return
        next_stop = next_stop_after(self.state.plan.profile, current_index)
        phase = RedesignDivePhase.TRAVEL_TO_SURFACE if next_stop is None else RedesignDivePhase.TRAVEL_TO_FIRST_STOP
        self.state = replace(
            self.state,
            phase=phase,
            travel_anchor=TimerAnchor(kind=AnchorKind.TRAVEL, started_at=now),
            travel_display_delay_sec=0.0,
            stop_anchor=None,
            tsv_anchor=None,
            audit=self.state.audit + _leave_stop_audit_entries(self.state, now, current_stop),
        )

    def _confirm_on_o2(self, now: datetime) -> None:
        if self.state.phase is not RedesignDivePhase.AT_O2_STOP_WAITING:
            return
        self.state = replace(
            self.state,
            phase=RedesignDivePhase.AT_O2_STOP_ON_O2,
            stop_anchor=TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=0.0),
            o2_anchor=TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=0.0),
            tsv_anchor=None,
            audit=self.state.audit + (_entry("On O2", now),),
        )

    def _toggle_off_o2(self, now: datetime) -> None:
        if self.state.phase is RedesignDivePhase.AT_O2_STOP_ON_O2:
            if _air_break_due_sec(self.state, now) == 0:
                paused_stop_anchor = self.state.stop_anchor
                if paused_stop_anchor is not None:
                    paused_stop_anchor = replace(
                        paused_stop_anchor,
                        carried_elapsed_sec=paused_stop_anchor.carried_elapsed_sec + (now - paused_stop_anchor.started_at).total_seconds(),
                        started_at=now,
                    )
                self.state = replace(
                    self.state,
                    phase=RedesignDivePhase.AT_O2_STOP_AIR_BREAK,
                    stop_anchor=paused_stop_anchor,
                    o2_anchor=None,
                    air_break_anchor=TimerAnchor(kind=AnchorKind.AIR_BREAK, started_at=now),
                    audit=self.state.audit
                    + (
                        _audit_message("AIR_BREAK_START", now, f"Air break start {now.strftime('%H:%M:%S')}"),
                        _entry("Off O2", now),
                    ),
                )
                return
            paused_stop_anchor = self.state.stop_anchor
            if paused_stop_anchor is not None:
                paused_stop_anchor = replace(
                    paused_stop_anchor,
                    carried_elapsed_sec=paused_stop_anchor.carried_elapsed_sec + (now - paused_stop_anchor.started_at).total_seconds(),
                    started_at=now,
                )
            self.state = replace(
                self.state,
                phase=RedesignDivePhase.AT_O2_STOP_OFF_O2,
                stop_anchor=paused_stop_anchor,
                off_o2_anchor=TimerAnchor(kind=AnchorKind.OFF_O2, started_at=now),
                audit=self.state.audit + (_entry("Off O2", now),),
            )
            return
        if self.state.phase is RedesignDivePhase.AT_O2_STOP_AIR_BREAK:
            if self.state.air_break_anchor is None:
                return
            break_elapsed_sec = max((now - self.state.air_break_anchor.started_at).total_seconds(), 0.0)
            if break_elapsed_sec < 5 * 60:
                remaining = (5 * 60) - break_elapsed_sec
                self.state = replace(
                    self.state,
                    audit=self.state.audit + (
                        _audit_message("AIR_BREAK_BLOCKED", now, f"Complete break first ({_format_mmss(remaining)})"),
                    ),
                )
                return
            carried_elapsed_sec = self.state.stop_anchor.carried_elapsed_sec if self.state.stop_anchor is not None else 0.0
            self.state = replace(
                self.state,
                phase=RedesignDivePhase.AT_O2_STOP_ON_O2,
                stop_anchor=TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=carried_elapsed_sec),
                air_break_anchor=None,
                o2_anchor=TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=0.0),
                audit=self.state.audit + (_audit_message("AIR_BREAK_END", now, f"Back on O2 {now.strftime('%H:%M:%S')}"),),
            )
            return
        if self.state.phase is RedesignDivePhase.AT_O2_STOP_OFF_O2:
            carried_elapsed_sec = self.state.stop_anchor.carried_elapsed_sec if self.state.stop_anchor is not None else 0.0
            self.state = replace(
                self.state,
                phase=RedesignDivePhase.AT_O2_STOP_ON_O2,
                stop_anchor=TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=carried_elapsed_sec),
                off_o2_anchor=None,
                audit=self.state.audit + (_entry("On O2", now),),
            )
            return

    def convert_to_air(self, now: datetime | None = None) -> None:
        now = self._now() if now is None else now
        if self.state.phase not in {RedesignDivePhase.AT_O2_STOP_OFF_O2, RedesignDivePhase.AT_O2_STOP_AIR_BREAK} or self.state.plan is None:
            return
        current_stop = stop_by_index(self.state.plan.profile, self.state.plan.current_stop_index)
        if current_stop is None:
            return
        remaining_sec = _current_stop_remaining_sec(self.state, now)
        if remaining_sec is None:
            return
        result = convert_remaining_o2_to_air(
            self.state.plan.profile,
            current_stop_index=current_stop.index,
            remaining_o2_stop_sec=int(round(remaining_sec)),
        )
        next_index = result.converted_stop_index
        self.state = replace(
            self.state,
            phase=RedesignDivePhase.AT_AIR_STOP,
            plan=PlanState(profile=result.profile, current_stop_index=next_index),
            stop_anchor=TimerAnchor(kind=AnchorKind.AIR_STOP, started_at=now, carried_elapsed_sec=0.0),
            tsv_anchor=None,
            o2_anchor=None,
            off_o2_anchor=None,
            air_break_anchor=None,
            last_delay_result=None,
            audit=self.state.audit + (
                _audit_message("CONVERT_TO_AIR", now, f"Convert to Air {now.strftime('%H:%M:%S')}"),
                _audit_message(
                    "CONVERTED_TO_AIR",
                    now,
                    f"Converted remaining O2 at {current_stop.depth_fsw} fsw to {result.converted_air_min} min air {_profile_inline(self.state.plan.profile)} -> {_profile_inline(result.profile)}",
                ),
            ),
        )

    def _toggle_delay(self, now: datetime) -> None:
        if self.state.phase not in {RedesignDivePhase.TRAVEL_TO_FIRST_STOP, RedesignDivePhase.TRAVEL_TO_SURFACE}:
            return
        if self.state.plan is None:
            return
        if self.state.delay_state is None:
            delay_index = 1 + sum(1 for entry in self.state.audit if entry.code.startswith("DELAY_") and entry.code.endswith("_START"))
            self.state = replace(
                self.state,
                delay_state=DelayState(
                    delay_index=delay_index,
                    anchor=TimerAnchor(kind=AnchorKind.DELAY, started_at=now),
                    delay_depth_fsw=_estimated_travel_depth(self.state, now),
                ),
                audit=self.state.audit + (_audit_message(f"DELAY_{delay_index}_START", now, f"Delay {delay_index} start {now.strftime('%H:%M:%S')}"),),
            )
            return

        delay_state = self.state.delay_state
        delay_elapsed_sec = max(int(round((now - delay_state.anchor.started_at).total_seconds())), 0)
        o2_time_before_delay_sec = None
        if self.state.o2_anchor is not None:
            o2_time_before_delay_sec = max(int(round((delay_state.anchor.started_at - self.state.o2_anchor.started_at).total_seconds())), 0)
        result = apply_delay(
            self.state.plan.profile,
            from_stop_index=self.state.plan.current_stop_index,
            delay_elapsed_sec=delay_elapsed_sec,
            delay_depth_fsw=delay_state.delay_depth_fsw,
            o2_time_before_delay_sec=o2_time_before_delay_sec,
        )
        audit_entries = [
            _audit_message(f"DELAY_{delay_state.delay_index}_END", now, f"Delay {delay_state.delay_index} end {now.strftime('%H:%M:%S')}"),
        ]
        if result.outcome is DelayOutcome.O2_DELAY_CREDIT:
            if result.credited_o2_min > 0:
                base = f"O2 delay credited (+{result.credited_o2_min}m) {_profile_inline(self.state.plan.profile)} -> {_profile_inline(result.profile)}"
            else:
                base = f"O2 delay did not add O2 credit (+{result.delay_min}m delay)"
            if result.air_interruption_min > 0:
                base = f"{base}; {result.air_interruption_min}m on air ignored"
            audit_entries.append(_audit_message("O2_DELAY_CREDIT", now, base))
            if result.air_interruption_min > 0:
                audit_entries.append(
                    _audit_message(
                        "O2_DELAY_INTERRUPTION",
                        now,
                        f"O2 delay interruption ({result.air_interruption_min}m air) ignored for O2 credit",
                    )
                )
        elif result.outcome is DelayOutcome.O2_SURFACE_DELAY:
            base = f"20 fsw departure delay ignored (+{result.delay_min}m)"
            if result.air_interruption_min > 0:
                base = f"{base}; {result.air_interruption_min}m on air before surface"
            audit_entries.append(_audit_message("O2_SURFACE_DELAY", now, base))
            if result.air_interruption_min > 0:
                audit_entries.append(
                    _audit_message(
                        "O2_SURFACE_INTERRUPTION",
                        now,
                        f"20 fsw O2 departure delay interruption ({result.air_interruption_min}m air) ignored",
                    )
                )
        elif result.schedule_changed:
            audit_entries.append(
                _audit_message(
                    "SCHEDULE_UPDATED",
                    now,
                    f"Schedule updated (+{result.delay_min}m) {_profile_inline(self.state.plan.profile)} -> {_profile_inline(result.profile)}",
                )
            )
        elif result.outcome is DelayOutcome.ADD_TO_FIRST_STOP:
            audit_entries.append(
                _audit_message(
                    "DELAY_FIRST_STOP",
                    now,
                    f"Delay (+{result.delay_min}m) added to first stop",
                )
            )
        else:
            audit_entries.append(
                _audit_message(
                    "DELAY_IGNORED",
                    now,
                    f"Delay (+{result.delay_min}m), schedule unchanged",
                )
            )

        updated_travel_anchor = self.state.travel_anchor
        if updated_travel_anchor is not None:
            updated_travel_anchor = replace(
                updated_travel_anchor,
                started_at=updated_travel_anchor.started_at + timedelta(seconds=delay_elapsed_sec),
            )

        updated_o2_anchor = self.state.o2_anchor
        if result.outcome in {DelayOutcome.O2_DELAY_CREDIT, DelayOutcome.O2_SURFACE_DELAY} and result.air_interruption_min > 0:
            updated_o2_anchor = TimerAnchor(kind=AnchorKind.O2_SEGMENT, started_at=now, carried_elapsed_sec=0.0)

        self.state = replace(
            self.state,
            plan=replace(self.state.plan, profile=result.profile),
            delay_state=None,
            travel_anchor=updated_travel_anchor,
            travel_display_delay_sec=self.state.travel_display_delay_sec + delay_elapsed_sec,
            o2_anchor=updated_o2_anchor,
            last_delay_result=result,
            audit=self.state.audit + tuple(audit_entries),
        )

    def _project_snapshot(self, now: datetime) -> Snapshot:
        phase = self.state.phase
        projection = SnapshotProjection(
            mode_text=self.state.mode.value,
            profile_schedule_text=_profile_schedule_text(self.state, now),
            status_text={
                RedesignDivePhase.READY: "READY",
                RedesignDivePhase.DESCENT: "DESCENT",
                RedesignDivePhase.BOTTOM: "BOTTOM",
                RedesignDivePhase.TRAVEL_TO_FIRST_STOP: "TRAVELING",
                RedesignDivePhase.TRAVEL_TO_SURFACE: "TRAVELING",
                RedesignDivePhase.AT_AIR_STOP: "AT STOP",
                RedesignDivePhase.AT_O2_STOP_WAITING: "AT O2 STOP",
                RedesignDivePhase.AT_O2_STOP_ON_O2: "AT O2 STOP",
                RedesignDivePhase.AT_O2_STOP_OFF_O2: "AT O2 STOP",
                RedesignDivePhase.AT_O2_STOP_AIR_BREAK: "AT O2 STOP",
                RedesignDivePhase.SURFACE_CLEAN_TIME: "CLEAN TIME",
                RedesignDivePhase.SURFACE_COMPLETE: "SURFACE",
            }[phase],
            status_value_text=_status_value_text(self.state),
            primary_text=_primary_text(self.state, now),
            depth_text=_depth_text(self.state, now),
            depth_timer_text=_depth_timer_text(self.state, now),
            remaining_text=_remaining_text(self.state, now),
            summary_text=_summary_text(self.state, now),
        )
        primary_button_label, secondary_button_label = _button_labels(self.state)
        projection.primary_button_label = primary_button_label
        projection.secondary_button_label = secondary_button_label
        return projection.to_snapshot()


def _entry(code: str, now: datetime) -> AuditEntry:
    return AuditEntry(code=code, at=now, message=f"{code} {now.strftime('%H:%M:%S')}")


def _audit_message(code: str, now: datetime, message: str) -> AuditEntry:
    return AuditEntry(code=code, at=now, message=message)


def _profile_schedule_text(state: RedesignDiveState, now: datetime | None = None) -> str:
    profile = _display_profile(state, now)
    if profile is None:
        return ""
    if profile.repeat_group is not None and profile.table_bottom_time_min is not None:
        return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min} {profile.repeat_group}"
    if profile.table_bottom_time_min is not None:
        return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}"
    return f"Max {profile.table_depth_fsw} fsw"


def _profile_inline(profile: DiveProfile) -> str:
    stops = ",".join(f"{stop.depth_fsw}/{stop.duration_min}" for stop in profile.stops)
    return f"{profile.table_depth_fsw}/{profile.table_bottom_time_min} [{stops}]"


def _depth_text(state: RedesignDiveState, now: datetime) -> str:
    if state.phase is RedesignDivePhase.READY:
        if state.depth_input.parsed_depth_fsw is None:
            return "Max -- fsw"
        return f"{state.depth_input.parsed_depth_fsw} fsw"
    if state.phase is RedesignDivePhase.DESCENT:
        return f"{_estimated_descent_depth(state, now)} fsw"
    if state.phase is RedesignDivePhase.BOTTOM:
        if state.depth_input.parsed_depth_fsw is None:
            return "Max -- fsw"
        return f"{state.depth_input.parsed_depth_fsw} fsw"
    if state.phase in {RedesignDivePhase.AT_AIR_STOP, RedesignDivePhase.AT_O2_STOP_WAITING, RedesignDivePhase.AT_O2_STOP_ON_O2, RedesignDivePhase.AT_O2_STOP_OFF_O2, RedesignDivePhase.AT_O2_STOP_AIR_BREAK} and state.plan is not None:
        stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
        if stop is not None:
            return f"{stop.depth_fsw} fsw"
    if state.phase is RedesignDivePhase.SURFACE_CLEAN_TIME or state.phase is RedesignDivePhase.SURFACE_COMPLETE:
        return _profile_schedule_text(state) or "Surface"
    if state.phase in {RedesignDivePhase.TRAVEL_TO_FIRST_STOP, RedesignDivePhase.TRAVEL_TO_SURFACE}:
        return f"{_estimated_travel_depth(state, now)} fsw"
    return "--"


def _primary_text(state: RedesignDiveState, now: datetime) -> str:
    if state.phase is RedesignDivePhase.READY:
        return "00:00.0"
    if state.phase in {RedesignDivePhase.DESCENT, RedesignDivePhase.BOTTOM} and state.bottom_anchor is not None:
        return _format_tenths((now - state.bottom_anchor.started_at).total_seconds())
    if state.phase in {RedesignDivePhase.TRAVEL_TO_FIRST_STOP, RedesignDivePhase.TRAVEL_TO_SURFACE} and state.travel_anchor is not None:
        elapsed = (now - state.travel_anchor.started_at).total_seconds() + state.travel_display_delay_sec
        if state.delay_state is not None:
            elapsed += (now - state.delay_state.anchor.started_at).total_seconds()
        return _format_tenths(elapsed)
    if state.phase is RedesignDivePhase.AT_AIR_STOP and state.stop_anchor is not None:
            elapsed = state.stop_anchor.carried_elapsed_sec + (now - state.stop_anchor.started_at).total_seconds()
            return _format_tenths(elapsed)
    if state.phase is RedesignDivePhase.AT_O2_STOP_WAITING and state.tsv_anchor is not None:
        return f"TSV {_format_tenths((now - state.tsv_anchor.started_at).total_seconds())}"
    if state.phase is RedesignDivePhase.AT_O2_STOP_ON_O2 and state.stop_anchor is not None:
        elapsed = state.stop_anchor.carried_elapsed_sec + (now - state.stop_anchor.started_at).total_seconds()
        return _format_tenths(elapsed)
    if state.phase is RedesignDivePhase.AT_O2_STOP_OFF_O2 and state.off_o2_anchor is not None:
        return _format_tenths((now - state.off_o2_anchor.started_at).total_seconds())
    if state.phase is RedesignDivePhase.AT_O2_STOP_AIR_BREAK and state.air_break_anchor is not None:
        return _format_tenths((now - state.air_break_anchor.started_at).total_seconds())
    if state.phase is RedesignDivePhase.SURFACE_CLEAN_TIME and state.clean_time_anchor is not None:
        remaining = max(10 * 60 - (now - state.clean_time_anchor.started_at).total_seconds(), 0.0)
        return _format_mmss(remaining)
    return "SURFACE"


def _depth_timer_text(state: RedesignDiveState, now: datetime) -> str:
    if state.phase is RedesignDivePhase.BOTTOM:
        profile = _display_profile(state, now)
        if profile is None or state.bottom_anchor is None:
            return ""
        if profile.is_no_decompression and state.depth_input.parsed_depth_fsw is not None:
            limit_min = no_decompression_limit(state.mode, state.depth_input.parsed_depth_fsw)
            if limit_min is None:
                return ""
            remaining = max((limit_min * 60) - (now - state.bottom_anchor.started_at).total_seconds(), 0.0)
        else:
            remaining = max((profile.table_bottom_time_min * 60) - (now - state.bottom_anchor.started_at).total_seconds(), 0.0)
        return f"{_format_mmss(remaining)} remaining"
    if state.phase is RedesignDivePhase.AT_AIR_STOP and state.plan is not None and state.stop_anchor is not None:
        stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
        if stop is not None:
            elapsed = state.stop_anchor.carried_elapsed_sec + (now - state.stop_anchor.started_at).total_seconds()
            remaining = max((stop.duration_min * 60) - elapsed, 0.0)
            return f"{_format_mmss(remaining)} left"
    if state.phase in {RedesignDivePhase.AT_O2_STOP_WAITING, RedesignDivePhase.AT_O2_STOP_ON_O2, RedesignDivePhase.AT_O2_STOP_OFF_O2} and state.plan is not None and state.stop_anchor is not None:
        stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
        if stop is not None:
            elapsed = state.stop_anchor.carried_elapsed_sec
            if state.phase is RedesignDivePhase.AT_O2_STOP_ON_O2:
                elapsed += (now - state.stop_anchor.started_at).total_seconds()
            remaining = max((stop.duration_min * 60) - elapsed, 0.0)
            return f"{_format_mmss(remaining)} left"
    if state.phase is RedesignDivePhase.AT_O2_STOP_AIR_BREAK:
        remaining = _current_stop_remaining_sec(state, now)
        return "" if remaining is None else f"{_format_mmss(remaining)} left"
    return ""


def _remaining_text(state: RedesignDiveState, now: datetime) -> str:
    return ""


def _summary_text(state: RedesignDiveState, now: datetime) -> str:
    if state.phase is RedesignDivePhase.READY:
        return "Next: --"
    if state.phase is RedesignDivePhase.DESCENT:
        return "Next: --"
    if state.phase is RedesignDivePhase.BOTTOM:
        profile = _display_profile(state, now)
        if profile is None:
            return ""
        return "Next: Surface" if profile.is_no_decompression else f"Next: {_next_stop_summary(profile)}"
    if state.phase is RedesignDivePhase.TRAVEL_TO_SURFACE:
        return "Next: Surface"
    if state.phase is RedesignDivePhase.TRAVEL_TO_FIRST_STOP and state.plan is not None:
        stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
        if stop is not None:
            return f"Next: {stop.depth_fsw} fsw for {stop.duration_min} min"
    if state.phase is RedesignDivePhase.AT_AIR_STOP and state.plan is not None:
        stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
        if stop is None:
            return "Next: Surface"
        return f"Next: {stop.depth_fsw} fsw for {stop.duration_min} min"
    if state.phase in {RedesignDivePhase.AT_O2_STOP_WAITING, RedesignDivePhase.AT_O2_STOP_ON_O2, RedesignDivePhase.AT_O2_STOP_OFF_O2, RedesignDivePhase.AT_O2_STOP_AIR_BREAK} and state.plan is not None:
        if state.phase is RedesignDivePhase.AT_O2_STOP_AIR_BREAK:
            return "Next: On O2"
        if state.phase is RedesignDivePhase.AT_O2_STOP_OFF_O2:
            return "Next: On O2"
        stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
        if state.phase is RedesignDivePhase.AT_O2_STOP_ON_O2 and state.o2_anchor is not None:
            o2_elapsed_sec = _continuous_o2_elapsed_sec(state, now)
            break_remaining = max((30 * 60) - o2_elapsed_sec, 0.0)
            current_stop_remaining = _current_stop_remaining_sec(state, now)
            if current_stop_remaining is not None and break_remaining <= current_stop_remaining:
                remaining = max((30 * 60) - o2_elapsed_sec, 0.0)
                return f"Next: Air break in {_format_mmss(remaining)}"
        if stop is None:
            return "Next: Surface"
        return f"Next: {stop.depth_fsw} fsw for {stop.duration_min} min"
    return ""


def _button_labels(state: RedesignDiveState) -> tuple[str, str]:
    return {
        RedesignDivePhase.READY: ("Leave Surface", ""),
        RedesignDivePhase.DESCENT: ("Reach Bottom", "Hold"),
        RedesignDivePhase.BOTTOM: ("Leave Bottom", ""),
        RedesignDivePhase.TRAVEL_TO_FIRST_STOP: ("Reach Stop", "Delay"),
        RedesignDivePhase.TRAVEL_TO_SURFACE: ("Reach Surface", "Delay"),
        RedesignDivePhase.AT_AIR_STOP: ("Leave Stop", ""),
        RedesignDivePhase.AT_O2_STOP_WAITING: ("Leave Stop", "On O2"),
        RedesignDivePhase.AT_O2_STOP_ON_O2: ("Leave Stop", "Off O2"),
        RedesignDivePhase.AT_O2_STOP_OFF_O2: ("Convert to Air", "On O2"),
        RedesignDivePhase.AT_O2_STOP_AIR_BREAK: ("Convert to Air", "On O2"),
        RedesignDivePhase.SURFACE_CLEAN_TIME: ("", ""),
        RedesignDivePhase.SURFACE_COMPLETE: ("", ""),
    }[state.phase]


def _status_value_text(state: RedesignDiveState) -> str:
    if (
        state.phase is RedesignDivePhase.TRAVEL_TO_SURFACE
        and state.o2_anchor is not None
        and state.last_delay_result is not None
        and state.last_delay_result.outcome is DelayOutcome.O2_SURFACE_DELAY
    ):
        return "On O2/ Traveling"
    return {
        RedesignDivePhase.READY: "Ready",
        RedesignDivePhase.DESCENT: "Descent",
        RedesignDivePhase.BOTTOM: "Bottom",
        RedesignDivePhase.TRAVEL_TO_FIRST_STOP: "Traveling",
        RedesignDivePhase.TRAVEL_TO_SURFACE: "Traveling",
        RedesignDivePhase.AT_AIR_STOP: "At Stop",
        RedesignDivePhase.AT_O2_STOP_WAITING: "TSV",
        RedesignDivePhase.AT_O2_STOP_ON_O2: "On O2",
        RedesignDivePhase.AT_O2_STOP_OFF_O2: "Off O2",
        RedesignDivePhase.AT_O2_STOP_AIR_BREAK: "Off O2",
        RedesignDivePhase.SURFACE_CLEAN_TIME: "Clean Time",
        RedesignDivePhase.SURFACE_COMPLETE: "Surface",
    }[state.phase]


def _current_stop_remaining_sec(state: RedesignDiveState, now: datetime) -> float | None:
    if state.plan is None or state.stop_anchor is None:
        return None
    stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if stop is None:
        return None
    elapsed = state.stop_anchor.carried_elapsed_sec
    if state.phase not in {RedesignDivePhase.AT_O2_STOP_OFF_O2, RedesignDivePhase.AT_O2_STOP_AIR_BREAK}:
        elapsed += (now - state.stop_anchor.started_at).total_seconds()
    return max((stop.duration_min * 60) - elapsed, 0.0)


def _display_profile(state: RedesignDiveState, now: datetime | None = None) -> DiveProfile | None:
    if state.plan is not None:
        return state.plan.profile
    if state.phase is not RedesignDivePhase.BOTTOM or state.bottom_anchor is None or state.depth_input.parsed_depth_fsw is None or now is None:
        return None
    bottom_elapsed_sec = max((now - state.bottom_anchor.started_at).total_seconds(), 0.0)
    bottom_time_min = max(math.ceil(bottom_elapsed_sec / 60), 1)
    return build_profile(state.mode, state.depth_input.parsed_depth_fsw, bottom_time_min)


def _estimated_descent_depth(state: RedesignDiveState, now: datetime) -> int:
    if state.bottom_anchor is None:
        return 0
    depth = state.depth_input.parsed_depth_fsw
    estimate = int(max((now - state.bottom_anchor.started_at).total_seconds(), 0.0))
    if depth is None:
        return estimate
    return min(estimate, depth)


def _next_stop_summary(profile: DiveProfile) -> str:
    next_stop = next_stop_after(profile, None)
    if next_stop is None:
        return "Surface"
    return f"{next_stop.depth_fsw} fsw for {next_stop.duration_min} min"


def _arrival_audit_entries(state: RedesignDiveState, now: datetime, *, code: str) -> tuple[AuditEntry, ...]:
    entries = [_entry(code, now)]
    if state.phase not in {RedesignDivePhase.TRAVEL_TO_FIRST_STOP, RedesignDivePhase.TRAVEL_TO_SURFACE} or state.plan is None or state.travel_anchor is None:
        return tuple(entries)
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index) if state.plan.current_stop_index is not None else None
    target_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
    if code == "RS":
        planned_travel_sec = (current_stop.depth_fsw * 2) if current_stop is not None else None
        arrival_label = "Arrived Surface early"
    elif state.plan.current_stop_index is None:
        planned_travel_sec = state.plan.profile.time_to_first_stop_sec
        arrival_label = f"Arrived {target_stop.depth_fsw} fsw early" if target_stop is not None else "Arrived Surface early"
    else:
        planned_travel_sec = int(abs(current_stop.depth_fsw - target_stop.depth_fsw) * 2) if current_stop is not None and target_stop is not None else None
        arrival_label = f"Arrived {target_stop.depth_fsw} fsw early" if target_stop is not None else "Arrived Surface early"
    if planned_travel_sec is None:
        return tuple(entries)
    elapsed_sec = max((now - state.travel_anchor.started_at).total_seconds(), 0.0)
    if elapsed_sec < planned_travel_sec:
        entries.append(_audit_message("EARLY_ARRIVAL", now, f"{arrival_label} ({_format_mmss(planned_travel_sec - elapsed_sec)} before planned travel time)"))
    return tuple(entries)


def _leave_stop_audit_entries(state: RedesignDiveState, now: datetime, current_stop) -> tuple[AuditEntry, ...]:
    entries = [_entry(f"L{current_stop.index}", now)]
    remaining = _current_stop_remaining_sec(state, now)
    if remaining is not None and remaining > 0.0:
        entries.append(_audit_message("EARLY_STOP", now, f"Left {current_stop.depth_fsw} fsw early ({_format_mmss(remaining)} remaining)"))
    return tuple(entries)


def _continuous_o2_elapsed_sec(state: RedesignDiveState, now: datetime) -> float:
    if state.o2_anchor is None:
        return 0.0
    return max((now - state.o2_anchor.started_at).total_seconds(), 0.0)


def _continuous_o2_remaining_sec(state: RedesignDiveState, now: datetime) -> float | None:
    if state.plan is None:
        return None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or current_stop.gas != "o2":
        return None
    current_remaining = _current_stop_remaining_sec(state, now)
    if current_remaining is None:
        return None
    remaining = max(current_remaining, 0.0)
    next_index = current_stop.index + 1
    while True:
        next_stop = stop_by_index(state.plan.profile, next_index)
        if next_stop is None or next_stop.gas != "o2":
            break
        remaining += next_stop.duration_min * 60
        next_index += 1
    return remaining


def _air_break_due_sec(state: RedesignDiveState, now: datetime) -> float | None:
    if state.phase not in {
        RedesignDivePhase.AT_O2_STOP_ON_O2,
        RedesignDivePhase.AT_O2_STOP_OFF_O2,
        RedesignDivePhase.AT_O2_STOP_AIR_BREAK,
    }:
        return None
    if state.phase in {RedesignDivePhase.AT_O2_STOP_OFF_O2, RedesignDivePhase.AT_O2_STOP_AIR_BREAK}:
        return None
    continuous_remaining = _continuous_o2_remaining_sec(state, now)
    if continuous_remaining is not None and continuous_remaining <= 35 * 60:
        return None
    if state.o2_anchor is None:
        return None
    return max((30 * 60) - _continuous_o2_elapsed_sec(state, now), 0.0)


def _estimated_travel_depth(state: RedesignDiveState, now: datetime) -> int:
    if state.plan is None or state.travel_anchor is None:
        return state.depth_input.parsed_depth_fsw or 0
    elapsed_sec = max((now - state.travel_anchor.started_at).total_seconds(), 0.0)
    if state.plan.current_stop_index is None:
        start_depth = state.plan.profile.input_depth_fsw
    else:
        current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
        start_depth = state.plan.profile.input_depth_fsw if current_stop is None else current_stop.depth_fsw
    estimated = start_depth - int(round(elapsed_sec / 2))
    return max(estimated, 0)
