from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ....contracts.timers import TimerState
from ..invariants import validate_state
from ..plan import build_mixed_gas_plan
from ..rules import current_stop, next_stop
from ..state import (
    MixedGasDelayState,
    MixedGasDelayStatus,
    MixedGasPhase,
    MixedGasPlan,
    MixedGasState,
    MixedGasStop,
    MixedGasTimer,
    MixedGasTimerKind,
)


def start_delay(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.delay.status is MixedGasDelayStatus.ACTIVE:
        return state, (invalid_action_event(now, EngineAction.START_DELAY.name),)
    depth_fsw = _delay_depth_fsw(state, now)
    if depth_fsw is None:
        return state, (invalid_action_event(now, EngineAction.START_DELAY.name),)
    updated = replace(
        state,
        delay=MixedGasDelayState(
            status=MixedGasDelayStatus.ACTIVE,
            started_at=now,
            depth_fsw=depth_fsw,
            paused_travel_sec=state.delay.paused_travel_sec,
        ),
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.DELAY_STARTED, at=now, payload={"depth_fsw": depth_fsw}),)


def end_delay(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.delay.status is not MixedGasDelayStatus.ACTIVE or state.delay.started_at is None or state.delay.depth_fsw is None:
        return state, (invalid_action_event(now, EngineAction.END_DELAY.name),)

    delay_elapsed_sec = max(int(round((now - state.delay.started_at).total_seconds())), 0)
    delay_min = _rounded_delay_min(delay_elapsed_sec)
    branch = "ignore_lt_1_min"

    if state.phase is MixedGasPhase.TRAVEL_TO_FIRST_STOP:
        if delay_min > 0:
            branch = "first_stop_add_to_bottom_time"
            updated = _recompute_from_delay(state, now=now, delay_min=delay_min, delay_depth_fsw=state.delay.depth_fsw, branch=branch)
        else:
            updated = _resume_travel_from_delay_depth(state, now, branch=branch)
    elif state.phase is MixedGasPhase.TRAVEL_TO_SURFACE:
        branch = "surface_resume_normal"
        updated = _resume_travel_from_delay_depth(state, now, branch=branch)
    elif state.phase is MixedGasPhase.AT_STOP:
        current = current_stop(state)
        if current is None:
            return state, (invalid_action_event(now, EngineAction.END_DELAY.name),)
        if current.depth_fsw == 30 and delay_min > 0:
            branch = "leave_30_subtract_from_20"
            updated = _subtract_from_twenty_stop(state, delay_min=delay_min, branch=branch)
        elif current.depth_fsw > 90 and delay_min > 0:
            branch = "deep_stop_add_to_bottom_time"
            updated = _recompute_from_delay(state, now=now, delay_min=delay_min, delay_depth_fsw=current.depth_fsw, branch=branch)
        else:
            branch = "shallow_stop_resume_normal"
            updated = replace(state, delay=MixedGasDelayState(status=MixedGasDelayStatus.RESOLVED, branch=branch))
    else:
        return state, (invalid_action_event(now, EngineAction.END_DELAY.name),)

    validate_state(updated)
    payload = {
        "branch": branch,
        "delay_depth_fsw": state.delay.depth_fsw,
        "delay_min": delay_min,
    }
    if state.plan is not None:
        payload["previous_schedule"] = _schedule_label(state.plan)
        payload["previous_table_depth_fsw"] = state.plan.table_depth_fsw
        payload["previous_table_bottom_time_min"] = state.plan.table_bottom_time_min
    if updated.plan is not None:
        payload["updated_schedule"] = _schedule_label(updated.plan)
        payload["updated_table_depth_fsw"] = updated.plan.table_depth_fsw
        payload["updated_table_bottom_time_min"] = updated.plan.table_bottom_time_min
    return updated, (AuditEvent(kind=AuditEventKind.DELAY_RESOLVED, at=now, payload=payload),)


def _delay_depth_fsw(state: MixedGasState, now: datetime) -> int | None:
    if state.phase is MixedGasPhase.AT_STOP:
        current = current_stop(state)
        return None if current is None else current.depth_fsw
    if state.phase in {MixedGasPhase.TRAVEL_TO_FIRST_STOP, MixedGasPhase.TRAVEL_TO_SURFACE}:
        return _travel_depth_fsw(state, now)
    return None


def _travel_depth_fsw(state: MixedGasState, now: datetime) -> int | None:
    if state.travel_timer is None:
        return state.travel_start_depth_fsw or state.depth_fsw
    start_depth = state.travel_start_depth_fsw
    if start_depth is None:
        previous = current_stop(state)
        start_depth = state.depth_fsw if previous is None else previous.depth_fsw
    if start_depth is None:
        return state.depth_fsw
    upcoming = next_stop(state.plan, state.current_stop_index)
    end_depth = 0 if state.phase is MixedGasPhase.TRAVEL_TO_SURFACE or upcoming is None else upcoming.depth_fsw
    traveled_fsw = max((now - state.travel_timer.timer.started_at).total_seconds(), 0.0) * 0.5
    if start_depth >= end_depth:
        return max(int(round(start_depth - traveled_fsw)), end_depth)
    return min(int(round(start_depth + traveled_fsw)), end_depth)


def _rounded_delay_min(delay_elapsed_sec: int) -> int:
    if delay_elapsed_sec <= 60:
        return 0
    return (delay_elapsed_sec + 59) // 60


def _resume_travel_from_delay_depth(state: MixedGasState, now: datetime, *, branch: str) -> MixedGasState:
    return replace(
        state,
        delay=MixedGasDelayState(
            status=MixedGasDelayStatus.RESOLVED,
            branch=branch,
            paused_travel_sec=state.delay.paused_travel_sec + max((now - state.delay.started_at).total_seconds(), 0.0),
        ),
    )


def _recompute_from_delay(
    state: MixedGasState,
    *,
    now: datetime,
    delay_min: int,
    delay_depth_fsw: int,
    branch: str,
) -> MixedGasState:
    if state.plan is None:
        return _resume_travel_from_delay_depth(state, now, branch=branch)
    recomputed = build_mixed_gas_plan(
        depth_fsw=state.plan.input_depth_fsw,
        bottom_time_min=state.plan.input_bottom_time_min + delay_min,
        bottom_mix_o2_percent=state.bottom_mix_o2_percent,
    )
    if recomputed is None:
        return _resume_travel_from_delay_depth(state, now, branch=branch)
    filtered = _filter_plan_for_delay_depth(recomputed, delay_depth_fsw)
    if state.phase is MixedGasPhase.AT_STOP:
        current = current_stop(state)
        new_current_index = None if current is None else next((stop.index for stop in filtered.stops if stop.depth_fsw == current.depth_fsw), None)
        return replace(
            state,
            plan=filtered,
            current_stop_index=new_current_index,
            delay=MixedGasDelayState(status=MixedGasDelayStatus.RESOLVED, branch=branch, paused_travel_sec=state.delay.paused_travel_sec),
        )
    previous = current_stop(state)
    previous_index = None if previous is None else next((stop.index for stop in filtered.stops if stop.depth_fsw == previous.depth_fsw), None)
    return replace(
        state,
        plan=filtered,
        current_stop_index=previous_index,
        delay=MixedGasDelayState(
            status=MixedGasDelayStatus.RESOLVED,
            branch=branch,
            paused_travel_sec=state.delay.paused_travel_sec + max((now - state.delay.started_at).total_seconds(), 0.0),
        ),
    )


def _filter_plan_for_delay_depth(plan: MixedGasPlan, delay_depth_fsw: int) -> MixedGasPlan:
    kept = tuple(stop for stop in plan.stops if stop.depth_fsw <= delay_depth_fsw)
    renumbered = tuple(
        MixedGasStop(index=index, depth_fsw=stop.depth_fsw, gas=stop.gas, duration_min=stop.duration_min)
        for index, stop in enumerate(kept, start=1)
    )
    return MixedGasPlan(
        input_depth_fsw=plan.input_depth_fsw,
        input_bottom_time_min=plan.input_bottom_time_min,
        table_depth_fsw=plan.table_depth_fsw,
        table_bottom_time_min=plan.table_bottom_time_min,
        stops=renumbered,
        is_no_decompression=plan.is_no_decompression or not renumbered,
    )


def _subtract_from_twenty_stop(state: MixedGasState, *, delay_min: int, branch: str) -> MixedGasState:
    if state.plan is None:
        return replace(state, delay=MixedGasDelayState(status=MixedGasDelayStatus.RESOLVED, branch=branch, paused_travel_sec=state.delay.paused_travel_sec))
    updated_stops = tuple(
        MixedGasStop(index=stop.index, depth_fsw=stop.depth_fsw, gas=stop.gas, duration_min=max(stop.duration_min - delay_min, 0))
        if stop.depth_fsw == 20 else stop
        for stop in state.plan.stops
    )
    return replace(
        state,
        plan=MixedGasPlan(
            input_depth_fsw=state.plan.input_depth_fsw,
            input_bottom_time_min=state.plan.input_bottom_time_min,
            table_depth_fsw=state.plan.table_depth_fsw,
            table_bottom_time_min=state.plan.table_bottom_time_min,
            stops=updated_stops,
            is_no_decompression=state.plan.is_no_decompression,
        ),
        delay=MixedGasDelayState(status=MixedGasDelayStatus.RESOLVED, branch=branch, paused_travel_sec=state.delay.paused_travel_sec),
    )


def _schedule_label(plan: MixedGasPlan) -> str:
    if plan.table_depth_fsw is None or plan.table_bottom_time_min is None:
        return "--"
    return f"{plan.table_depth_fsw} / {plan.table_bottom_time_min}"
