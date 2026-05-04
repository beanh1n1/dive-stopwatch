from __future__ import annotations

from datetime import datetime

from ...domain.air_o2_profiles import next_stop_after, stop_by_index
from ...contracts.timers import elapsed as timer_elapsed
from ...contracts.timers import pause as pause_timer_state
from ...contracts.timers import remaining as timer_remaining
from ...domain.o2_breaks import break_due as shared_break_due
from ...domain.o2_breaks import break_due_remaining_sec as shared_break_due_remaining_sec
from .state import AirState, AirTimer

AIR_CLEAN_TIME_SEC = 10 * 60
AIR_MAX_DEPTH_FSW = 300
AIR_O2_BREAK_TRIGGER_SEC = 30 * 60
AIR_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC = 35 * 60


def has_supported_depth(depth_fsw: int | None) -> bool:
    return depth_fsw is not None and 0 < depth_fsw <= AIR_MAX_DEPTH_FSW


def invalid_depth_label(depth_fsw: int | None) -> str | None:
    if depth_fsw is None or depth_fsw <= 0 or depth_fsw <= AIR_MAX_DEPTH_FSW:
        return None
    return f"Max Depth ≤ {AIR_MAX_DEPTH_FSW} fsw"


def table_schedule_label(profile) -> str:
    repeat_group = f" {profile.repeat_group}" if profile.repeat_group else ""
    return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}{repeat_group}"


def next_required_stop(profile, current_stop_index):
    return next_stop_after(profile, current_stop_index)


def elapsed(timer: AirTimer | None, now: datetime) -> float:
    return timer_elapsed(None if timer is None else timer.timer, now)


def pause_timer(timer: AirTimer, now: datetime) -> AirTimer:
    return AirTimer(kind=timer.kind, timer=pause_timer_state(timer.timer, now))


def current_stop_remaining_sec(state: AirState, now: datetime) -> float | None:
    if state.plan is None or state.plan.current_stop_index is None or state.stop_timer is None:
        return None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None:
        return None
    return timer_remaining(state.stop_timer.timer, now, target_sec=current_stop.duration_min * 60)


def can_leave_stop(state: AirState, now: datetime) -> bool:
    if state.plan is None or state.plan.current_stop_index is None or state.gas_state.name == "WAITING_ON_O2":
        return False
    remaining = current_stop_remaining_sec(state, now)
    return remaining is not None and remaining <= 0


def continuous_o2_remaining_sec(state: AirState, now: datetime) -> float | None:
    if state.plan is None or state.plan.current_stop_index is None:
        return None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None or current_stop.gas != "o2":
        return None
    remaining = current_stop_remaining_sec(state, now)
    if remaining is None:
        return None
    next_index = current_stop.index + 1
    while True:
        next_stop = stop_by_index(state.plan.profile, next_index)
        if next_stop is None or next_stop.gas != "o2":
            break
        remaining += next_stop.duration_min * 60
        next_index += 1
    return remaining


def air_break_due(state: AirState, now: datetime) -> bool:
    if state.oxygen.continuous_anchor_at is None:
        return False
    remaining = continuous_o2_remaining_sec(state, now)
    return shared_break_due(
        continuous_elapsed_sec=max((now - state.oxygen.continuous_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=remaining,
        trigger_sec=AIR_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=AIR_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC,
    )


def air_break_due_remaining_sec(state: AirState, now: datetime) -> float | None:
    if state.oxygen.continuous_anchor_at is None:
        return None
    remaining = continuous_o2_remaining_sec(state, now)
    return shared_break_due_remaining_sec(
        continuous_elapsed_sec=max((now - state.oxygen.continuous_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=remaining,
        trigger_sec=AIR_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=AIR_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC,
    )


def estimated_travel_depth(state: AirState, now: datetime) -> int:
    if state.travel_timer is None:
        return state.depth_fsw or 0
    travel_elapsed_sec = max(elapsed(state.travel_timer, now) - state.delay.paused_travel_sec, 0.0)
    previous_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index) if state.plan is not None and state.plan.current_stop_index is not None else None
    start_depth = previous_stop.depth_fsw if previous_stop is not None else (state.depth_fsw or 0)
    next_stop = next_required_stop(state.plan.profile, state.plan.current_stop_index) if state.plan is not None else None
    end_depth = 0 if next_stop is None else next_stop.depth_fsw
    traveled_fsw = travel_elapsed_sec * 0.5
    if start_depth >= end_depth:
        return max(int(start_depth - traveled_fsw), end_depth)
    return min(int(round(start_depth + traveled_fsw)), end_depth)
