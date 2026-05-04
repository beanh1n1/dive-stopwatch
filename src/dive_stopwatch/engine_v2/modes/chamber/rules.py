from __future__ import annotations

from datetime import datetime

from ...contracts.timers import elapsed
from .state import ChamberGasState
from .state import ChamberPhase, ChamberState


CHAMBER_INITIAL_DEPTH_FSW = 60
CHAMBER_DESCENT_RATE_FPM = 20.0
CHAMBER_TREATMENT_DESCENT_RATE_FPM = 75.0
CHAMBER_ASCENT_TO_30_RATE_FPM = 1.0
CHAMBER_TT5_ASCENT_TO_SURFACE_RATE_FPM = 1.0
CHAMBER_TT6_ASCENT_TO_SURFACE_RATE_FPM = 30.0
CHAMBER_60_O2_PERIOD_SEC = 20 * 60
CHAMBER_60_AIR_BREAK_SEC = 5 * 60
CHAMBER_TT5_30_ARRIVAL_BREAK_SEC = 5 * 60
CHAMBER_TT5_30_O2_PERIOD_SEC = 20 * 60
CHAMBER_TT5_30_MID_BREAK_SEC = 5 * 60
CHAMBER_TT6_30_AIR_BREAK_SEC = 15 * 60
CHAMBER_TT6_30_O2_PERIOD_SEC = 60 * 60
CHAMBER_CLEAN_TIME_SEC = 10 * 60
CHAMBER_MAX_60_O2_PERIODS = 5
CHAMBER_MAX_TT5_30_O2_PERIODS = 3
CHAMBER_MAX_TT6_30_O2_PERIODS = 5


def descent_rate_fpm(state: ChamberState) -> float:
    if state.treatment_handoff is not None:
        return CHAMBER_TREATMENT_DESCENT_RATE_FPM
    return CHAMBER_DESCENT_RATE_FPM


def current_o2_target_sec(state: ChamberState) -> int | None:
    if state.stop_depth_fsw == 60:
        return CHAMBER_60_O2_PERIOD_SEC
    if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
        if state.final_ascent_o2_ready_at_30:
            return None
        return CHAMBER_TT5_30_O2_PERIOD_SEC
    if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
        return CHAMBER_TT6_30_O2_PERIOD_SEC
    return None


def current_air_break_target_sec(state: ChamberState) -> int | None:
    if state.stop_depth_fsw == 60:
        return CHAMBER_60_AIR_BREAK_SEC
    if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
        if state.pending_arrival_break_at_30:
            return CHAMBER_TT5_30_ARRIVAL_BREAK_SEC
        if state.o2_periods_30_completed == 1 and not state.final_ascent_o2_ready_at_30:
            return CHAMBER_TT5_30_ARRIVAL_BREAK_SEC
        return None
    if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
        if state.pending_arrival_break_at_30:
            return CHAMBER_TT6_30_AIR_BREAK_SEC
        if state.o2_periods_30_completed == 1:
            return CHAMBER_TT6_30_AIR_BREAK_SEC
        return None
    return None


def current_o2_period_complete(state: ChamberState, now: datetime) -> bool:
    if state.phase is not ChamberPhase.ON_O2 or state.o2_timer is None:
        return False
    target = current_o2_target_sec(state)
    return target is not None and elapsed(state.o2_timer, now) >= target


def current_air_break_complete(state: ChamberState, now: datetime) -> bool:
    if state.phase is not ChamberPhase.AIR_BREAK or state.air_break_timer is None:
        return False
    target = current_air_break_target_sec(state)
    return target is not None and elapsed(state.air_break_timer, now) >= target


def can_leave_stop(state: ChamberState, now: datetime) -> bool:
    if (
        state.phase is ChamberPhase.ON_O2
        and state.stop_depth_fsw == 60
        and state.selected_table == "TT6"
        and state.o2_periods_60_completed >= 3
    ):
        return True
    if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
        return state.phase is ChamberPhase.ON_O2 and state.final_ascent_o2_ready_at_30
    if state.phase is ChamberPhase.ON_O2 and not current_o2_period_complete(state, now):
        return False
    if state.stop_depth_fsw == 60:
        next_count = state.o2_periods_60_completed + 1
        if state.selected_table is None:
            return next_count >= 2
        if state.selected_table == "TT6":
            return False
        return False
    if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
        return state.phase is ChamberPhase.ON_O2 and (state.o2_periods_30_completed + 1) >= 2
    return False


def can_start_air_break(state: ChamberState, now: datetime) -> bool:
    if (
        state.phase is ChamberPhase.AT_STOP
        and state.stop_depth_fsw == 30
        and state.gas_state is ChamberGasState.ON_O2
        and state.pending_arrival_break_at_30
    ):
        return True
    if state.phase is not ChamberPhase.ON_O2:
        return False
    if state.stop_depth_fsw == 60:
        if not current_o2_period_complete(state, now):
            return True
        next_count = state.o2_periods_60_completed + 1
        if state.selected_table is None:
            return next_count <= 2
        return next_count <= CHAMBER_MAX_60_O2_PERIODS
    if state.stop_depth_fsw == 30 and state.selected_table == "TT5":
        if state.final_ascent_o2_ready_at_30:
            return False
        if not current_o2_period_complete(state, now):
            return True
        next_count = state.o2_periods_30_completed + 1
        return next_count == 1
    if state.stop_depth_fsw == 30 and state.selected_table == "TT6":
        if not current_o2_period_complete(state, now):
            return True
        next_count = state.o2_periods_30_completed + 1
        return next_count == 1
    return False


def can_start_next_o2_period(state: ChamberState, now: datetime) -> bool:
    if state.phase is ChamberPhase.AT_STOP and state.gas_state is ChamberGasState.WAITING_ON_O2:
        return True
    if state.phase is ChamberPhase.AIR_BREAK:
        return current_air_break_complete(state, now)
    return False


def travel_elapsed_sec(state: ChamberState, now: datetime) -> float:
    return elapsed(state.travel_timer, now)
