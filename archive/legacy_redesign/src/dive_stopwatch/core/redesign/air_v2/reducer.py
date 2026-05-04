from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import math

from ...air_o2_profiles import build_profile, next_stop_after, stop_by_index
from .actions import AirV2Action
from .events import AirV2Event, AirV2EventKind
from .state import AirV2GasState, AirV2Phase, AirV2Plan, AirV2State, AirV2Timer, AirV2TimerKind, make_initial_state


def reduce_action(state: AirV2State, action: AirV2Action, now: datetime) -> AirV2State:
    if action is AirV2Action.RESET:
        return make_initial_state(mode=state.mode, depth_text=state.depth_text, depth_fsw=state.depth_fsw)
    if action is AirV2Action.LEAVE_SURFACE:
        return _leave_surface(state, now)
    if action is AirV2Action.REACH_BOTTOM:
        return _reach_bottom(state, now)
    if action is AirV2Action.LEAVE_BOTTOM:
        return _leave_bottom(state, now)
    if action is AirV2Action.REACH_STOP:
        return _reach_stop(state, now)
    if action is AirV2Action.REACH_SURFACE:
        return _reach_surface(state, now)
    if action is AirV2Action.LEAVE_STOP:
        return _leave_stop(state, now)
    return _record_invalid_action(state, now, action)


def _leave_surface(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.READY:
        return _record_invalid_action(state, now, AirV2Action.LEAVE_SURFACE)
    return replace(
        state,
        phase=AirV2Phase.DESCENT,
        active_timer=AirV2Timer(kind=AirV2TimerKind.BOTTOM, started_at=now),
        events=state.events + (AirV2Event(kind=AirV2EventKind.LEFT_SURFACE, at=now),),
    )


def _reach_bottom(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.DESCENT:
        return _record_invalid_action(state, now, AirV2Action.REACH_BOTTOM)
    return replace(
        state,
        phase=AirV2Phase.BOTTOM,
        events=state.events + (AirV2Event(kind=AirV2EventKind.REACHED_BOTTOM, at=now),),
    )


def _leave_bottom(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.BOTTOM or state.active_timer is None or state.depth_fsw is None:
        return _record_invalid_action(state, now, AirV2Action.LEAVE_BOTTOM)
    bottom_elapsed_sec = max((now - state.active_timer.started_at).total_seconds(), 0.0)
    bottom_time_min = max(math.ceil(bottom_elapsed_sec / 60), 1)
    profile = build_profile(state.mode, state.depth_fsw, bottom_time_min)
    next_stop = next_stop_after(profile, None)
    return replace(
        state,
        phase=AirV2Phase.TRAVEL_TO_SURFACE if profile.is_no_decompression or next_stop is None else AirV2Phase.TRAVEL_TO_FIRST_STOP,
        active_timer=AirV2Timer(kind=AirV2TimerKind.TRAVEL, started_at=now),
        plan=AirV2Plan(profile=profile),
        events=state.events + (AirV2Event(kind=AirV2EventKind.LEFT_BOTTOM, at=now),),
    )


def _reach_stop(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.TRAVEL_TO_FIRST_STOP or state.plan is None:
        return _record_invalid_action(state, now, AirV2Action.REACH_STOP)
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
    if next_stop is None:
        return _record_invalid_action(state, now, AirV2Action.REACH_STOP)
    return replace(
        state,
        phase=AirV2Phase.AT_STOP,
        active_timer=AirV2Timer(kind=AirV2TimerKind.STOP, started_at=now),
        plan=replace(state.plan, current_stop_index=next_stop.index),
        events=state.events + (AirV2Event(kind=AirV2EventKind.REACHED_STOP, at=now, detail=str(next_stop.index)),),
    )


def _reach_surface(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.TRAVEL_TO_SURFACE:
        return _record_invalid_action(state, now, AirV2Action.REACH_SURFACE)
    return replace(
        state,
        phase=AirV2Phase.COMPLETE,
        active_timer=None,
        events=state.events + (AirV2Event(kind=AirV2EventKind.REACHED_SURFACE, at=now),),
    )


def _leave_stop(state: AirV2State, now: datetime) -> AirV2State:
    if state.phase is not AirV2Phase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return _record_invalid_action(state, now, AirV2Action.LEAVE_STOP)
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
    next_phase = AirV2Phase.TRAVEL_TO_SURFACE if next_stop is None else AirV2Phase.TRAVEL_TO_FIRST_STOP
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    detail = "" if current_stop is None else str(current_stop.index)
    return replace(
        state,
        phase=next_phase,
        active_timer=AirV2Timer(kind=AirV2TimerKind.TRAVEL, started_at=now),
        events=state.events + (AirV2Event(kind=AirV2EventKind.LEFT_STOP, at=now, detail=detail),),
    )


def _record_invalid_action(state: AirV2State, now: datetime, action: AirV2Action) -> AirV2State:
    return replace(
        state,
        events=state.events + (
            AirV2Event(kind=AirV2EventKind.INVALID_ACTION, at=now, detail=action.name),
        ),
    )
