from __future__ import annotations

from datetime import datetime
import math

from ...contracts.actions import EngineAction
from ...contracts.view import EngineMode, EngineView, ObligationKind, TimerRole, TimerView, WarningKind
from ...domain.depth import linear_depth_fsw
from .rules import (
    CHAMBER_CLEAN_TIME_SEC,
    CHAMBER_INITIAL_DEPTH_FSW,
    can_leave_stop,
    can_start_air_break,
    can_start_next_o2_period,
    current_air_break_complete,
    current_air_break_target_sec,
    current_o2_period_complete,
    current_o2_target_sec,
    descent_rate_fpm,
    travel_elapsed_sec,
)
from .state import ChamberGasState, ChamberPhase, ChamberState


def derive_view(state: ChamberState, now: datetime) -> EngineView:
    return EngineView(
        mode=EngineMode.CHAMBER,
        phase_name=state.phase.name,
        gas_state_name=_gas_state_name(state),
        committed_depth_fsw=state.current_depth_fsw,
        display_depth_fsw=_display_depth_fsw(state, now),
        obligation=_obligation(state, now),
        active_timer=_active_timer(state, now),
        next_stop_depth_fsw=_next_stop_depth_fsw(state),
        next_stop_duration_min=_next_stop_duration_min(state),
        current_stop_depth_fsw=state.stop_depth_fsw,
        current_stop_remaining_sec=_current_stop_remaining_sec(state, now),
        available_actions=tuple(action.name for action in _available_actions(state, now)),
        pending_action_text=_pending_action_text(state, now),
        warnings=(WarningKind.NONE,),
    )


def _gas_state_name(state: ChamberState) -> str:
    if state.phase is ChamberPhase.COMPLETE_CLEAN_TIME:
        return "CLEAN_TIME"
    return {
        ChamberGasState.AIR: "AIR",
        ChamberGasState.WAITING_ON_O2: "WAITING_ON_O2",
        ChamberGasState.ON_O2: "ON_O2",
        ChamberGasState.AIR_BREAK: "AIR_BREAK",
    }[state.gas_state]


def _obligation(state: ChamberState, now: datetime) -> ObligationKind:
    if state.phase is ChamberPhase.READY:
        return ObligationKind.LEAVE_SURFACE
    if state.phase is ChamberPhase.DESCENT_TO_60:
        return ObligationKind.REACH_BOTTOM
    if state.phase is ChamberPhase.AT_STOP:
        if state.gas_state is ChamberGasState.WAITING_ON_O2:
            return ObligationKind.CONFIRM_ON_O2
        return ObligationKind.START_AIR_BREAK
    if state.phase is ChamberPhase.ON_O2:
        if can_leave_stop(state, now):
            return ObligationKind.LEAVE_STOP
        if can_start_air_break(state, now):
            return ObligationKind.START_AIR_BREAK
    if state.phase is ChamberPhase.AIR_BREAK and current_air_break_complete(state, now):
        return ObligationKind.CONFIRM_ON_O2
    if state.phase is ChamberPhase.TRAVEL_TO_30:
        return ObligationKind.REACH_STOP
    if state.phase is ChamberPhase.TRAVEL_TO_SURFACE:
        return ObligationKind.REACH_SURFACE
    return ObligationKind.NONE


def _available_actions(state: ChamberState, now: datetime) -> tuple[EngineAction, ...]:
    if state.phase is ChamberPhase.READY:
        return (EngineAction.LEAVE_SURFACE, EngineAction.TOGGLE_OFF_O2, EngineAction.RESET)
    if state.phase is ChamberPhase.DESCENT_TO_60:
        return (EngineAction.REACH_BOTTOM, EngineAction.RESET)
    if state.phase is ChamberPhase.AT_STOP:
        if state.gas_state is ChamberGasState.WAITING_ON_O2:
            return (EngineAction.CONFIRM_ON_O2, EngineAction.RESET)
        if state.stop_depth_fsw in {60, 30}:
            return (EngineAction.TOGGLE_OFF_O2, EngineAction.RESET)
        return (EngineAction.LEAVE_STOP, EngineAction.RESET)
    if state.phase is ChamberPhase.ON_O2:
        actions = [EngineAction.RESET]
        if can_leave_stop(state, now):
            actions.insert(0, EngineAction.LEAVE_STOP)
        if can_start_air_break(state, now):
            actions.insert(0, EngineAction.TOGGLE_OFF_O2)
        if can_start_next_o2_period(state, now):
            actions.insert(0, EngineAction.CONFIRM_ON_O2)
        return tuple(dict.fromkeys(actions))
    if state.phase is ChamberPhase.AIR_BREAK:
        actions = [EngineAction.RESET]
        if current_air_break_complete(state, now):
            actions.insert(0, EngineAction.CONFIRM_ON_O2)
        return tuple(actions)
    if state.phase is ChamberPhase.TRAVEL_TO_30:
        return (EngineAction.REACH_STOP, EngineAction.RESET)
    if state.phase is ChamberPhase.TRAVEL_TO_SURFACE:
        return (EngineAction.REACH_SURFACE, EngineAction.RESET)
    if state.phase is ChamberPhase.COMPLETE_CLEAN_TIME:
        return (EngineAction.RESET,)
    return (EngineAction.RESET,)


def _pending_action_text(state: ChamberState, now: datetime) -> str | None:
    if state.phase is ChamberPhase.AT_STOP:
        if state.gas_state is ChamberGasState.WAITING_ON_O2:
            return "On O2"
        if state.stop_depth_fsw == 30 and state.pending_arrival_break_at_30:
            return "Air Break for 5 min" if state.selected_table == "TT5" else "Air Break for 15 min"
        if state.stop_depth_fsw == 60:
            return "Air Break for 5 min"
        if state.stop_depth_fsw == 30:
            return "Air Break for 5 min" if state.selected_table == "TT5" else "Air Break for 15 min"
        return "Surface"
    if state.phase is ChamberPhase.ON_O2:
        if state.stop_depth_fsw == 30 and state.selected_table == "TT5" and state.final_ascent_o2_ready_at_30:
            return "Surface"
        if not current_o2_period_complete(state, now):
            if state.stop_depth_fsw == 60:
                if state.selected_table == "TT6" and state.o2_periods_60_completed >= 3:
                    return "Next Stop"
                return "5 min air break"
            if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
                return "5 min air break"
            if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
                return "15 min air break" if state.o2_periods_30_completed < 1 else "Surface"
        if state.stop_depth_fsw == 60:
            next_count = state.o2_periods_60_completed + 1
            if state.selected_table == "TT6" and next_count >= 3:
                return "5 min air break"
            if state.selected_table is None and next_count < 2:
                return "5 min air break"
            return "Next Stop"
        if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
            return "5 min air break"
        if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
            return "15 min air break" if (state.o2_periods_30_completed + 1) == 1 else "Surface"
        return "Surface"
    if state.phase is ChamberPhase.AIR_BREAK:
        return "On O2"
    if state.phase is ChamberPhase.TRAVEL_TO_30:
        return "Reach Stop"
    if state.phase is ChamberPhase.TRAVEL_TO_SURFACE:
        return "Reach Surface"
    if state.phase is ChamberPhase.COMPLETE_CLEAN_TIME:
        return None
    return None


def _active_timer(state: ChamberState, now: datetime) -> TimerView | None:
    if state.phase is ChamberPhase.DESCENT_TO_60 and state.descent_timer is not None:
        return TimerView(role=TimerRole.TRAVEL, elapsed_sec=(now - state.descent_timer.started_at).total_seconds())
    if state.phase is ChamberPhase.AT_STOP and state.stop_wait_timer is not None:
        return TimerView(role=TimerRole.STOP, elapsed_sec=(now - state.stop_wait_timer.started_at).total_seconds())
    if state.phase is ChamberPhase.ON_O2 and state.o2_timer is not None:
        target = current_o2_target_sec(state)
        elapsed_sec = (now - state.o2_timer.started_at).total_seconds()
        return TimerView(role=TimerRole.CHAMBER_SEGMENT, elapsed_sec=elapsed_sec, remaining_sec=None if target is None else max(target - elapsed_sec, 0.0))
    if state.phase is ChamberPhase.AIR_BREAK and state.air_break_timer is not None:
        target = current_air_break_target_sec(state)
        elapsed_sec = (now - state.air_break_timer.started_at).total_seconds()
        return TimerView(role=TimerRole.AIR_BREAK, elapsed_sec=elapsed_sec, remaining_sec=None if target is None else max(target - elapsed_sec, 0.0))
    if state.phase in {ChamberPhase.TRAVEL_TO_30, ChamberPhase.TRAVEL_TO_SURFACE} and state.travel_timer is not None:
        return TimerView(role=TimerRole.TRAVEL, elapsed_sec=travel_elapsed_sec(state, now))
    if state.phase is ChamberPhase.COMPLETE_CLEAN_TIME and state.clean_time_timer is not None:
        elapsed_sec = (now - state.clean_time_timer.started_at).total_seconds()
        return TimerView(role=TimerRole.CLEAN_TIME, elapsed_sec=elapsed_sec, remaining_sec=max(CHAMBER_CLEAN_TIME_SEC - elapsed_sec, 0.0))
    return None


def _display_depth_fsw(state: ChamberState, now: datetime) -> int | None:
    if state.phase is ChamberPhase.DESCENT_TO_60 and state.descent_timer is not None:
        start_depth = 0 if state.treatment_handoff is None else state.treatment_handoff.entry_depth_fsw
        return linear_depth_fsw(
            start_depth_fsw=start_depth,
            end_depth_fsw=CHAMBER_INITIAL_DEPTH_FSW,
            elapsed_sec=(now - state.descent_timer.started_at).total_seconds(),
            rate_fsw_per_sec=descent_rate_fpm(state) / 60.0,
        )
    if state.phase in {ChamberPhase.TRAVEL_TO_30, ChamberPhase.TRAVEL_TO_SURFACE} and state.travel_timer is not None and state.travel_from_depth_fsw is not None and state.travel_to_depth_fsw is not None and state.travel_rate_fpm is not None:
        if state.travel_rate_fpm == 1.0:
            return _stepped_chamber_travel_depth_fsw(state, now)
        return linear_depth_fsw(
            start_depth_fsw=state.travel_from_depth_fsw,
            end_depth_fsw=state.travel_to_depth_fsw,
            elapsed_sec=travel_elapsed_sec(state, now),
            rate_fsw_per_sec=state.travel_rate_fpm / 60.0,
        )
    return state.current_depth_fsw


def _stepped_chamber_travel_depth_fsw(state: ChamberState, now: datetime) -> int:
    assert state.travel_from_depth_fsw is not None
    assert state.travel_to_depth_fsw is not None
    elapsed_sec = travel_elapsed_sec(state, now)
    stepped_distance = math.floor(max(elapsed_sec, 0.0) / 60.0)
    if state.travel_from_depth_fsw <= state.travel_to_depth_fsw:
        return min(state.travel_from_depth_fsw + stepped_distance, state.travel_to_depth_fsw)
    return max(state.travel_from_depth_fsw - stepped_distance, state.travel_to_depth_fsw)


def _current_stop_remaining_sec(state: ChamberState, now: datetime) -> float | None:
    if state.phase is ChamberPhase.ON_O2 and state.o2_timer is not None:
        target = current_o2_target_sec(state)
        if target is None:
            return None
        return max(target - (now - state.o2_timer.started_at).total_seconds(), 0.0)
    return None


def _next_stop_depth_fsw(state: ChamberState) -> int | None:
    if state.phase is ChamberPhase.ON_O2 and state.stop_depth_fsw == 60:
        return 30
    if state.phase is ChamberPhase.TRAVEL_TO_30:
        return 30
    if state.phase is ChamberPhase.TRAVEL_TO_SURFACE:
        return 0
    return None


def _next_stop_duration_min(state: ChamberState) -> int | None:
    if state.phase is ChamberPhase.ON_O2 and state.stop_depth_fsw == 60:
        if state.selected_table == "TT6":
            return 15
        if state.o2_periods_60_completed + 1 >= 2:
            return 5
    return None
