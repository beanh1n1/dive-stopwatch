from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....domain.air_o2_profiles import convert_remaining_o2_to_air, stop_by_index
from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState
from ..rules import air_break_due, current_stop_remaining_sec, elapsed, pause_timer
from ..invariants import validate_state
from ..state import AirGasState, AirOxygenState, AirPhase, AirPlan, AirState, AirTimer, AirTimerKind


def confirm_on_o2(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.AT_STOP or state.gas_state is not AirGasState.WAITING_ON_O2:
        return state, (invalid_action_event(now, EngineAction.CONFIRM_ON_O2.name),)
    updated = replace(
        state,
        gas_state=AirGasState.ON_O2,
        tsv_timer=None,
        stop_timer=AirTimer(kind=AirTimerKind.STOP, timer=TimerState(started_at=now)),
        oxygen=replace(
            state.oxygen,
            first_confirmed_at=now if state.oxygen.first_confirmed_at is None else state.oxygen.first_confirmed_at,
            continuous_anchor_at=now if state.oxygen.continuous_anchor_at is None else state.oxygen.continuous_anchor_at,
        ),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "on_o2"}),)


def toggle_off_o2(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or current_stop.gas != "o2":
        return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)

    if state.gas_state is AirGasState.ON_O2 and state.stop_timer is not None:
        paused_timer = pause_timer(state.stop_timer, now)
        if air_break_due(state, now):
            updated = replace(
                state,
                gas_state=AirGasState.AIR_BREAK,
                stop_timer=paused_timer,
                air_break_timer=AirTimer(kind=AirTimerKind.AIR_BREAK, timer=TimerState(started_at=now)),
                interruption_timer=None,
                oxygen=state.oxygen,
            )
            validate_state(updated)
            return updated, (
                AuditEvent(
                    kind=AuditEventKind.GAS_INTERRUPTED,
                    at=now,
                    payload={"kind": "air_break_start", "stop_index": current_stop.index, "depth_fsw": current_stop.depth_fsw},
                ),
            )

        updated = replace(
            state,
            gas_state=AirGasState.INTERRUPTED_O2,
            stop_timer=paused_timer,
            interruption_timer=AirTimer(kind=AirTimerKind.INTERRUPTION, timer=TimerState(started_at=now)),
            air_break_timer=None,
            oxygen=state.oxygen,
        )
        validate_state(updated)
        return updated, (
            AuditEvent(
                kind=AuditEventKind.GAS_INTERRUPTED,
                at=now,
                payload={"kind": "off_o2", "stop_index": current_stop.index, "depth_fsw": current_stop.depth_fsw},
            ),
        )

    if state.gas_state is AirGasState.INTERRUPTED_O2 and state.stop_timer is not None:
        updated = replace(
            state,
            gas_state=AirGasState.ON_O2,
            stop_timer=AirTimer(kind=AirTimerKind.STOP, timer=TimerState(started_at=now, carried_elapsed_sec=state.stop_timer.timer.carried_elapsed_sec)),
            interruption_timer=None,
            oxygen=state.oxygen,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_o2"}),)

    if state.gas_state is AirGasState.AIR_BREAK and state.stop_timer is not None and state.air_break_timer is not None:
        if elapsed(state.air_break_timer, now) < 5 * 60:
            return state, (invalid_action_event(now, "END_AIR_BREAK_TOO_EARLY"),)
        updated = replace(
            state,
            gas_state=AirGasState.ON_O2,
            stop_timer=AirTimer(kind=AirTimerKind.STOP, timer=TimerState(started_at=now, carried_elapsed_sec=state.stop_timer.timer.carried_elapsed_sec)),
            air_break_timer=None,
            oxygen=replace(state.oxygen, continuous_anchor_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_after_break"}),)

    return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)


def convert_to_air(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return state, (invalid_action_event(now, EngineAction.CONVERT_TO_AIR.name),)
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or current_stop.gas != "o2":
        return state, (invalid_action_event(now, EngineAction.CONVERT_TO_AIR.name),)
    remaining_sec = current_stop_remaining_sec(state, now)
    if remaining_sec is None:
        return state, (invalid_action_event(now, EngineAction.CONVERT_TO_AIR.name),)
    result = convert_remaining_o2_to_air(
        state.plan.profile,
        current_stop_index=current_stop.index,
        remaining_o2_stop_sec=int(round(remaining_sec)),
    )
    updated = replace(
        state,
        gas_state=AirGasState.AIR,
        plan=AirPlan(profile=result.profile, current_stop_index=result.converted_stop_index),
        stop_timer=AirTimer(kind=AirTimerKind.STOP, timer=TimerState(started_at=now)),
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
        oxygen=AirOxygenState(),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"conversion": "to_air", "converted_stop_index": result.converted_stop_index}),)
