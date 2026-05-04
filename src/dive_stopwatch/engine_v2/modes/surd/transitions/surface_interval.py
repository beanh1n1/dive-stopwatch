from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState, elapsed
from ...mixed_gas.plan import mixed_gas_chamber_o2_half_periods
from ..rules import surface_interval_penalty_kind
from ..invariants import validate_state
from ..plan import build_surd_chamber_plan, build_surd_chamber_plan_from_half_periods
from ..state import SurdPhase, SurdState


def reach_surface(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP:
        updated = replace(
            state,
            phase=SurdPhase.SURFACE_UNDRESS,
            surface_ascent_timer=None,
            undress_timer=TimerState(started_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now),)
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE:
        updated = replace(
            state,
            phase=SurdPhase.COMPLETE_CLEAN_TIME,
            chamber_surface_ascent_timer=None,
            chamber_surface_ascent_from_depth_fsw=None,
            chamber_surface_ascent_on_o2=None,
            o2_timer=None,
            clean_time_timer=TimerState(started_at=now),
            current_segment_index=None,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now, payload={"completion": "to_surface"}),)
    updated = replace(
        state,
    )
    return updated, (invalid_action_event(now, EngineAction.REACH_SURFACE.name),)


def leave_surface(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.SURFACE_UNDRESS:
        return state, (invalid_action_event(now, EngineAction.LEAVE_SURFACE.name),)
    updated = replace(
        state,
        phase=SurdPhase.SURFACE_TO_CHAMBER_50,
        undress_timer=None,
        to_chamber_timer=TimerState(started_at=now),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_SURFACE, at=now),)


def reach_chamber_50(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.SURFACE_TO_CHAMBER_50 or state.handoff is None or state.surface_interval_timer is None:
        return state, (invalid_action_event(now, EngineAction.REACH_CHAMBER_50.name),)
    penalty_kind = surface_interval_penalty_kind(elapsed(state.surface_interval_timer, now))
    if penalty_kind.name == "EXCEEDED":
        updated = replace(
            state,
            phase=SurdPhase.SURFACE_INTERVAL_EXCEEDED,
            penalty_kind=penalty_kind,
            to_chamber_timer=None,
            chamber_plan=None,
            current_segment_index=None,
        )
        validate_state(updated)
        return updated, (
            AuditEvent(
                kind=AuditEventKind.REACHED_STOP,
                at=now,
                payload={"chamber_depth_fsw": 50, "penalty_kind": penalty_kind.name, "requires_treatment": True},
            ),
        )
    if state.handoff.source_mode == "MIXED_GAS":
        chamber_plan = build_surd_chamber_plan_from_half_periods(
            chamber_o2_half_periods=mixed_gas_chamber_o2_half_periods(
                depth_fsw=(
                    state.handoff.source_table_depth_fsw
                    if state.handoff.source_table_depth_fsw is not None
                    else state.handoff.input_depth_fsw
                ),
                bottom_time_min=(
                    state.handoff.source_table_bottom_time_min
                    if state.handoff.source_table_bottom_time_min is not None
                    else state.handoff.input_bottom_time_min
                ),
            ),
            penalty_kind=penalty_kind,
        )
    else:
        chamber_plan = build_surd_chamber_plan(
            input_depth_fsw=(
                state.handoff.source_table_depth_fsw
                if state.handoff.source_table_depth_fsw is not None
                else state.handoff.input_depth_fsw
            ),
            input_bottom_time_min=(
                state.handoff.source_table_bottom_time_min
                if state.handoff.source_table_bottom_time_min is not None
                else state.handoff.input_bottom_time_min
            ),
            penalty_kind=penalty_kind,
        )
    updated = replace(
        state,
        phase=SurdPhase.CHAMBER_AT_50_WAITING_O2,
        penalty_kind=penalty_kind,
        to_chamber_timer=None,
        chamber_plan=chamber_plan,
        current_segment_index=0 if chamber_plan.segments else None,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"chamber_depth_fsw": 50, "penalty_kind": penalty_kind.name}),)
