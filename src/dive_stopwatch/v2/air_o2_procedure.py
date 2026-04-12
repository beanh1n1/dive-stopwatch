from __future__ import annotations

from datetime import datetime
from typing import Iterable, Protocol


class AirBreakLike(Protocol):
    kind: str
    index: int
    timestamp: datetime


class AscentStopLike(Protocol):
    kind: str
    stop_number: int
    timestamp: datetime


def active_air_break_event(events: Iterable[AirBreakLike]) -> AirBreakLike | None:
    starts = {
        event.index: event
        for event in events
        if event.kind == "start"
    }
    ends = {
        event.index: event
        for event in events
        if event.kind == "end"
    }
    active_indices = [index for index in starts if index not in ends]
    if not active_indices:
        return None
    return starts[max(active_indices)]


def current_air_break_elapsed_seconds(
    *,
    active_break,
    now: datetime,
) -> float | None:
    if active_break is None:
        return None
    return max((now - active_break.timestamp).total_seconds(), 0.0)


def ignored_air_seconds_between(
    *,
    events: Iterable[AirBreakLike],
    start_time: datetime,
    end_time: datetime,
    now: datetime,
) -> float:
    ignored_seconds = 0.0
    start_events = {
        event.index: event
        for event in events
        if event.kind == "start"
    }
    end_events = {
        event.index: event
        for event in events
        if event.kind == "end"
    }
    for index, start_event in start_events.items():
        interval_end = end_events.get(index).timestamp if index in end_events else now
        overlap_start = max(start_time, start_event.timestamp)
        overlap_end = min(end_time, interval_end)
        if overlap_end > overlap_start:
            ignored_seconds += (overlap_end - overlap_start).total_seconds()
    return ignored_seconds


def oxygen_elapsed_seconds(
    *,
    oxygen_segment_started_at: datetime | None,
    active_break,
    now: datetime,
) -> float | None:
    if oxygen_segment_started_at is None or active_break is not None:
        return None
    return max((now - oxygen_segment_started_at).total_seconds(), 0.0)


def oxygen_break_due(oxygen_elapsed: float | None) -> bool:
    return oxygen_elapsed is not None and oxygen_elapsed >= 1800


def air_o2_credit_to_20_stop_seconds(
    *,
    stops_fsw: dict[int, int],
    ascent_stop_events: Iterable[AscentStopLike],
    first_oxygen_confirmed_at: datetime | None,
    air_break_events: Iterable[AirBreakLike],
    now: datetime,
) -> float:
    if first_oxygen_confirmed_at is None:
        return 0.0
    stop_depths = sorted(stops_fsw.keys(), reverse=True)
    if 20 not in stop_depths or 30 not in stop_depths:
        return 0.0
    stop_30_number = stop_depths.index(30) + 1
    arrival_30 = next(
        (
            event
            for event in ascent_stop_events
            if event.kind == "reach" and event.stop_number == stop_30_number
        ),
        None,
    )
    departure_30 = next(
        (
            event
            for event in ascent_stop_events
            if event.kind == "leave" and event.stop_number == stop_30_number
        ),
        None,
    )
    if arrival_30 is None or departure_30 is None:
        return 0.0
    planned_30_seconds = (stops_fsw.get(30) or 0) * 60
    actual_30_seconds = max(
        (departure_30.timestamp - first_oxygen_confirmed_at).total_seconds()
        - ignored_air_seconds_between(
            events=air_break_events,
            start_time=first_oxygen_confirmed_at,
            end_time=departure_30.timestamp,
            now=now,
        ),
        0.0,
    )
    return max(actual_30_seconds - planned_30_seconds, 0.0)


def air_o2_accrued_credit_to_20_stop_seconds(
    *,
    stops_fsw: dict[int, int],
    current_depth: int | None,
    first_oxygen_confirmed_at: datetime | None,
    air_break_events: Iterable[AirBreakLike],
    now: datetime,
) -> float:
    if first_oxygen_confirmed_at is None or current_depth != 30:
        return 0.0
    planned_30_seconds = (stops_fsw.get(30) or 0) * 60
    elapsed_30_seconds = max(
        (now - first_oxygen_confirmed_at).total_seconds()
        - ignored_air_seconds_between(
            events=air_break_events,
            start_time=first_oxygen_confirmed_at,
            end_time=now,
            now=now,
        ),
        0.0,
    )
    return max(elapsed_30_seconds - planned_30_seconds, 0.0)


def current_stop_balance_seconds(
    *,
    required_stop_time_min: int | None,
    anchor_time: datetime | None,
    now: datetime,
    current_depth: int | None,
    is_air_o2_mode: bool,
    ignored_air_seconds: float,
    credit_to_20_seconds: float,
) -> float | None:
    if required_stop_time_min is None or anchor_time is None:
        return None
    elapsed_seconds = max((now - anchor_time).total_seconds(), 0.0)
    if is_air_o2_mode and current_depth in {20, 30}:
        elapsed_seconds = max(elapsed_seconds - ignored_air_seconds, 0.0)
    balance_seconds = (required_stop_time_min * 60) - elapsed_seconds
    if is_air_o2_mode and current_depth == 20:
        balance_seconds -= credit_to_20_seconds
    return balance_seconds


def remaining_oxygen_obligation_seconds(
    *,
    stops_fsw: dict[int, int],
    at_stop: bool,
    current_depth: int | None,
    current_balance_seconds: float | None,
    latest_departure_timestamp: datetime | None,
    departure_depth: int | None,
    next_depth: int | None,
    credit_to_20_seconds: float,
    accrued_credit_to_20_seconds: float,
    ignored_air_seconds_since_departure: float,
    now: datetime,
) -> float | None:
    if at_stop:
        if current_depth not in {20, 30} or current_balance_seconds is None:
            return None
        future_seconds = 0.0
        for depth, stop_time in stops_fsw.items():
            if depth < current_depth and depth in {20, 30}:
                future_seconds += stop_time * 60
        if current_depth == 30:
            future_seconds = max(future_seconds - accrued_credit_to_20_seconds, 0.0)
        return max(current_balance_seconds, 0.0) + future_seconds

    if latest_departure_timestamp is None or departure_depth != 30 or next_depth != 20:
        return None
    stop_20_seconds = (stops_fsw.get(20) or 0) * 60
    elapsed_seconds = max(
        (now - latest_departure_timestamp).total_seconds() - ignored_air_seconds_since_departure,
        0.0,
    )
    return max(stop_20_seconds - credit_to_20_seconds - elapsed_seconds, 0.0)


def active_o2_display_mode(
    *,
    oxygen_segment_started_at: datetime | None,
    active_break,
    current_depth: int | None,
    departure_depth: int | None,
    next_depth: int | None,
    at_stop: bool,
) -> bool:
    if oxygen_segment_started_at is None or active_break is not None:
        return False
    if at_stop:
        return current_depth in {20, 30}
    return departure_depth in {20, 30} and next_depth in {20, 0}


def should_shift_to_air_for_surface(
    *,
    current_depth: int | None,
    oxygen_break_due_now: bool,
    current_stop_remaining_text: str,
    at_stop: bool,
) -> bool:
    return (
        at_stop
        and current_depth == 20
        and oxygen_break_due_now
        and current_stop_remaining_text == "00:00"
    )


def can_start_air_break(
    *,
    active_break,
    awaiting_o2_confirmation: bool,
    current_depth: int | None,
    oxygen_segment_started_at: datetime | None,
    oxygen_break_due_now: bool,
    current_stop_remaining_text: str,
    at_stop: bool,
) -> bool:
    if at_stop is False:
        return False
    if active_break is not None or awaiting_o2_confirmation:
        return False
    if current_depth not in {20, 30}:
        return False
    if oxygen_segment_started_at is None or not oxygen_break_due_now:
        return False
    if current_depth == 20 and current_stop_remaining_text == "00:00":
        return False
    return True
