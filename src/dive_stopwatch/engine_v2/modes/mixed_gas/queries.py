from __future__ import annotations

from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.timers import elapsed
from ...contracts.view import EngineMode, EngineView, ObligationKind, TimerRole, TimerView, WarningKind
from ...domain.depth import linear_depth_fsw
from .plan import build_mixed_gas_plan, mixed_gas_chamber_o2_half_periods
from .rules import (
    MIXED_GAS_20_FSW_GRACE_SEC,
    MIXED_GAS_AIR_BREAK_SEC,
    MIXED_GAS_CLEAN_TIME_SEC,
    air_break_due,
    air_break_due_remaining_sec,
    can_begin_descent,
    current_stop,
    current_stop_remaining_sec,
    has_supported_bottom_mix,
    has_supported_depth,
    has_minimum_bottom_mix_percent,
    invalid_depth_label,
    invalid_bottom_mix_label,
    max_supported_depth_label,
    next_stop,
    requires_20fsw_air_descent,
    supported_bottom_mix_range_label,
)
from .state import MixedGasBreathingGas, MixedGasDelayStatus, MixedGasPhase, MixedGasShiftState, MixedGasState, MixedGasTimerKind


def derive_view(state: MixedGasState, now: datetime) -> EngineView:
    current = current_stop(state)
    upcoming = next_stop(state.plan, state.current_stop_index)
    bottom_preview = _bottom_preview_plan(state, now)
    bottom_next_stop = None if bottom_preview is None else next_stop(bottom_preview, None)
    surface_only_surd_bottom = _surface_only_surd_bottom(state, bottom_next_stop)
    surface_only_surd_travel = _surface_only_surd_travel(state, upcoming)
    surface_only_surd_forty_stop = _surface_only_surd_forty_stop(state, current, upcoming)
    surface_deco_required = _surface_deco_required(state, bottom_preview=bottom_preview)
    surd_surface_half_periods = _surd_surface_half_periods(state, bottom_preview=bottom_preview)
    return EngineView(
        mode=EngineMode.MIXED_GAS,
        phase_name=state.phase.name,
        gas_state_name=_gas_state_name(state),
        committed_depth_fsw=state.depth_fsw,
        display_depth_fsw=_display_depth_fsw(state, now, current, surface_only_surd_travel=surface_only_surd_travel),
        obligation=_obligation(state, surface_only_surd_travel=surface_only_surd_travel),
        active_timer=_active_timer(state, now, current),
        next_stop_depth_fsw=None if upcoming is None or surface_only_surd_travel or surface_only_surd_forty_stop else upcoming.depth_fsw,
        next_stop_duration_min=None if upcoming is None or surface_only_surd_travel or surface_only_surd_forty_stop else upcoming.duration_min,
        current_stop_depth_fsw=20 if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT else (None if current is None else current.depth_fsw),
        current_stop_remaining_sec=_current_stop_remaining(state, now),
        travel_overtime_sec=_travel_overtime_sec(state, now, surface_only_surd_travel=surface_only_surd_travel),
        available_actions=tuple(action.name for action in _available_actions(state)),
        warnings=_warnings(state, now),
        traveling_on_o2=_traveling_on_o2(state, current, upcoming),
        air_break_due_remaining_sec=air_break_due_remaining_sec(state, now),
        gas_mix_label=_gas_mix_label(state),
        pending_action_text=(
            "Surface"
            if (surface_only_surd_bottom or surface_only_surd_travel or surface_only_surd_forty_stop)
            else _pending_action_text(state)
        ),
        profile_preview_label=_profile_preview_label(state),
        current_stop_gas_name=None if current is None else current.gas,
        next_stop_gas_name=None if upcoming is None or surface_only_surd_travel or surface_only_surd_forty_stop else upcoming.gas,
        active_hold_label=_active_hold_label(state, now),
        delay_active=state.delay.status is MixedGasDelayStatus.ACTIVE,
        bottom_table_depth_fsw=None if bottom_preview is None else bottom_preview.table_depth_fsw,
        bottom_table_bottom_time_min=None if bottom_preview is None else bottom_preview.table_bottom_time_min,
        bottom_next_stop_depth_fsw=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.depth_fsw,
        bottom_next_stop_duration_min=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.duration_min,
        bottom_next_stop_gas_name=None if bottom_next_stop is None or surface_only_surd_bottom else bottom_next_stop.gas,
        surface_deco_required=surface_deco_required,
        surd_surface_half_periods=surd_surface_half_periods,
    )


def _gas_state_name(state: MixedGasState) -> str:
    if state.phase is MixedGasPhase.COMPLETE:
        return "CLEAN_TIME"
    if state.shift_state is MixedGasShiftState.AWAITING_50_50_CONFIRM:
        return "WAITING_ON_50_50"
    if state.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
        return "WAITING_ON_O2"
    if state.shift_state is MixedGasShiftState.OFF_O2:
        return "INTERRUPTED_O2"
    if state.shift_state is MixedGasShiftState.AIR_BREAK:
        return "AIR_BREAK"
    return {
        MixedGasBreathingGas.AIR: "AIR",
        MixedGasBreathingGas.BOTTOM_MIX: "BOTTOM_MIX",
        MixedGasBreathingGas.HELIOX_50_50: "HELIOX_50_50",
        MixedGasBreathingGas.OXYGEN: "ON_O2",
    }[state.breathing_gas]


def _display_depth_fsw(state: MixedGasState, now: datetime, current, *, surface_only_surd_travel: bool = False) -> int | None:
    if state.phase is MixedGasPhase.DESCENT_TO_20_ON_AIR and state.surface_timer is not None:
        return min(
            linear_depth_fsw(
                start_depth_fsw=0,
                end_depth_fsw=20,
                elapsed_sec=max(elapsed(state.surface_timer.timer, now) - _total_hold_elapsed_sec(state, now), 0.0),
                rate_fsw_per_sec=75 / 60,
            ),
            20,
        )
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT:
        return 20
    if state.phase is MixedGasPhase.DESCENT_TO_BOTTOM:
        start_depth = 20 if requires_20fsw_air_descent(state) else 0
        active = state.travel_timer or state.surface_timer
        if active is not None and state.depth_fsw is not None:
            return linear_depth_fsw(
                start_depth_fsw=start_depth,
                end_depth_fsw=state.depth_fsw,
                elapsed_sec=max(elapsed(active.timer, now) - _total_hold_elapsed_sec(state, now), 0.0),
                rate_fsw_per_sec=75 / 60,
            )
    if state.phase in {MixedGasPhase.TRAVEL_TO_FIRST_STOP, MixedGasPhase.TRAVEL_TO_SURFACE}:
        if state.delay.status is MixedGasDelayStatus.ACTIVE and state.delay.depth_fsw is not None:
            return state.delay.depth_fsw
        if state.travel_timer is None:
            return state.depth_fsw
        if surface_only_surd_travel:
            return _surface_only_surd_ascent_depth(state, now)
        start_depth = (
            20
            if state.phase is MixedGasPhase.TRAVEL_TO_SURFACE and state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR
            else (state.travel_start_depth_fsw if state.travel_start_depth_fsw is not None else (state.depth_fsw if state.current_stop_index is None else (None if current is None else current.depth_fsw)))
        )
        if start_depth is None:
            return state.depth_fsw
        end_depth = 0 if state.phase is MixedGasPhase.TRAVEL_TO_SURFACE or current is None else current.depth_fsw
        if state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP:
            upcoming = next_stop(state.plan, state.current_stop_index)
            end_depth = 0 if upcoming is None else upcoming.depth_fsw
        return linear_depth_fsw(
            start_depth_fsw=start_depth,
            end_depth_fsw=end_depth,
            elapsed_sec=max(elapsed(state.travel_timer.timer, now) - state.delay.paused_travel_sec, 0.0),
            rate_fsw_per_sec=30 / 60,
        )
    if state.phase is MixedGasPhase.AT_STOP and current is not None:
        return current.depth_fsw
    return state.depth_fsw


def _obligation(state: MixedGasState, *, surface_only_surd_travel: bool = False) -> ObligationKind:
    if surface_only_surd_travel:
        return ObligationKind.REACH_SURFACE
    if state.phase is MixedGasPhase.READY and can_begin_descent(state):
        return ObligationKind.LEAVE_SURFACE
    if state.phase is MixedGasPhase.DESCENT_TO_20_ON_AIR:
        return ObligationKind.REACH_STOP
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.shift_state is MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM:
        return ObligationKind.CONFIRM_BOTTOM_MIX
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR:
        return ObligationKind.LEAVE_BOTTOM
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT:
        return ObligationKind.LEAVE_STOP
    if state.phase is MixedGasPhase.DESCENT_TO_BOTTOM:
        return ObligationKind.REACH_BOTTOM
    if state.phase is MixedGasPhase.BOTTOM:
        return ObligationKind.LEAVE_BOTTOM
    if state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP:
        return ObligationKind.REACH_STOP
    if state.phase is MixedGasPhase.AT_STOP and state.shift_state is MixedGasShiftState.AWAITING_50_50_CONFIRM:
        return ObligationKind.CONFIRM_50_50
    if state.phase is MixedGasPhase.AT_STOP and state.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
        return ObligationKind.CONFIRM_ON_O2
    if state.phase is MixedGasPhase.AT_STOP:
        return ObligationKind.LEAVE_STOP
    if state.phase is MixedGasPhase.TRAVEL_TO_SURFACE:
        return ObligationKind.REACH_SURFACE
    return ObligationKind.NONE


def _available_actions(state: MixedGasState) -> tuple[EngineAction, ...]:
    if _surface_only_surd_travel(state, next_stop(state.plan, state.current_stop_index)):
        return (
            EngineAction.REACH_SURFACE,
            EngineAction.END_DELAY if state.delay.status is MixedGasDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    if state.phase is MixedGasPhase.READY:
        actions = [EngineAction.RESET]
        if can_begin_descent(state):
            actions.insert(0, EngineAction.LEAVE_SURFACE)
        return tuple(actions)
    if state.phase in {MixedGasPhase.DESCENT_TO_20_ON_AIR, MixedGasPhase.DESCENT_TO_BOTTOM}:
        return (
            EngineAction.REACH_STOP if state.phase is MixedGasPhase.DESCENT_TO_20_ON_AIR else EngineAction.REACH_BOTTOM,
            EngineAction.END_HOLD if state.active_hold_started_at is not None else EngineAction.START_HOLD,
            EngineAction.RESET,
        )
    if state.phase is MixedGasPhase.DESCENT_TO_20_ON_AIR:
        return (EngineAction.REACH_STOP, EngineAction.RESET)
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT:
        if state.shift_state is MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM:
            return (EngineAction.LEAVE_STOP, EngineAction.CONFIRM_BOTTOM_MIX, EngineAction.RESET)
        if state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR:
            return (EngineAction.LEAVE_BOTTOM, EngineAction.CONFIRM_BOTTOM_MIX, EngineAction.RESET)
        return (EngineAction.LEAVE_STOP, EngineAction.CONVERT_TO_AIR, EngineAction.RESET)
    if state.phase is MixedGasPhase.DESCENT_TO_BOTTOM:
        return (EngineAction.REACH_BOTTOM, EngineAction.RESET)
    if state.phase is MixedGasPhase.BOTTOM:
        return (EngineAction.LEAVE_BOTTOM, EngineAction.RESET)
    if state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP:
        return (
            EngineAction.REACH_STOP,
            EngineAction.END_DELAY if state.delay.status is MixedGasDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    if state.phase is MixedGasPhase.AT_STOP:
        if state.delay.status is MixedGasDelayStatus.ACTIVE:
            return (EngineAction.END_DELAY, EngineAction.RESET)
        if state.shift_state is MixedGasShiftState.AWAITING_50_50_CONFIRM:
            return (EngineAction.CONFIRM_50_50, EngineAction.LEAVE_STOP, EngineAction.RESET)
        if state.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
            return (EngineAction.CONFIRM_ON_O2, EngineAction.LEAVE_STOP, EngineAction.RESET)
        if state.breathing_gas is MixedGasBreathingGas.OXYGEN or state.shift_state in {MixedGasShiftState.OFF_O2, MixedGasShiftState.AIR_BREAK}:
            return (EngineAction.LEAVE_STOP, EngineAction.TOGGLE_OFF_O2, EngineAction.RESET)
        return (EngineAction.LEAVE_STOP, EngineAction.RESET)
    if state.phase is MixedGasPhase.TRAVEL_TO_SURFACE:
        return (
            EngineAction.REACH_SURFACE,
            EngineAction.END_DELAY if state.delay.status is MixedGasDelayStatus.ACTIVE else EngineAction.START_DELAY,
            EngineAction.RESET,
        )
    return (EngineAction.RESET,)


def _active_timer(state: MixedGasState, now: datetime, current) -> TimerView | None:
    if state.delay.status is MixedGasDelayStatus.ACTIVE and state.delay.started_at is not None:
        return TimerView(role=TimerRole.TRAVEL, elapsed_sec=max((now - state.delay.started_at).total_seconds(), 0.0), remaining_sec=None)
    timer = (
        state.clean_time_timer
        or state.air_break_timer
        or state.shift_timer
        or state.interruption_timer
        or state.stop_timer
        or state.travel_timer
        or state.bottom_timer
        or state.grace_window_timer
        or state.surface_timer
    )
    if timer is None:
        return None
    role = {
        MixedGasTimerKind.BOTTOM: TimerRole.BOTTOM,
        MixedGasTimerKind.TRAVEL: TimerRole.TRAVEL,
        MixedGasTimerKind.STOP: TimerRole.STOP,
        MixedGasTimerKind.SHIFT: TimerRole.STOP,
        MixedGasTimerKind.AIR_BREAK: TimerRole.AIR_BREAK,
        MixedGasTimerKind.CLEAN_TIME: TimerRole.CLEAN_TIME,
        MixedGasTimerKind.GRACE_WINDOW: TimerRole.TRAVEL,
    }[timer.kind]
    remaining_sec = None
    if timer.kind is MixedGasTimerKind.CLEAN_TIME:
        remaining_sec = max(MIXED_GAS_CLEAN_TIME_SEC - elapsed(timer.timer, now), 0.0)
    elif timer.kind is MixedGasTimerKind.AIR_BREAK:
        remaining_sec = max(MIXED_GAS_AIR_BREAK_SEC - elapsed(timer.timer, now), 0.0)
    elif state.phase is MixedGasPhase.AT_STOP and current is not None and state.stop_timer is not None:
        remaining_sec = current_stop_remaining_sec(state, now)
    elif state.phase in {MixedGasPhase.DESCENT_TO_20_ON_AIR, MixedGasPhase.AT_20_PREBOTTOM_SHIFT} and state.grace_window_timer is not None:
        remaining_sec = max(MIXED_GAS_20_FSW_GRACE_SEC - elapsed(state.grace_window_timer.timer, now), 0.0)
    return TimerView(role=role, elapsed_sec=elapsed(timer.timer, now), remaining_sec=remaining_sec)


def _current_stop_remaining(state: MixedGasState, now: datetime) -> float | None:
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.grace_window_timer is not None:
        return max(MIXED_GAS_20_FSW_GRACE_SEC - elapsed(state.grace_window_timer.timer, now), 0.0)
    if state.phase is MixedGasPhase.AT_STOP:
        return current_stop_remaining_sec(state, now)
    return None


def _travel_overtime_sec(state: MixedGasState, now: datetime, *, surface_only_surd_travel: bool = False) -> float | None:
    if surface_only_surd_travel:
        return None
    if state.phase is not MixedGasPhase.TRAVEL_TO_FIRST_STOP or state.plan is None or state.travel_timer is None:
        return None
    if state.current_stop_index is not None:
        return None
    first_stop = next_stop(state.plan, None)
    start_depth_fsw = state.travel_start_depth_fsw
    if first_stop is None or start_depth_fsw is None or start_depth_fsw <= first_stop.depth_fsw:
        return None
    planned_sec = (start_depth_fsw - first_stop.depth_fsw) / (30 / 60)
    overtime = elapsed(state.travel_timer.timer, now) - planned_sec
    return overtime if overtime > 0 else None


def _gas_mix_label(state: MixedGasState) -> str | None:
    if state.bottom_mix_o2_percent is None:
        return None
    label = f"Bottom Mix: {_format_o2_percent(state.bottom_mix_o2_percent)}% O2"
    if requires_20fsw_air_descent(state):
        return f"{label} | Air to 20 fsw required"
    return label


def _pending_action_text(state: MixedGasState) -> str | None:
    if state.depth_fsw is not None and state.depth_fsw > 0 and not has_supported_depth(state):
        return "Depth not supported"
    if not has_supported_depth(state):
        return "Input Max Depth"
    if state.bottom_mix_o2_percent is not None and not has_supported_bottom_mix(state):
        return "Bottom mix not supported for depth"
    if not has_supported_bottom_mix(state):
        return "Input Bottom Mix"
    if state.phase is MixedGasPhase.READY:
        return "Leave Surface"
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.shift_state is MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM:
        return "Confirm Bottom Mix"
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR:
        return "Leave Bottom"
    if state.phase is MixedGasPhase.AT_STOP and state.shift_state is MixedGasShiftState.AWAITING_50_50_CONFIRM:
        return "Confirm 50/50"
    if state.phase is MixedGasPhase.AT_STOP and state.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
        return "On O2"
    if state.phase is MixedGasPhase.AT_STOP and state.shift_state is MixedGasShiftState.OFF_O2:
        return "On O2"
    return None


def _profile_preview_label(state: MixedGasState) -> str | None:
    depth_label = invalid_depth_label(state)
    if depth_label is not None:
        return depth_label
    invalid_label = invalid_bottom_mix_label(state)
    if invalid_label is not None:
        return invalid_label
    if state.depth_fsw is not None and state.bottom_mix_o2_percent is not None and not has_supported_bottom_mix(state):
        return supported_bottom_mix_range_label(state)
    labels: list[str] = []
    if requires_20fsw_air_descent(state):
        labels.append("Air to 20 fsw required")
    max_depth_label = max_supported_depth_label(state)
    if max_depth_label is not None:
        labels.append(max_depth_label)
    if state.depth_fsw is not None:
        range_label = supported_bottom_mix_range_label(state)
        if range_label is not None:
            labels.append(range_label)
    if not labels:
        return None
    return " | ".join(labels)


def _warnings(state: MixedGasState, now: datetime) -> tuple[WarningKind, ...]:
    if state.depth_fsw is not None and state.depth_fsw > 0 and not has_supported_depth(state):
        return (WarningKind.UNSUPPORTED_DEPTH,)
    if not has_minimum_bottom_mix_percent(state):
        return (WarningKind.UNSUPPORTED_BOTTOM_MIX,)
    if state.depth_fsw is None:
        return (WarningKind.NONE,)
    if air_break_due(state, now):
        return (WarningKind.AIR_BREAK_DUE,)
    if state.bottom_mix_o2_percent is not None and not has_supported_bottom_mix(state):
        return (WarningKind.UNSUPPORTED_BOTTOM_MIX,)
    return (WarningKind.NONE,)


def _bottom_preview_plan(state: MixedGasState, now: datetime):
    if state.phase is not MixedGasPhase.BOTTOM or state.bottom_timer is None or state.depth_fsw is None:
        return None
    bottom_elapsed_min = max(int(((now - state.bottom_timer.timer.started_at).total_seconds() + 59.999) // 60), 0)
    return build_mixed_gas_plan(
        depth_fsw=state.depth_fsw,
        bottom_time_min=bottom_elapsed_min,
        bottom_mix_o2_percent=state.bottom_mix_o2_percent,
    )


def _surface_only_surd_bottom(state: MixedGasState, bottom_next_stop) -> bool:
    return bool(
        state.selected_surd
        and state.phase is MixedGasPhase.BOTTOM
        and (bottom_next_stop is None or bottom_next_stop.depth_fsw < 40)
    )


def _surface_only_surd_travel(state: MixedGasState, upcoming) -> bool:
    return bool(
        state.selected_surd
        and state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP
        and upcoming is not None
        and upcoming.depth_fsw < 40
    )


def _surface_only_surd_forty_stop(state: MixedGasState, current, upcoming) -> bool:
    return bool(
        state.selected_surd
        and state.phase is MixedGasPhase.AT_STOP
        and current is not None
        and current.depth_fsw == 40
        and upcoming is not None
        and upcoming.depth_fsw < 40
    )


def _surface_deco_required(state: MixedGasState, *, bottom_preview) -> bool:
    half_periods = _surd_surface_half_periods(state, bottom_preview=bottom_preview)
    return (half_periods or 0) > 0


def _surd_surface_half_periods(state: MixedGasState, *, bottom_preview) -> int | None:
    if not state.selected_surd:
        return None
    if state.phase is MixedGasPhase.BOTTOM and bottom_preview is not None:
        return mixed_gas_chamber_o2_half_periods(
            depth_fsw=bottom_preview.table_depth_fsw,
            bottom_time_min=bottom_preview.table_bottom_time_min,
            bottom_mix_o2_percent=state.bottom_mix_o2_percent,
        )
    if state.plan is not None:
        return mixed_gas_chamber_o2_half_periods(
            depth_fsw=state.plan.table_depth_fsw,
            bottom_time_min=state.plan.table_bottom_time_min,
            bottom_mix_o2_percent=state.bottom_mix_o2_percent,
        )
    return None


def _surface_only_surd_ascent_depth(state: MixedGasState, now: datetime) -> int:
    if state.travel_timer is None:
        return state.depth_fsw or 0
    start_depth = state.travel_start_depth_fsw if state.travel_start_depth_fsw is not None else (state.depth_fsw or 0)
    travel_elapsed_sec = max(elapsed(state.travel_timer.timer, now) - state.delay.paused_travel_sec, 0.0)
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


def _format_o2_percent(percent: float) -> str:
    formatted = f"{percent:.1f}"
    if formatted.endswith(".0"):
        return formatted[:-2]
    return formatted


def _traveling_on_o2(state: MixedGasState, current, upcoming) -> bool:
    return (
        state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP
        and state.breathing_gas is MixedGasBreathingGas.OXYGEN
        and current is not None
        and upcoming is not None
        and current.gas == "o2"
        and upcoming.gas == "o2"
    )


def _total_hold_elapsed_sec(state: MixedGasState, now: datetime) -> float:
    active_elapsed = 0.0
    if state.active_hold_started_at is not None:
        active_elapsed = max((now - state.active_hold_started_at).total_seconds(), 0.0)
    return state.hold_elapsed_sec + active_elapsed


def _active_hold_label(state: MixedGasState, now: datetime) -> str | None:
    if state.phase not in {MixedGasPhase.DESCENT_TO_20_ON_AIR, MixedGasPhase.DESCENT_TO_BOTTOM} or state.active_hold_started_at is None or state.hold_index <= 0:
        return None
    hold_elapsed = max((now - state.active_hold_started_at).total_seconds(), 0.0)
    minutes = int(hold_elapsed // 60)
    seconds = int(hold_elapsed % 60)
    return f"H{state.hold_index}   {minutes:02d}:{seconds:02d}"
