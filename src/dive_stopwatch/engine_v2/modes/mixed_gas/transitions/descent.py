from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState
from ..invariants import validate_state
from ..plan import build_mixed_gas_plan
from ..rules import MIXED_GAS_20_FSW_GRACE_SEC, can_begin_descent, grace_anchor, planned_bottom_anchor_for_departure, requires_20fsw_air_descent
from ..state import (
    MixedGasBreathingGas,
    MixedGasPhase,
    MixedGasShiftState,
    MixedGasState,
    MixedGasTimer,
    MixedGasTimerKind,
)


def leave_surface(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.READY or not can_begin_descent(state):
        return state, (invalid_action_event(now, EngineAction.LEAVE_SURFACE.name),)
    if requires_20fsw_air_descent(state):
        updated = replace(
            state,
            phase=MixedGasPhase.DESCENT_TO_20_ON_AIR,
            breathing_gas=MixedGasBreathingGas.AIR,
            surface_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
            travel_start_depth_fsw=0,
            grace_window_timer=MixedGasTimer(kind=MixedGasTimerKind.GRACE_WINDOW, timer=TimerState(started_at=now)),
        )
    else:
        updated = replace(
            state,
            phase=MixedGasPhase.DESCENT_TO_BOTTOM,
            breathing_gas=MixedGasBreathingGas.BOTTOM_MIX,
            surface_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
            travel_start_depth_fsw=0,
        )
    validate_state(updated)
    return updated, (
        AuditEvent(
            kind=AuditEventKind.LEFT_SURFACE,
            at=now,
            payload={"gas": updated.breathing_gas.name.lower(), "bottom_mix_o2_percent": state.bottom_mix_o2_percent},
        ),
    )


def reach_prebottom_twenty(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.DESCENT_TO_20_ON_AIR:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    updated = replace(
        state,
        phase=MixedGasPhase.AT_20_PREBOTTOM_SHIFT,
        shift_state=MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"depth_fsw": 20, "gas": "air"}),)


def confirm_bottom_mix(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_20_PREBOTTOM_SHIFT or state.shift_state not in {
        MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM,
        MixedGasShiftState.ABORT_READY_ON_AIR,
    }:
        return state, (invalid_action_event(now, EngineAction.CONFIRM_BOTTOM_MIX.name),)
    updated = replace(
        state,
        breathing_gas=MixedGasBreathingGas.BOTTOM_MIX,
        shift_state=MixedGasShiftState.NONE,
        grace_window_timer=state.grace_window_timer,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "bottom_mix", "depth_fsw": 20}),)


def convert_to_air(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_20_PREBOTTOM_SHIFT or state.shift_state is not MixedGasShiftState.NONE:
        return state, (invalid_action_event(now, EngineAction.CONVERT_TO_AIR.name),)
    updated = replace(
        state,
        breathing_gas=MixedGasBreathingGas.AIR,
        shift_state=MixedGasShiftState.ABORT_READY_ON_AIR,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "shift_to_air_abort", "depth_fsw": 20}),)


def leave_twenty(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.AT_20_PREBOTTOM_SHIFT:
        return state, (invalid_action_event(now, EngineAction.LEAVE_STOP.name),)
    breathing_gas = state.breathing_gas
    grace_window_timer = state.grace_window_timer
    if breathing_gas is not MixedGasBreathingGas.BOTTOM_MIX:
        breathing_gas = MixedGasBreathingGas.BOTTOM_MIX
        if requires_20fsw_air_descent(state) and grace_window_timer is None:
            grace_window_timer = MixedGasTimer(kind=MixedGasTimerKind.GRACE_WINDOW, timer=TimerState(started_at=now))
    anchor_at = planned_bottom_anchor_for_departure(state, now) if requires_20fsw_air_descent(state) else None
    updated = replace(
        state,
        phase=MixedGasPhase.DESCENT_TO_BOTTOM,
        breathing_gas=breathing_gas,
        shift_state=MixedGasShiftState.NONE,
        grace_window_timer=grace_window_timer,
        travel_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        travel_start_depth_fsw=20,
        pending_bottom_anchor_at=anchor_at,
    )
    validate_state(updated)
    payload = {"depth_fsw": 20, "gas": "bottom_mix"}
    grace_start = grace_anchor(state)
    if anchor_at is not None and grace_start is not None:
        payload["bottom_time_anchor"] = "grace_5_min" if anchor_at == grace_start + timedelta(seconds=MIXED_GAS_20_FSW_GRACE_SEC) else "leave_20"
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload=payload),)


def reach_bottom(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is not MixedGasPhase.DESCENT_TO_BOTTOM:
        return state, (invalid_action_event(now, EngineAction.REACH_BOTTOM.name),)
    if state.pending_bottom_anchor_at is not None:
        anchor = state.pending_bottom_anchor_at
    elif state.surface_timer is not None:
        anchor = state.surface_timer.timer.started_at
    else:
        anchor = now
    updated = replace(
        state,
        phase=MixedGasPhase.BOTTOM,
        bottom_timer=MixedGasTimer(kind=MixedGasTimerKind.BOTTOM, timer=TimerState(started_at=anchor)),
        surface_timer=None,
        travel_timer=None,
        travel_start_depth_fsw=None,
        grace_window_timer=None,
        pending_bottom_anchor_at=None,
        active_hold_started_at=None,
        hold_elapsed_sec=0.0,
        hold_index=0,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_BOTTOM, at=now, payload={"gas": updated.breathing_gas.name.lower()}),)


def leave_bottom(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT and state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR:
        updated = replace(
            state,
            phase=MixedGasPhase.TRAVEL_TO_SURFACE,
            travel_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
            travel_start_depth_fsw=20,
            shift_state=MixedGasShiftState.ABORT_READY_ON_AIR,
            grace_window_timer=None,
            pending_bottom_anchor_at=None,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_BOTTOM, at=now, payload={"depth_fsw": 20, "abort_prebottom": True, "gas": "air"}),)
    if state.phase is not MixedGasPhase.BOTTOM or state.bottom_timer is None or state.depth_fsw is None:
        return state, (invalid_action_event(now, EngineAction.LEAVE_BOTTOM.name),)
    bottom_elapsed_min = max(int(((now - state.bottom_timer.timer.started_at).total_seconds() + 59.999) // 60), 0)
    plan = state.plan or build_mixed_gas_plan(
        depth_fsw=state.depth_fsw,
        bottom_time_min=bottom_elapsed_min,
        bottom_mix_o2_percent=state.bottom_mix_o2_percent,
    )
    if plan is None:
        return state, (invalid_action_event(now, EngineAction.LEAVE_BOTTOM.name),)
    updated = replace(
        state,
        phase=MixedGasPhase.TRAVEL_TO_SURFACE if plan.is_no_decompression or not plan.stops else MixedGasPhase.TRAVEL_TO_FIRST_STOP,
        plan=plan,
        current_stop_index=None,
        bottom_timer=None,
        travel_timer=MixedGasTimer(kind=MixedGasTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        travel_start_depth_fsw=state.depth_fsw,
        shift_state=(
            MixedGasShiftState.AWAITING_50_50_CONFIRM
            if state.depth_fsw > 90 and plan.stops and plan.stops[0].depth_fsw < 90 and not any(stop.depth_fsw == 90 for stop in plan.stops)
            else MixedGasShiftState.NONE
        ),
    )
    validate_state(updated)
    payload = {"depth_fsw": state.depth_fsw, "input_bottom_time_min": bottom_elapsed_min}
    if plan.table_depth_fsw is not None:
        payload["table_depth_fsw"] = plan.table_depth_fsw
    if plan.table_bottom_time_min is not None:
        payload["table_bottom_time_min"] = plan.table_bottom_time_min
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_BOTTOM, at=now, payload=payload),)
