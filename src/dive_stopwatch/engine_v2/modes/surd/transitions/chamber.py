from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState
from ..rules import SURD_AIR_BREAK_SEC, SURD_CLEAN_TIME_SEC, air_break_due, current_segment, elapsed, next_segment, pause, resume
from ..invariants import validate_state
from ..state import SurdPhase, SurdState, make_initial_state


def confirm_on_o2(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.CHAMBER_AT_50_WAITING_O2:
        return state, (invalid_action_event(now, EngineAction.CONFIRM_ON_O2.name),)
    updated = replace(
        state,
        phase=SurdPhase.CHAMBER_ON_O2,
        move_ready_timer=None,
        o2_timer=TimerState(started_at=now),
        continuous_o2_anchor_at=now if state.continuous_o2_anchor_at is None else state.continuous_o2_anchor_at,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "on_o2"}),)


def toggle_off_o2(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is SurdPhase.CHAMBER_ON_O2 and state.o2_timer is not None:
        if air_break_due(state, now):
            updated = replace(
                state,
                phase=SurdPhase.CHAMBER_AIR_BREAK,
                o2_timer=pause(state.o2_timer, now),
                air_break_timer=TimerState(started_at=now),
                off_o2_timer=None,
            )
            validate_state(updated)
            return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "air_break_start"}),)
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_OFF_O2,
            o2_timer=pause(state.o2_timer, now),
            off_o2_timer=TimerState(started_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "off_o2"}),)
    if state.phase is SurdPhase.CHAMBER_OFF_O2 and state.o2_timer is not None:
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_ON_O2,
            o2_timer=resume(state.o2_timer, now),
            off_o2_timer=None,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_o2"}),)
    return state, (invalid_action_event(now, EngineAction.TOGGLE_OFF_O2.name),)


def move_chamber(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    next_seg = next_segment(state)
    if next_seg is None:
        return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)

    if state.phase is SurdPhase.CHAMBER_ON_O2:
        seg = current_segment(state)
        if seg is None or seg.period_number != next_seg.period_number:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        if state.o2_timer is None or elapsed(state.o2_timer, now) < seg.duration_sec:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        if air_break_due(state, now):
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_TRAVEL_TO_STOP,
            current_segment_index=next_seg.segment_index,
            chamber_travel_timer=TimerState(started_at=now),
            chamber_travel_from_depth_fsw=seg.depth_fsw,
            o2_timer=TimerState(started_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": seg.depth_fsw, "next_depth_fsw": next_seg.depth_fsw}),)

    if state.phase is SurdPhase.CHAMBER_READY_TO_MOVE:
        seg = current_segment(state)
        if seg is None:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_TRAVEL_TO_STOP,
            current_segment_index=next_seg.segment_index,
            chamber_travel_timer=TimerState(started_at=now),
            chamber_travel_from_depth_fsw=seg.depth_fsw,
            move_ready_timer=None,
            o2_timer=TimerState(started_at=now),
            continuous_o2_anchor_at=now,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": seg.depth_fsw, "next_depth_fsw": next_seg.depth_fsw}),)

    if state.phase is SurdPhase.CHAMBER_OFF_O2:
        seg = current_segment(state)
        if seg is None or state.o2_timer is None:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        if elapsed(state.o2_timer, now) < seg.duration_sec:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        if air_break_due(state, now):
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_TRAVEL_TO_STOP,
            current_segment_index=next_seg.segment_index,
            chamber_travel_timer=TimerState(started_at=now),
            chamber_travel_from_depth_fsw=seg.depth_fsw,
            off_o2_timer=None,
            o2_timer=TimerState(started_at=now),
            continuous_o2_anchor_at=now,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": seg.depth_fsw, "next_depth_fsw": next_seg.depth_fsw}),)

    if state.phase is SurdPhase.CHAMBER_AIR_BREAK:
        seg = current_segment(state)
        if seg is None or state.air_break_timer is None:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        if next_seg.depth_fsw == seg.depth_fsw:
            return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_TRAVEL_TO_STOP,
            current_segment_index=next_seg.segment_index,
            chamber_travel_timer=TimerState(started_at=now),
            chamber_travel_from_depth_fsw=seg.depth_fsw,
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": seg.depth_fsw, "next_depth_fsw": next_seg.depth_fsw}),)

    return state, (invalid_action_event(now, EngineAction.MOVE_CHAMBER.name),)


def reach_stop(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.CHAMBER_TRAVEL_TO_STOP:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    seg = current_segment(state)
    if seg is None:
        return state, (invalid_action_event(now, EngineAction.REACH_STOP.name),)
    next_phase = SurdPhase.CHAMBER_AIR_BREAK if state.air_break_timer is not None else SurdPhase.CHAMBER_ON_O2
    updated = replace(
        state,
        phase=next_phase,
        chamber_travel_timer=None,
        chamber_travel_from_depth_fsw=None,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"chamber_depth_fsw": seg.depth_fsw}),)


def start_air_break(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.CHAMBER_ON_O2:
        return state, (invalid_action_event(now, EngineAction.START_AIR_BREAK.name),)
    seg = current_segment(state)
    next_seg = next_segment(state)
    if seg is None or state.o2_timer is None or next_seg is None or not air_break_due(state, now):
        return state, (invalid_action_event(now, EngineAction.START_AIR_BREAK.name),)
    updated = replace(
        state,
        phase=SurdPhase.CHAMBER_AIR_BREAK,
        o2_timer=pause(state.o2_timer, now),
        air_break_timer=TimerState(started_at=now),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.GAS_INTERRUPTED, at=now, payload={"kind": "air_break_start"}),)


def end_air_break(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase is not SurdPhase.CHAMBER_AIR_BREAK or state.air_break_timer is None:
        return state, (invalid_action_event(now, EngineAction.END_AIR_BREAK.name),)
    if elapsed(state.air_break_timer, now) < SURD_AIR_BREAK_SEC:
        return state, (invalid_action_event(now, "END_AIR_BREAK_TOO_EARLY"),)
    seg = current_segment(state)
    next_seg = next_segment(state)
    if seg is not None and next_seg is not None and next_seg.depth_fsw != seg.depth_fsw:
        updated = replace(
            state,
            phase=SurdPhase.CHAMBER_READY_TO_MOVE,
            air_break_timer=None,
            move_ready_timer=TimerState(started_at=now),
        )
        validate_state(updated)
        return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_after_break"}),)
    new_index = state.current_segment_index if next_seg is None or seg is None else (
        next_seg.segment_index if (seg.period_number != next_seg.period_number and seg.depth_fsw == next_seg.depth_fsw) else state.current_segment_index
    )
    updated = replace(
        state,
        phase=SurdPhase.CHAMBER_ON_O2,
        current_segment_index=new_index,
        air_break_timer=None,
        move_ready_timer=None,
        o2_timer=TimerState(started_at=now),
        continuous_o2_anchor_at=now,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.REACHED_STOP, at=now, payload={"confirmation": "resume_after_break"}),)


def complete_to_surface(state: SurdState, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if state.phase not in {SurdPhase.CHAMBER_ON_O2, SurdPhase.CHAMBER_OFF_O2}:
        return state, (invalid_action_event(now, "COMPLETE_TO_SURFACE"),)
    seg = current_segment(state)
    if seg is None or state.o2_timer is None or next_segment(state) is not None:
        return state, (invalid_action_event(now, "COMPLETE_TO_SURFACE"),)
    if elapsed(state.o2_timer, now) < seg.duration_sec:
        return state, (invalid_action_event(now, "COMPLETE_TO_SURFACE"),)
    updated = replace(
        state,
        phase=SurdPhase.CHAMBER_TRAVEL_TO_SURFACE,
        off_o2_timer=None,
        air_break_timer=None,
        chamber_surface_ascent_timer=TimerState(started_at=now),
        chamber_surface_ascent_from_depth_fsw=seg.depth_fsw,
        chamber_surface_ascent_on_o2=state.phase is SurdPhase.CHAMBER_ON_O2,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": seg.depth_fsw, "next_depth_fsw": 0}),)


def maybe_finish_clean_time(state: SurdState, now: datetime) -> SurdState:
    if state.phase is not SurdPhase.COMPLETE_CLEAN_TIME or state.clean_time_timer is None:
        return state
    if elapsed(state.clean_time_timer, now) < SURD_CLEAN_TIME_SEC:
        return state
    return make_initial_state()
