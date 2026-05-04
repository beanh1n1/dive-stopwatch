from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ...contracts.timers import TimerState
from .rules import (
    CHAMBER_INITIAL_DEPTH_FSW,
    CHAMBER_TT5_ASCENT_TO_SURFACE_RATE_FPM,
    CHAMBER_TT6_ASCENT_TO_SURFACE_RATE_FPM,
    CHAMBER_ASCENT_TO_30_RATE_FPM,
    CHAMBER_CLEAN_TIME_SEC,
    can_leave_stop,
    can_start_air_break,
    can_start_next_o2_period,
    current_o2_period_complete,
    current_air_break_complete,
)
from .state import ChamberGasState, ChamberPhase, ChamberState, make_initial_state


def reduce_action(state: ChamberState, action: EngineAction, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if action is EngineAction.RESET:
        return make_initial_state(), ()
    state = maybe_finish_clean_time(state, now)
    if action in {EngineAction.LEAVE_SURFACE, EngineAction.START_CHAMBER}:
        return leave_surface(state, now)
    if action in {EngineAction.REACH_BOTTOM, EngineAction.REACH_TREATMENT_DEPTH}:
        return reach_bottom(state, now)
    if action is EngineAction.CONFIRM_ON_O2:
        return confirm_on_o2(state, now)
    if action is EngineAction.TOGGLE_OFF_O2:
        return toggle_off_o2(state, now)
    if action is EngineAction.LEAVE_STOP:
        return leave_stop(state, now)
    if action is EngineAction.REACH_STOP:
        return reach_stop(state, now)
    if action is EngineAction.REACH_SURFACE:
        return reach_surface(state, now)
    return state, (invalid_action_event(now, action.name),)


def leave_surface(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if state.phase is not ChamberPhase.READY:
        return state, (invalid_action_event(now, EngineAction.LEAVE_SURFACE.name),)
    entry_depth = 0 if state.treatment_handoff is None else state.treatment_handoff.entry_depth_fsw
    updated = replace(
        state,
        phase=ChamberPhase.DESCENT_TO_60,
        current_depth_fsw=entry_depth,
        descent_timer=TimerState(started_at=now),
        gas_state=ChamberGasState.ON_O2 if state.ready_on_o2 else ChamberGasState.AIR,
    )
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_SURFACE, at=now),)


def reach_bottom(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if state.phase is not ChamberPhase.DESCENT_TO_60:
        return state, (invalid_action_event(now, EngineAction.REACH_BOTTOM.name),)
    updated = replace(
        state,
        phase=ChamberPhase.AT_STOP,
        gas_state=ChamberGasState.WAITING_ON_O2,
        current_depth_fsw=CHAMBER_INITIAL_DEPTH_FSW,
        stop_depth_fsw=CHAMBER_INITIAL_DEPTH_FSW,
        descent_timer=None,
        stop_wait_timer=TimerState(started_at=now),
    )
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_BOTTOM, at=now, payload={"depth_fsw": CHAMBER_INITIAL_DEPTH_FSW}),)


def confirm_on_o2(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if not can_start_next_o2_period(state, now):
        return state, (invalid_action_event(now, EngineAction.CONFIRM_ON_O2.name),)
    updated = state
    if state.phase is ChamberPhase.AIR_BREAK:
        updated = replace(updated, air_break_timer=None)
    if (
        updated.stop_depth_fsw == 30
        and updated.selected_table == "TT5"
        and updated.o2_periods_30_completed >= 1
        and not updated.pending_arrival_break_at_30
    ):
        updated = replace(
            updated,
            phase=ChamberPhase.ON_O2,
            gas_state=ChamberGasState.ON_O2,
            stop_wait_timer=None,
            o2_timer=None,
            pending_arrival_break_at_30=False,
            final_ascent_o2_ready_at_30=True,
        )
        return updated, (
            AuditEvent(
                kind=AuditEventKind.REACHED_STOP,
                at=now,
                payload={"confirmation": "on_o2", "depth_fsw": updated.stop_depth_fsw},
            ),
        )
    updated = replace(
        updated,
        phase=ChamberPhase.ON_O2,
        gas_state=ChamberGasState.ON_O2,
        stop_wait_timer=None,
        o2_timer=TimerState(started_at=now),
        pending_arrival_break_at_30=False,
        final_ascent_o2_ready_at_30=False,
    )
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "on_o2", "depth_fsw": updated.stop_depth_fsw}),)


def toggle_off_o2(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if state.phase is ChamberPhase.READY:
        updated = replace(
            state,
            ready_on_o2=not state.ready_on_o2,
            gas_state=ChamberGasState.ON_O2 if not state.ready_on_o2 else ChamberGasState.AIR,
        )
        return updated, ()
    if not can_start_air_break(state, now):
        return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)
    keep_arrival_break_flag = state.pending_arrival_break_at_30 and state.phase is ChamberPhase.AT_STOP
    updated = state
    if state.phase is ChamberPhase.ON_O2 and current_o2_period_complete(state, now):
        updated = _commit_completed_o2_period(state)
    if updated.stop_depth_fsw == 60 and updated.selected_table is None and updated.o2_periods_60_completed >= 2:
        updated = replace(updated, selected_table="TT6")
    updated = replace(
        updated,
        phase=ChamberPhase.AIR_BREAK,
        gas_state=ChamberGasState.AIR_BREAK,
        o2_timer=None,
        air_break_timer=TimerState(started_at=now),
        stop_wait_timer=None,
        pending_arrival_break_at_30=keep_arrival_break_flag,
    )
    return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "air_break_start", "depth_fsw": updated.stop_depth_fsw}),)


def leave_stop(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if not can_leave_stop(state, now):
        return state, (invalid_action_event(now, EngineAction.LEAVE_STOP.name),)
    updated = _commit_completed_o2_period(state) if state.phase is ChamberPhase.ON_O2 and current_o2_period_complete(state, now) else state
    if updated.stop_depth_fsw == 60:
        selected_table = "TT5" if updated.selected_table is None else updated.selected_table
        updated = replace(
            updated,
            selected_table=selected_table,
            phase=ChamberPhase.TRAVEL_TO_30,
            gas_state=ChamberGasState.ON_O2,
            current_depth_fsw=60,
            travel_timer=TimerState(started_at=now),
            travel_from_depth_fsw=60,
            travel_to_depth_fsw=30,
            travel_rate_fpm=CHAMBER_ASCENT_TO_30_RATE_FPM,
            stop_depth_fsw=None,
            stop_wait_timer=None,
            o2_timer=None,
            air_break_timer=None,
            pending_arrival_break_at_30=False,
            final_ascent_o2_ready_at_30=False,
        )
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": 60, "table": selected_table}),)
    ascent_rate = CHAMBER_TT5_ASCENT_TO_SURFACE_RATE_FPM if updated.selected_table == "TT5" else CHAMBER_TT6_ASCENT_TO_SURFACE_RATE_FPM
    updated = replace(
        updated,
        phase=ChamberPhase.TRAVEL_TO_SURFACE,
        gas_state=ChamberGasState.ON_O2,
        current_depth_fsw=30,
        travel_timer=TimerState(started_at=now),
        travel_from_depth_fsw=30,
        travel_to_depth_fsw=0,
        travel_rate_fpm=ascent_rate,
        stop_depth_fsw=None,
        stop_wait_timer=None,
        o2_timer=None,
        air_break_timer=None,
        pending_arrival_break_at_30=False,
        final_ascent_o2_ready_at_30=False,
    )
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": 30, "table": updated.selected_table or ""}),)


def reach_stop(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if state.phase is not ChamberPhase.TRAVEL_TO_30:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    updated = replace(
        state,
        phase=ChamberPhase.AT_STOP,
        gas_state=ChamberGasState.ON_O2,
        current_depth_fsw=30,
        stop_depth_fsw=30,
        stop_wait_timer=TimerState(started_at=now),
        travel_timer=None,
        travel_from_depth_fsw=None,
        travel_to_depth_fsw=None,
        travel_rate_fpm=None,
        pending_arrival_break_at_30=True,
        final_ascent_o2_ready_at_30=False,
    )
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"depth_fsw": 30, "gas": "o2"}),)


def reach_surface(state: ChamberState, now: datetime) -> tuple[ChamberState, tuple[AuditEvent, ...]]:
    if state.phase is not ChamberPhase.TRAVEL_TO_SURFACE:
        return state, (invalid_action_event(now, EngineAction.REACH_SURFACE.name),)
    updated = replace(
        state,
        phase=ChamberPhase.COMPLETE_CLEAN_TIME,
        gas_state=ChamberGasState.AIR,
        current_depth_fsw=0,
        travel_timer=None,
        travel_from_depth_fsw=None,
        travel_to_depth_fsw=None,
        travel_rate_fpm=None,
        stop_depth_fsw=None,
        stop_wait_timer=None,
        clean_time_timer=TimerState(started_at=now),
    )
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now),)


def maybe_finish_clean_time(state: ChamberState, now: datetime) -> ChamberState:
    if state.phase is not ChamberPhase.COMPLETE_CLEAN_TIME or state.clean_time_timer is None:
        return state
    if (now - state.clean_time_timer.started_at).total_seconds() < CHAMBER_CLEAN_TIME_SEC:
        return state
    return make_initial_state()


def _commit_completed_o2_period(state: ChamberState) -> ChamberState:
    if state.stop_depth_fsw == 60:
        return replace(state, o2_periods_60_completed=state.o2_periods_60_completed + 1)
    if state.stop_depth_fsw == 30:
        return replace(state, o2_periods_30_completed=state.o2_periods_30_completed + 1)
    return state
