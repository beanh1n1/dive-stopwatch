from __future__ import annotations

from datetime import datetime

from ...domain.air_o2_profiles import build_profile, build_surface_profile, next_stop_after, no_decompression_limit, stop_by_index
from ...contracts.actions import EngineAction
from ...contracts.view import EngineMode, EngineView, ObligationKind, TimerRole, TimerView, WarningKind
from ...domain.depth import linear_depth_fsw
from .rules import AIR_CLEAN_TIME_SEC, air_break_due, air_break_due_remaining_sec, can_leave_stop, elapsed, estimated_travel_depth
from .rules import has_supported_depth as air_has_supported_depth
from .rules import invalid_depth_label as air_invalid_depth_label
from .state import AirDelayStatus, AirGasState, AirPhase, AirState, AirTimer, AirTimerKind


def derive_view(state: AirState, now: datetime) -> EngineView:
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index) if state.plan is not None and state.plan.current_stop_index is not None else None
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index) if state.plan is not None else None
    bottom_profile = _bottom_profile(state, now)
    bottom_next_stop = None if bottom_profile is None else next_stop_after(bottom_profile, None)
    surface_only_surd_bottom = _surface_only_surd_bottom(bottom_next_stop, state)
    surface_only_surd_travel = _surface_only_surd_travel(next_stop, state)
    surface_only_surd_forty_stop = _surface_only_surd_forty_stop(state, next_stop)
    surface_deco_required = _surface_deco_required(state, bottom_profile=bottom_profile)
    surd_surface_half_periods = _surd_surface_half_periods(state, bottom_profile=bottom_profile)
    active_timer = _active_timer_view(state, now, current_stop)
    warnings = tuple(kind for kind in (
        WarningKind.UNSUPPORTED_DEPTH if state.phase is AirPhase.READY and state.depth_fsw is not None and state.depth_fsw > 0 and not air_has_supported_depth(state.depth_fsw) else WarningKind.NONE,
        WarningKind.AIR_BREAK_DUE if air_break_due(state, now) else WarningKind.NONE,
    ) if kind is not WarningKind.NONE) or (WarningKind.NONE,)
    return EngineView(
        mode=EngineMode.AIR if state.mode.name == "AIR" else EngineMode.AIR_O2,
        phase_name=state.phase.name,
        gas_state_name=_gas_state_name(state, active_timer),
        committed_depth_fsw=state.depth_fsw,
        display_depth_fsw=_display_depth_fsw(state, now, current_stop, surface_only_surd_travel=surface_only_surd_travel),
        obligation=_obligation(state, now, surface_only_surd_travel=surface_only_surd_travel),
        active_timer=active_timer,
        next_stop_depth_fsw=None if next_stop is None or surface_only_surd_travel or surface_only_surd_forty_stop else next_stop.depth_fsw,
        next_stop_duration_min=None if next_stop is None or surface_only_surd_travel or surface_only_surd_forty_stop else next_stop.duration_min,
        current_stop_depth_fsw=None if current_stop is None else current_stop.depth_fsw,
        current_stop_remaining_sec=_current_stop_remaining_sec(state, now, current_stop),
        travel_overtime_sec=_travel_overtime_sec(state, now, surface_only_surd_travel=surface_only_surd_travel),
        available_actions=tuple(action.name for action in _available_actions(state, now)),
        current_stop_gas_name=None if current_stop is None else current_stop.gas,
        next_stop_gas_name=None if next_stop is None or surface_only_surd_travel or surface_only_surd_forty_stop else next_stop.gas,
        active_hold_label=_active_hold_label(state, now),
        delay_active=state.delay.status is AirDelayStatus.ACTIVE,
        traveling_on_o2=_traveling_on_o2(state, current_stop, next_stop),
        air_break_due_remaining_sec=air_break_due_remaining_sec(state, now),
        bottom_table_depth_fsw=None if bottom_profile is None else bottom_profile.table_depth_fsw,
        bottom_table_bottom_time_min=None if bottom_profile is None else bottom_profile.table_bottom_time_min,
        bottom_repeat_group=None if bottom_profile is None else bottom_profile.repeat_group,
        bottom_next_stop_depth_fsw=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.depth_fsw,
        bottom_next_stop_duration_min=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.duration_min,
        bottom_next_stop_gas_name=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.gas,
        warnings=warnings,
        pending_action_text=(
            "Surface"
            if (surface_only_surd_bottom or surface_only_surd_travel or surface_only_surd_forty_stop)
            else ("Depth not supported" if state.phase is AirPhase.READY and state.depth_fsw is not None and state.depth_fsw > 0 and not air_has_supported_depth(state.depth_fsw) else None)
        ),
        profile_preview_label=air_invalid_depth_label(state.depth_fsw),
        surface_deco_required=surface_deco_required,
        surd_surface_half_periods=surd_surface_half_periods,
    )


def _gas_state_name(state: AirState, active_timer: TimerView | None) -> str:
    if state.phase is AirPhase.COMPLETE and active_timer is not None and active_timer.role is TimerRole.CLEAN_TIME and (active_timer.remaining_sec or 0.0) > 0:
        return "CLEAN_TIME"
    return state.gas_state.name


def _obligation(state: AirState, now: datetime, *, surface_only_surd_travel: bool = False) -> ObligationKind:
    if surface_only_surd_travel:
        return ObligationKind.REACH_SURFACE
    if state.phase is AirPhase.AT_STOP and state.gas_state is AirGasState.WAITING_ON_O2:
        return ObligationKind.CONFIRM_ON_O2
    if state.phase is AirPhase.AT_STOP and not can_leave_stop(state, now):
        return ObligationKind.NONE
    if state.phase is AirPhase.READY and not air_has_supported_depth(state.depth_fsw):
        return ObligationKind.NONE
    return {
        AirPhase.READY: ObligationKind.LEAVE_SURFACE,
        AirPhase.DESCENT: ObligationKind.REACH_BOTTOM,
        AirPhase.BOTTOM: ObligationKind.LEAVE_BOTTOM,
        AirPhase.TRAVEL_TO_FIRST_STOP: ObligationKind.REACH_STOP,
        AirPhase.TRAVEL_TO_SURFACE: ObligationKind.REACH_SURFACE,
        AirPhase.AT_STOP: ObligationKind.LEAVE_STOP,
        AirPhase.COMPLETE: ObligationKind.NONE,
    }[state.phase]


def _available_actions(state: AirState, now: datetime) -> tuple[EngineAction, ...]:
    if _surface_only_surd_travel(next_stop_after(state.plan.profile, state.plan.current_stop_index) if state.plan is not None else None, state):
        return (
            EngineAction.REACH_SURFACE,
            EngineAction.END_DELAY if state.delay.status is AirDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    if state.phase is AirPhase.AT_STOP and state.gas_state is AirGasState.WAITING_ON_O2:
        return (EngineAction.CONFIRM_ON_O2, EngineAction.RESET)
    if state.phase is AirPhase.AT_STOP and state.gas_state in {AirGasState.ON_O2, AirGasState.INTERRUPTED_O2, AirGasState.AIR_BREAK}:
        actions = [EngineAction.TOGGLE_OFF_O2, EngineAction.RESET]
        if state.gas_state in {AirGasState.INTERRUPTED_O2, AirGasState.AIR_BREAK}:
            actions.insert(len(actions) - 1, EngineAction.CONVERT_TO_AIR)
        if can_leave_stop(state, now):
            actions.insert(0, EngineAction.LEAVE_STOP)
        return tuple(actions)
    if state.phase is AirPhase.TRAVEL_TO_FIRST_STOP:
        return (
            EngineAction.REACH_STOP,
            EngineAction.END_DELAY if state.delay.status is AirDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    if state.phase is AirPhase.TRAVEL_TO_SURFACE:
        return (
            EngineAction.REACH_SURFACE,
            EngineAction.END_DELAY if state.delay.status is AirDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    return {
        AirPhase.READY: ((EngineAction.LEAVE_SURFACE, EngineAction.RESET) if air_has_supported_depth(state.depth_fsw) else (EngineAction.RESET,)),
        AirPhase.DESCENT: (
            EngineAction.REACH_BOTTOM,
            EngineAction.END_HOLD if state.active_hold_started_at is not None else EngineAction.START_HOLD,
            EngineAction.RESET,
        ),
        AirPhase.BOTTOM: (EngineAction.LEAVE_BOTTOM, EngineAction.RESET),
        AirPhase.AT_STOP: ((EngineAction.LEAVE_STOP, EngineAction.RESET) if can_leave_stop(state, now) else (EngineAction.RESET,)),
        AirPhase.COMPLETE: (EngineAction.RESET,),
    }[state.phase]


def _timer_role(kind: AirTimerKind) -> TimerRole:
    return {
        AirTimerKind.BOTTOM: TimerRole.BOTTOM,
        AirTimerKind.TRAVEL: TimerRole.TRAVEL,
        AirTimerKind.STOP: TimerRole.STOP,
        AirTimerKind.TSV: TimerRole.STOP,
        AirTimerKind.INTERRUPTION: TimerRole.STOP,
        AirTimerKind.AIR_BREAK: TimerRole.AIR_BREAK,
        AirTimerKind.CLEAN_TIME: TimerRole.CLEAN_TIME,
    }[kind]


def _active_timer_view(state: AirState, now: datetime, current_stop) -> TimerView | None:
    if state.phase is AirPhase.COMPLETE and state.clean_time_timer is not None:
        clean_elapsed = elapsed(state.clean_time_timer, now)
        return TimerView(
            role=TimerRole.CLEAN_TIME,
            elapsed_sec=clean_elapsed,
            remaining_sec=max(AIR_CLEAN_TIME_SEC - clean_elapsed, 0.0),
        )
    if (
        state.phase in {AirPhase.TRAVEL_TO_FIRST_STOP, AirPhase.TRAVEL_TO_SURFACE}
        and state.delay.status is AirDelayStatus.ACTIVE
        and state.delay.started_at is not None
    ):
        return TimerView(
            role=TimerRole.TRAVEL,
            elapsed_sec=max((now - state.delay.started_at).total_seconds(), 0.0),
            remaining_sec=None,
        )
    timer = _select_active_timer(state)
    if timer is None:
        return None
    timer_elapsed = elapsed(timer, now)
    remaining = None
    if _traveling_on_o2(state, current_stop, next_stop_after(state.plan.profile, state.plan.current_stop_index) if state.plan is not None else None):
        remaining = _traveling_on_o2_remaining_sec(state, now)
    if current_stop is not None and timer.kind is AirTimerKind.STOP:
        remaining = max((current_stop.duration_min * 60) - timer_elapsed, 0.0)
    if timer.kind is AirTimerKind.AIR_BREAK:
        remaining = max((5 * 60) - timer_elapsed, 0.0)
    return TimerView(role=_timer_role(timer.kind), elapsed_sec=timer_elapsed, remaining_sec=remaining)


def _current_stop_remaining_sec(state: AirState, now: datetime, current_stop) -> float | None:
    if state.phase is not AirPhase.AT_STOP:
        return None
    if current_stop is None:
        return None
    total_sec = current_stop.duration_min * 60
    if state.stop_timer is not None:
        return max(total_sec - elapsed(state.stop_timer, now), 0.0)
    return float(total_sec)


def _select_active_timer(state: AirState) -> AirTimer | None:
    if state.phase in {AirPhase.DESCENT, AirPhase.BOTTOM} and state.surface_timer is not None:
        return state.surface_timer
    return (
        state.clean_time_timer
        or
        state.air_break_timer
        or state.interruption_timer
        or state.tsv_timer
        or state.stop_timer
        or state.travel_timer
        or state.bottom_timer
    )


def _display_depth_fsw(state: AirState, now: datetime, current_stop, *, surface_only_surd_travel: bool = False) -> int | None:
    if state.phase in {AirPhase.READY, AirPhase.BOTTOM, AirPhase.COMPLETE}:
        return state.depth_fsw
    if state.phase is AirPhase.DESCENT:
        if state.surface_timer is None:
            return state.depth_fsw
        descent_elapsed = max(elapsed(state.surface_timer, now) - _total_hold_elapsed_sec(state, now), 0.0)
        if state.depth_fsw is None:
            return int(descent_elapsed)
        return linear_depth_fsw(
            start_depth_fsw=0,
            end_depth_fsw=state.depth_fsw,
            elapsed_sec=descent_elapsed,
            rate_fsw_per_sec=1.0,
        )
    if state.phase in {AirPhase.TRAVEL_TO_FIRST_STOP, AirPhase.TRAVEL_TO_SURFACE}:
        if state.delay.status is AirDelayStatus.ACTIVE and state.delay.depth_fsw is not None:
            return state.delay.depth_fsw
        if state.plan is None or state.depth_fsw is None or state.travel_timer is None:
            return state.depth_fsw
        if surface_only_surd_travel:
            return _surface_only_surd_ascent_depth(state, now)
        return estimated_travel_depth(state, now)
    if state.phase is AirPhase.AT_STOP and current_stop is not None:
        return current_stop.depth_fsw
    return state.depth_fsw


def _travel_overtime_sec(state: AirState, now: datetime, *, surface_only_surd_travel: bool = False) -> float | None:
    if surface_only_surd_travel:
        return None
    if state.phase is not AirPhase.TRAVEL_TO_FIRST_STOP or state.plan is None or state.travel_timer is None:
        return None
    if state.plan.current_stop_index is not None:
        return None
    planned = state.plan.profile.time_to_first_stop_sec
    if planned is None:
        return None
    overtime = elapsed(state.travel_timer, now) - planned
    return overtime if overtime > 0 else None


def _traveling_on_o2(state: AirState, current_stop, next_stop) -> bool:
    return (
        state.phase is AirPhase.TRAVEL_TO_FIRST_STOP
        and state.gas_state is AirGasState.ON_O2
        and current_stop is not None
        and next_stop is not None
        and current_stop.gas == "o2"
        and next_stop.gas == "o2"
    )


def _traveling_on_o2_remaining_sec(state: AirState, now: datetime) -> float | None:
    if state.plan is None or state.plan.current_stop_index is None or state.travel_timer is None:
        return None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or next_stop is None or current_stop.gas != "o2" or next_stop.gas != "o2":
        return None
    return max((next_stop.duration_min * 60) - elapsed(state.travel_timer, now), 0.0)


def _total_hold_elapsed_sec(state: AirState, now: datetime) -> float:
    active_elapsed = 0.0
    if state.active_hold_started_at is not None:
        active_elapsed = max((now - state.active_hold_started_at).total_seconds(), 0.0)
    return state.hold_elapsed_sec + active_elapsed


def _active_hold_label(state: AirState, now: datetime) -> str | None:
    if state.phase is not AirPhase.DESCENT or state.active_hold_started_at is None or state.hold_index <= 0:
        return None
    hold_elapsed = max((now - state.active_hold_started_at).total_seconds(), 0.0)
    minutes = int(hold_elapsed // 60)
    seconds = int(hold_elapsed % 60)
    return f"H{state.hold_index}   {minutes:02d}:{seconds:02d}"


def _bottom_profile(state: AirState, now: datetime):
    if state.phase is not AirPhase.BOTTOM or state.depth_fsw is None or state.surface_timer is None:
        return None
    limit_min = no_decompression_limit(state.mode, state.depth_fsw)
    if limit_min is None:
        return None
    elapsed_min = int((elapsed(state.surface_timer, now) + 59) // 60)
    if elapsed_min <= limit_min:
        return None
    return build_profile(state.mode, state.depth_fsw, elapsed_min)


def _surface_only_surd_bottom(bottom_next_stop, state: AirState) -> bool:
    return bool(
        state.selected_surd
        and state.phase is AirPhase.BOTTOM
        and (bottom_next_stop is None or bottom_next_stop.depth_fsw < 40)
    )


def _surface_only_surd_travel(next_stop, state: AirState) -> bool:
    return bool(
        state.selected_surd
        and state.phase is AirPhase.TRAVEL_TO_FIRST_STOP
        and next_stop is not None
        and next_stop.depth_fsw < 40
    )


def _surface_only_surd_forty_stop(state: AirState, next_stop) -> bool:
    if not state.selected_surd or state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return False
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or current_stop.depth_fsw != 40 or next_stop is None:
        return False
    return next_stop.depth_fsw < 40


def _surface_deco_required(state: AirState, *, bottom_profile) -> bool:
    half_periods = _surd_surface_half_periods(state, bottom_profile=bottom_profile)
    return (half_periods or 0) > 0


def _surd_surface_half_periods(state: AirState, *, bottom_profile) -> int | None:
    if not state.selected_surd:
        return None
    if state.phase is AirPhase.BOTTOM and bottom_profile is not None:
        profile = build_surface_profile(
            bottom_profile.table_depth_fsw,
            bottom_profile.table_bottom_time_min,
        )
        return profile.chamber_o2_half_periods
    if state.plan is not None:
        profile = build_surface_profile(
            state.plan.profile.table_depth_fsw,
            state.plan.profile.table_bottom_time_min,
        )
        return profile.chamber_o2_half_periods
    return None


def _surface_only_surd_ascent_depth(state: AirState, now: datetime) -> int:
    if state.travel_timer is None:
        return state.depth_fsw or 0
    start_depth = state.depth_fsw or 0
    travel_elapsed_sec = max(elapsed(state.travel_timer, now) - state.delay.paused_travel_sec, 0.0)
    if start_depth <= 40:
        return linear_depth_fsw(
            start_depth_fsw=start_depth,
            end_depth_fsw=0,
            elapsed_sec=travel_elapsed_sec,
            rate_fsw_per_sec=40 / 60,
        )
    to_forty_sec = (start_depth - 40) / (30 / 60)
    if travel_elapsed_sec <= to_forty_sec:
        return linear_depth_fsw(
            start_depth_fsw=start_depth,
            end_depth_fsw=40,
            elapsed_sec=travel_elapsed_sec,
            rate_fsw_per_sec=30 / 60,
        )
    return linear_depth_fsw(
        start_depth_fsw=40,
        end_depth_fsw=0,
        elapsed_sec=travel_elapsed_sec - to_forty_sec,
        rate_fsw_per_sec=40 / 60,
    )
