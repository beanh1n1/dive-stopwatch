from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....domain.air_o2_profiles import stop_by_index
from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState
from ..rules import can_leave_stop, elapsed, next_required_stop, table_schedule_label
from ..invariants import validate_state
from ..plan import build_air_plan
from ..state import AirDelayState, AirGasState, AirOxygenState, AirPhase, AirPlan, AirState, AirTimer, AirTimerKind


def leave_surface(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.READY:
        return state, (invalid_action_event(now, EngineAction.LEAVE_SURFACE.name),)
    updated = replace(
        state,
        phase=AirPhase.DESCENT,
        surface_timer=AirTimer(kind=AirTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        active_hold_started_at=None,
        hold_elapsed_sec=0.0,
        hold_index=0,
        bottom_timer=None,
        travel_timer=None,
        stop_timer=None,
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_SURFACE, at=now),)


def reach_bottom(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.DESCENT:
        return state, (invalid_action_event(now, EngineAction.REACH_BOTTOM.name),)
    updated = replace(
        state,
        phase=AirPhase.BOTTOM,
        bottom_timer=AirTimer(kind=AirTimerKind.BOTTOM, timer=TimerState(started_at=now)),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_BOTTOM, at=now),)


def leave_bottom(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.BOTTOM or state.bottom_timer is None or state.depth_fsw is None:
        return state, (invalid_action_event(now, EngineAction.LEAVE_BOTTOM.name),)
    in_water_elapsed_sec = elapsed(state.surface_timer if state.surface_timer is not None else state.bottom_timer, now)
    profile = build_air_plan(mode=state.mode, depth_fsw=state.depth_fsw, bottom_elapsed_sec=in_water_elapsed_sec)
    next_stop = next_required_stop(profile, None)
    updated = replace(
        state,
        phase=AirPhase.TRAVEL_TO_SURFACE if profile.is_no_decompression or next_stop is None else AirPhase.TRAVEL_TO_FIRST_STOP,
        travel_timer=AirTimer(kind=AirTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        bottom_timer=state.bottom_timer,
        stop_timer=None,
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
        plan=AirPlan(profile=profile),
        gas_state=AirGasState.AIR,
        oxygen=AirOxygenState(),
        delay=AirDelayState(),
    )
    validate_state(updated)
    return updated, (
        AuditEvent(
            kind=AuditEventKind.LEFT_BOTTOM,
            at=now,
            payload={
                "depth_fsw": state.depth_fsw,
                "table_schedule": table_schedule_label(profile),
            },
        ),
    )


def reach_stop(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.TRAVEL_TO_FIRST_STOP or state.plan is None:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    next_stop = next_required_stop(state.plan.profile, state.plan.current_stop_index)
    if next_stop is None:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)

    previous_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index) if state.plan.current_stop_index is not None else None
    carried_travel_sec = elapsed(state.travel_timer, now)

    if next_stop.gas == "o2" and state.oxygen.first_confirmed_at is None:
        tsv_started_at = now if previous_stop is None else (state.travel_timer.timer.started_at if state.travel_timer is not None else now)
        updated = replace(
            state,
            phase=AirPhase.AT_STOP,
            gas_state=AirGasState.WAITING_ON_O2,
            travel_timer=None,
            stop_timer=None,
            tsv_timer=AirTimer(kind=AirTimerKind.TSV, timer=TimerState(started_at=tsv_started_at)),
            interruption_timer=None,
            air_break_timer=None,
            plan=replace(state.plan, current_stop_index=next_stop.index),
        )
        validate_state(updated)
        return updated, (
            AuditEvent(
                kind=AuditEventKind.REACHED_STOP,
                at=now,
                payload={"stop_index": next_stop.index, "depth_fsw": next_stop.depth_fsw, "gas": "o2_waiting"},
            ),
        )

    updated = replace(
        state,
        phase=AirPhase.AT_STOP,
        gas_state=AirGasState.ON_O2 if next_stop.gas == "o2" and state.gas_state is AirGasState.ON_O2 else AirGasState.AIR,
        travel_timer=None,
        stop_timer=AirTimer(
            kind=AirTimerKind.STOP,
            timer=TimerState(started_at=now, carried_elapsed_sec=carried_travel_sec if previous_stop is not None else 0.0),
        ),
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
        plan=replace(state.plan, current_stop_index=next_stop.index),
    )
    validate_state(updated)
    return updated, (
        AuditEvent(
            kind=AuditEventKind.REACHED_STOP,
            at=now,
            payload={"stop_index": next_stop.index, "depth_fsw": next_stop.depth_fsw, "gas": next_stop.gas},
        ),
    )


def leave_stop(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None or not can_leave_stop(state, now):
        return state, (invalid_action_event(now, EngineAction.LEAVE_STOP.name),)
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    next_stop = next_required_stop(state.plan.profile, state.plan.current_stop_index)
    updated = replace(
        state,
        phase=AirPhase.TRAVEL_TO_SURFACE if next_stop is None else AirPhase.TRAVEL_TO_FIRST_STOP,
        travel_timer=AirTimer(kind=AirTimerKind.TRAVEL, timer=TimerState(started_at=now)),
        stop_timer=None,
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
        delay=AirDelayState(),
    )
    validate_state(updated)
    payload = {} if current_stop is None else {"stop_index": current_stop.index, "depth_fsw": current_stop.depth_fsw}
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload=payload),)


def reach_surface(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase is not AirPhase.TRAVEL_TO_SURFACE:
        return state, (invalid_action_event(now, EngineAction.REACH_SURFACE.name),)
    updated = replace(
        state,
        phase=AirPhase.COMPLETE,
        surface_timer=None,
        active_hold_started_at=None,
        travel_timer=None,
        stop_timer=None,
        tsv_timer=None,
        interruption_timer=None,
        air_break_timer=None,
        clean_time_timer=AirTimer(kind=AirTimerKind.CLEAN_TIME, timer=TimerState(started_at=now)),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now),)
