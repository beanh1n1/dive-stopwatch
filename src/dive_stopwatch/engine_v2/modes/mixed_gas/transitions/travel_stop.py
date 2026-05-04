from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState, elapsed
from ..invariants import validate_state
from ..rules import air_break_due, crosses_ninety, current_stop, has_ninety_stop, next_stop, pause_timer
from ..state import (
    MixedGasBreathingGas,
    MixedGasDelayState,
    MixedGasPhase,
    MixedGasShiftState,
    MixedGasState,
    MixedGasTimer,
    MixedGasTimerKind,
)


def reach_stop(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.TRAVEL_TO_FIRST_STOP or state.plan is None:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    next_planned = next_stop(state.plan, state.current_stop_index)
    if next_planned is None:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)

    first_stop = state.current_stop_index is None
    awaiting_50_50 = state.shift_state is MixedGasShiftState.AWAITING_50_50_CONFIRM
    stop_timer = MixedGasTimer(
        kind=MixedGasTimerKind.STOP,
        timer=TimerState(started_at=now if first_stop else state.travel_timer.timer.started_at),
    )

    updated = replace(
        state,
        phase=MixedGasPhase.AT_STOP,
        current_stop_index=next_planned.index,
        stop_timer=stop_timer,
        travel_timer=None,
        travel_start_depth_fsw=None,
        delay=MixedGasDelayState(),
    )
    if next_planned.depth_fsw == 90 or awaiting_50_50:
        updated = replace(updated, shift_state=MixedGasShiftState.AWAITING_50_50_CONFIRM)
    elif next_planned.depth_fsw == 30 and next_planned.gas == "o2":
        updated = replace(
            updated,
            stop_timer=None,
            shift_timer=MixedGasTimer(kind=MixedGasTimerKind.SHIFT, timer=TimerState(started_at=now)),
            shift_state=MixedGasShiftState.AWAITING_O2_CONFIRM,
        )
    elif next_planned.gas == "50_50":
        updated = replace(updated, breathing_gas=MixedGasBreathingGas.HELIOX_50_50)
    elif next_planned.gas == "o2":
        updated = replace(updated, breathing_gas=MixedGasBreathingGas.OXYGEN)
    validate_state(updated)
    payload = {"depth_fsw": next_planned.depth_fsw, "gas": next_planned.gas}
    if updated.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
        payload["gas"] = "o2_waiting"
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload=payload),)


def leave_stop(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_STOP or state.plan is None or state.current_stop_index is None:
        return state, (invalid_action_event(now, EngineAction.LEAVE_STOP.name),)
    current = current_stop(state)
    upcoming = next_stop(state.plan, state.current_stop_index)
    next_shift_state = state.shift_state
    if (
        current is not None
        and upcoming is not None
        and current.depth_fsw > 90
        and not has_ninety_stop(state.plan)
        and crosses_ninety(current.depth_fsw, upcoming.depth_fsw)
    ):
        next_shift_state = MixedGasShiftState.AWAITING_50_50_CONFIRM
    updated = replace(
        state,
        phase=MixedGasPhase.TRAVEL_TO_SURFACE if upcoming is None else MixedGasPhase.TRAVEL_TO_FIRST_STOP,
        stop_timer=None,
        travel_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        travel_start_depth_fsw=None if current is None else current.depth_fsw,
        shift_state=next_shift_state,
        delay=MixedGasDelayState(),
    )
    validate_state(updated)
    payload = {} if current is None else {"depth_fsw": current.depth_fsw, "gas": current.gas}
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload=payload),)


def confirm_50_50(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_STOP or state.shift_state is not MixedGasShiftState.AWAITING_50_50_CONFIRM:
        return state, (invalid_action_event(now, EngineAction.CONFIRM_50_50.name),)
    updated = replace(
        state,
        breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
        shift_state=MixedGasShiftState.NONE,
        shift_timer=MixedGasTimer(kind=MixedGasTimerKind.SHIFT, timer=TimerState(started_at=now)),
    )
    validate_state(updated)
    current = current_stop(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "50_50", "depth_fsw": None if current is None else current.depth_fsw}),)


def confirm_on_o2(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_STOP or state.shift_state is not MixedGasShiftState.AWAITING_O2_CONFIRM:
        return state, (invalid_action_event(now, EngineAction.CONFIRM_ON_O2.name),)
    updated = replace(
        state,
        breathing_gas=MixedGasBreathingGas.OXYGEN,
        shift_state=MixedGasShiftState.NONE,
        stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        shift_timer=None,
        oxygen=replace(state.oxygen, continuous_anchor_at=now if state.oxygen.continuous_anchor_at is None else state.oxygen.continuous_anchor_at),
    )
    validate_state(updated)
    current = current_stop(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "on_o2", "depth_fsw": None if current is None else current.depth_fsw}),)


def toggle_off_o2(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_STOP or state.plan is None or state.current_stop_index is None:
        return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)
    current = current_stop(state)
    if current is None or current.gas != "o2":
        return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)

    if state.breathing_gas is MixedGasBreathingGas.OXYGEN and state.stop_timer is not None and state.shift_state is MixedGasShiftState.NONE:
        paused_timer = pause_timer(state.stop_timer, now)
        if air_break_due(state, now):
            updated = replace(
                state,
                shift_state=MixedGasShiftState.AIR_BREAK,
                stop_timer=paused_timer,
                air_break_timer=MixedGasTimer(kind=MixedGasTimerKind.AIR_BREAK, timer=TimerState(started_at=now)),
                interruption_timer=None,
            )
            validate_state(updated)
            return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "air_break_start", "depth_fsw": current.depth_fsw}),)
        updated = replace(
            state,
            shift_state=MixedGasShiftState.OFF_O2,
            stop_timer=paused_timer,
            interruption_timer=MixedGasTimer(kind=MixedGasTimerKind.SHIFT, timer=TimerState(started_at=now)),
            air_break_timer=None,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "off_o2", "depth_fsw": current.depth_fsw}),)

    if state.shift_state is MixedGasShiftState.OFF_O2 and state.stop_timer is not None:
        updated = replace(
            state,
            shift_state=MixedGasShiftState.NONE,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now, carried_elapsed_sec=state.stop_timer.timer.carried_elapsed_sec)),
            interruption_timer=None,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_o2", "depth_fsw": current.depth_fsw}),)

    if state.shift_state is MixedGasShiftState.AIR_BREAK and state.stop_timer is not None and state.air_break_timer is not None:
        if elapsed(state.air_break_timer.timer, now) < 5 * 60:
            return state, (invalid_action_event(now, "END_AIR_BREAK_TOO_EARLY"),)
        updated = replace(
            state,
            shift_state=MixedGasShiftState.NONE,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now, carried_elapsed_sec=state.stop_timer.timer.carried_elapsed_sec)),
            air_break_timer=None,
            oxygen=replace(state.oxygen, continuous_anchor_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_after_break", "depth_fsw": current.depth_fsw}),)

    return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)


def reach_surface(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.TRAVEL_TO_SURFACE:
        return state, (invalid_action_event(now, EngineAction.REACH_SURFACE.name),)
    updated = replace(
        state,
        phase=MixedGasPhase.COMPLETE,
        breathing_gas=MixedGasBreathingGas.AIR,
        shift_state=MixedGasShiftState.NONE,
        travel_timer=None,
        travel_start_depth_fsw=None,
        clean_time_timer=MixedGasTimer(kind=MixedGasTimerKind.CLEAN_TIME, timer=TimerState(started_at=now)),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now),)
