from __future__ import annotations

from datetime import datetime, timedelta

from ...contracts.timers import elapsed, pause
from ...domain.o2_breaks import break_due as shared_break_due
from ...domain.o2_breaks import break_due_remaining_sec as shared_break_due_remaining_sec
from .plan import is_supported_bottom_mix_for_depth, max_supported_depth_for_bottom_mix, supported_bottom_mix_range_for_depth
from .state import MixedGasPlan, MixedGasShiftState, MixedGasState, MixedGasStop, MixedGasTimer

MIXED_GAS_CLEAN_TIME_SEC = 10 * 60
MIXED_GAS_MAX_DEPTH_FSW = 380
MIXED_GAS_20_FSW_GRACE_SEC = 5 * 60
MIXED_GAS_AIR_BREAK_SEC = 5 * 60
MIXED_GAS_O2_BREAK_TRIGGER_SEC = 30 * 60
MIXED_GAS_O2_BREAK_SUPPRESSION_SEC = 35 * 60


def has_supported_depth(state: MixedGasState) -> bool:
    return state.depth_fsw is not None and 0 < state.depth_fsw <= MIXED_GAS_MAX_DEPTH_FSW


def has_supported_bottom_mix(state: MixedGasState) -> bool:
    percent = state.bottom_mix_o2_percent
    if percent is None or not 10 <= percent <= 40:
        return False
    if state.depth_fsw is None:
        return True
    return is_supported_bottom_mix_for_depth(depth_fsw=state.depth_fsw, bottom_mix_o2_percent=percent)


def has_minimum_bottom_mix_percent(state: MixedGasState) -> bool:
    percent = state.bottom_mix_o2_percent
    return percent is None or percent >= minimum_bottom_mix_percent(state)


def requires_20fsw_air_descent(state: MixedGasState) -> bool:
    percent = state.bottom_mix_o2_percent
    return percent is not None and percent < 16


def can_begin_descent(state: MixedGasState) -> bool:
    return has_supported_depth(state) and has_supported_bottom_mix(state)


def supported_bottom_mix_range_label(state: MixedGasState) -> str | None:
    supported_range = supported_bottom_mix_range_for_depth(state.depth_fsw)
    if supported_range is None:
        return None
    low, high = supported_range
    return f"Supported Mix: {_format_o2_percent(low)}-{_format_o2_percent(high)}% O2"


def invalid_depth_label(state: MixedGasState) -> str | None:
    if state.depth_fsw is None or state.depth_fsw <= 0 or state.depth_fsw <= MIXED_GAS_MAX_DEPTH_FSW:
        return None
    return f"Max Depth ≤ {MIXED_GAS_MAX_DEPTH_FSW} fsw"


def max_supported_depth_label(state: MixedGasState) -> str | None:
    max_depth_fsw = max_supported_depth_for_bottom_mix(state.bottom_mix_o2_percent)
    if max_depth_fsw is None:
        return None
    return f"Max Depth ≤ {max_depth_fsw} fsw"


def invalid_bottom_mix_label(state: MixedGasState) -> str | None:
    percent = state.bottom_mix_o2_percent
    if percent is not None and not 10 <= percent <= 40:
        return "Bottom Mix 10-40% required"
    minimum_percent = minimum_bottom_mix_percent(state)
    if percent is None or percent >= minimum_percent:
        return None
    return f"Bottom Mix ≥ {_format_o2_percent(minimum_percent)}% required"


def minimum_bottom_mix_percent(state: MixedGasState) -> float:
    depth_fsw = state.depth_fsw
    if depth_fsw is not None and depth_fsw <= 200:
        return 14.0
    return 10.0


def grace_anchor(state: MixedGasState) -> datetime | None:
    if state.grace_window_timer is None:
        return None
    return state.grace_window_timer.timer.started_at


def planned_bottom_anchor_for_departure(state: MixedGasState, departure_at: datetime) -> datetime:
    anchor = grace_anchor(state)
    if anchor is None:
        return departure_at
    return min(departure_at, anchor + timedelta(seconds=MIXED_GAS_20_FSW_GRACE_SEC))


def stop_by_index(plan: MixedGasPlan, stop_index: int | None) -> MixedGasStop | None:
    if stop_index is None:
        return None
    for stop in plan.stops:
        if stop.index == stop_index:
            return stop
    return None


def current_stop(state: MixedGasState) -> MixedGasStop | None:
    if state.plan is None:
        return None
    return stop_by_index(state.plan, state.current_stop_index)


def next_stop(plan: MixedGasPlan | None, current_stop_index: int | None) -> MixedGasStop | None:
    if plan is None:
        return None
    for stop in plan.stops:
        if current_stop_index is None or stop.index > current_stop_index:
            return stop
    return None


def crosses_ninety(from_depth_fsw: int | None, to_depth_fsw: int | None) -> bool:
    if from_depth_fsw is None or to_depth_fsw is None:
        return False
    return from_depth_fsw > 90 > to_depth_fsw


def has_ninety_stop(plan: MixedGasPlan | None) -> bool:
    return bool(plan is not None and any(stop.depth_fsw == 90 for stop in plan.stops))


def current_stop_remaining_sec(state: MixedGasState, now: datetime) -> float | None:
    stop = current_stop(state)
    if stop is None:
        return None
    if state.stop_timer is None:
        return float(stop.duration_min * 60)
    return max((stop.duration_min * 60) - elapsed(state.stop_timer.timer, now), 0.0)


def continuous_o2_remaining_sec(state: MixedGasState, now: datetime) -> float | None:
    stop = current_stop(state)
    if stop is None or stop.gas != "o2":
        return None
    if state.shift_state is MixedGasShiftState.AWAITING_O2_CONFIRM:
        return None
    remaining = current_stop_remaining_sec(state, now)
    if remaining is None:
        return None
    next_index = stop.index + 1
    while True:
        upcoming = stop_by_index(state.plan, next_index) if state.plan is not None else None
        if upcoming is None or upcoming.gas != "o2":
            break
        remaining += upcoming.duration_min * 60
        next_index += 1
    return remaining


def air_break_due(state: MixedGasState, now: datetime) -> bool:
    if state.oxygen.continuous_anchor_at is None:
        return False
    remaining = continuous_o2_remaining_sec(state, now)
    return shared_break_due(
        continuous_elapsed_sec=max((now - state.oxygen.continuous_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=remaining,
        trigger_sec=MIXED_GAS_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=MIXED_GAS_O2_BREAK_SUPPRESSION_SEC,
    )


def air_break_due_remaining_sec(state: MixedGasState, now: datetime) -> float | None:
    if state.oxygen.continuous_anchor_at is None:
        return None
    remaining = continuous_o2_remaining_sec(state, now)
    return shared_break_due_remaining_sec(
        continuous_elapsed_sec=max((now - state.oxygen.continuous_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=remaining,
        trigger_sec=MIXED_GAS_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=MIXED_GAS_O2_BREAK_SUPPRESSION_SEC,
    )


def pause_timer(timer: MixedGasTimer, now: datetime) -> MixedGasTimer:
    return MixedGasTimer(kind=timer.kind, timer=pause(timer.timer, now))


def _format_o2_percent(percent: float) -> str:
    formatted = f"{percent:.1f}"
    if formatted.endswith(".0"):
        return formatted[:-2]
    return formatted
