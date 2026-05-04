from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....domain.air_o2_profiles import apply_delay
from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ..invariants import validate_state
from ..state import AirDelayState, AirDelayStatus, AirOxygenState, AirPhase, AirPlan, AirState
from ..rules import estimated_travel_depth, table_schedule_label


def start_delay(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase not in {AirPhase.TRAVEL_TO_FIRST_STOP, AirPhase.TRAVEL_TO_SURFACE} or state.delay.status is AirDelayStatus.ACTIVE:
        return state, (invalid_action_event(now, EngineAction.START_DELAY.name),)
    updated = replace(
        state,
        delay=AirDelayState(
            status=AirDelayStatus.ACTIVE,
            started_at=now,
            depth_fsw=estimated_travel_depth(state, now),
            paused_travel_sec=state.delay.paused_travel_sec,
        ),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.DELAY_STARTED, at=now, payload={"depth_fsw": updated.delay.depth_fsw}),)


def end_delay(state: AirState, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if state.phase not in {AirPhase.TRAVEL_TO_FIRST_STOP, AirPhase.TRAVEL_TO_SURFACE} or state.delay.status is not AirDelayStatus.ACTIVE or state.plan is None or state.delay.started_at is None or state.delay.depth_fsw is None:
        return state, (invalid_action_event(now, EngineAction.END_DELAY.name),)
    delay_elapsed_sec = max(int(round((now - state.delay.started_at).total_seconds())), 0)
    o2_time_before_delay_sec = None
    if state.oxygen.continuous_anchor_at is not None:
        o2_time_before_delay_sec = max(int(round((state.delay.started_at - state.oxygen.continuous_anchor_at).total_seconds())), 0)
    result = apply_delay(
        state.plan.profile,
        from_stop_index=state.plan.current_stop_index,
        delay_elapsed_sec=delay_elapsed_sec,
        delay_depth_fsw=state.delay.depth_fsw,
        o2_time_before_delay_sec=o2_time_before_delay_sec,
    )
    updated = replace(
        state,
        plan=AirPlan(profile=result.profile, current_stop_index=state.plan.current_stop_index),
        travel_timer=state.travel_timer,
        delay=AirDelayState(
            status=AirDelayStatus.RESOLVED,
            outcome=result.outcome,
            paused_travel_sec=state.delay.paused_travel_sec + delay_elapsed_sec,
        ),
        oxygen=replace(state.oxygen, continuous_anchor_at=now if result.air_interruption_min > 0 and result.outcome.value.startswith("o2_") else state.oxygen.continuous_anchor_at),
    )
    validate_state(updated)
    return updated, (
        AuditEvent(
            kind=AuditEventKind.DELAY_RESOLVED,
            at=now,
            payload={
                "outcome": result.outcome.value,
                "delay_status": updated.delay.status.name,
                "delay_depth_fsw": state.delay.depth_fsw,
                "delay_min": result.delay_min,
                "previous_schedule": table_schedule_label(state.plan.profile),
                "updated_schedule": table_schedule_label(result.profile),
                "air_interruption_min": result.air_interruption_min,
                "credited_o2_min": result.credited_o2_min,
            },
        ),
    )
