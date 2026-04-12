from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .dive_controller import DiveController, DivePhase
from .profile_helpers import next_stop_depth, stop_depth_for_number


@dataclass(frozen=True)
class DepthSegment:
    start_depth_fsw: int
    end_depth_fsw: int
    anchor_time: datetime
    rate_fsw_per_minute: float
    round_up: bool = True
    frozen_depth_fsw: int | None = None


def interpolate_depth(segment: DepthSegment, *, now: datetime) -> int:
    if segment.frozen_depth_fsw is not None:
        return max(segment.frozen_depth_fsw, 0)

    elapsed_seconds = max((now - segment.anchor_time).total_seconds(), 0.0)
    depth_delta = elapsed_seconds * (segment.rate_fsw_per_minute / 60.0)
    if segment.end_depth_fsw >= segment.start_depth_fsw:
        current_depth = segment.start_depth_fsw + depth_delta
        clamped_depth = min(segment.end_depth_fsw, current_depth)
    else:
        current_depth = segment.start_depth_fsw - depth_delta
        clamped_depth = max(segment.end_depth_fsw, current_depth)

    if segment.round_up:
        return max(int(math.ceil(clamped_depth)), 0)
    return max(int(clamped_depth), 0)


def estimate_current_depth(
    *,
    controller: DiveController,
    now: datetime,
    max_depth_fsw: int | None,
    active_profile,
) -> int | None:
    if controller.phase is DivePhase.DESCENT:
        return _estimate_descent_depth(
            controller=controller,
            now=now,
            max_depth_fsw=max_depth_fsw,
        )

    if controller.phase is not DivePhase.ASCENT or max_depth_fsw is None or active_profile is None:
        return None

    return _estimate_ascent_depth(
        controller=controller,
        now=now,
        max_depth_fsw=max_depth_fsw,
        active_profile=active_profile,
    )


def descent_hold_depth_for_display(
    *,
    controller: DiveController,
    start_time: datetime,
    max_depth_fsw: int | None,
) -> int | None:
    target_depth = max_depth_fsw if max_depth_fsw is not None else 10_000
    return _descent_hold_depth_at_start(
        controller=controller,
        start_time=start_time,
        target_depth_fsw=target_depth,
        round_up=False,
    )


def _estimate_descent_depth(
    *,
    controller: DiveController,
    now: datetime,
    max_depth_fsw: int | None,
) -> int | None:
    ls_event = controller.session.events.get("LS")
    if ls_event is None:
        return None

    target_depth = max_depth_fsw if max_depth_fsw is not None else 10_000
    latest_hold = controller.latest_stop_event()
    if controller._awaiting_leave_stop and latest_hold is not None:
        return _descent_hold_depth_at_start(
            controller=controller,
            start_time=latest_hold.timestamp,
            target_depth_fsw=target_depth,
            round_up=False,
        )

    segment = DepthSegment(
        start_depth_fsw=0,
        end_depth_fsw=target_depth,
        anchor_time=ls_event.timestamp,
        rate_fsw_per_minute=60.0,
        round_up=False,
    )

    if latest_hold is not None and latest_hold.kind == "end":
        hold_depth = _descent_hold_depth_at_end(
            controller=controller,
            stop_number=latest_hold.index,
            target_depth_fsw=target_depth,
        )
        if hold_depth is None:
            return None
        segment = DepthSegment(
            start_depth_fsw=hold_depth,
            end_depth_fsw=target_depth,
            anchor_time=latest_hold.timestamp,
            rate_fsw_per_minute=60.0,
            round_up=False,
        )

    return interpolate_depth(segment, now=now)


def _estimate_ascent_depth(
    *,
    controller: DiveController,
    now: datetime,
    max_depth_fsw: int,
    active_profile,
) -> int | None:
    stop_depths = sorted(active_profile.stops_fsw.keys(), reverse=True)
    active_delay = controller.latest_ascent_delay_event()
    latest_arrival = controller.latest_arrival_event()
    latest_departure = controller.latest_stop_departure_event()
    first_stop_arrival = controller.first_stop_arrival_event()
    lb_event = controller.session.events.get("LB")

    if first_stop_arrival is None:
        if lb_event is None:
            return None
        if active_delay is not None and active_delay.depth_fsw is not None:
            return active_delay.depth_fsw
        segment = DepthSegment(
            start_depth_fsw=max_depth_fsw,
            end_depth_fsw=stop_depths[0] if stop_depths else 0,
            anchor_time=lb_event.timestamp,
            rate_fsw_per_minute=30.0,
        )
        return interpolate_depth(segment, now=now)

    if controller._at_stop and latest_arrival is not None:
        return stop_depth_for_number(stop_depths, latest_arrival.stop_number)

    if latest_departure is not None:
        if active_delay is not None and active_delay.depth_fsw is not None:
            return active_delay.depth_fsw
        source_depth = stop_depth_for_number(stop_depths, latest_departure.stop_number)
        if source_depth is None:
            return None
        segment = DepthSegment(
            start_depth_fsw=source_depth,
            end_depth_fsw=next_stop_depth(stop_depths, latest_departure.stop_number),
            anchor_time=latest_departure.timestamp,
            rate_fsw_per_minute=30.0,
        )
        return interpolate_depth(segment, now=now)

    if first_stop_arrival is not None:
        return stop_depth_for_number(stop_depths, first_stop_arrival.stop_number)

    return None


def _descent_hold_depth_at_end(
    *,
    controller: DiveController,
    stop_number: int,
    target_depth_fsw: int,
) -> int | None:
    start_event = next(
        (
            event
            for event in controller.descent_hold_events
            if event.kind == "start" and event.index == stop_number
        ),
        None,
    )
    if start_event is None:
        return None
    return _descent_hold_depth_at_start(
        controller=controller,
        start_time=start_event.timestamp,
        target_depth_fsw=target_depth_fsw,
        round_up=False,
    )


def _descent_hold_depth_at_start(
    *,
    controller: DiveController,
    start_time: datetime,
    target_depth_fsw: int,
    round_up: bool,
) -> int | None:
    ls_event = controller.session.events.get("LS")
    if ls_event is None:
        return None

    previous_leave = next(
        (
            event
            for event in reversed(controller.descent_hold_events)
            if event.kind == "end" and event.timestamp <= start_time
        ),
        None,
    )
    if previous_leave is None:
        segment = DepthSegment(
            start_depth_fsw=0,
            end_depth_fsw=target_depth_fsw,
            anchor_time=ls_event.timestamp,
            rate_fsw_per_minute=60.0,
            round_up=round_up,
        )
        return interpolate_depth(segment, now=start_time)

    previous_start = next(
        (
            event
            for event in controller.descent_hold_events
            if event.kind == "start" and event.index == previous_leave.index
        ),
        None,
    )
    if previous_start is None:
        return None

    anchor_depth = _descent_hold_depth_at_start(
        controller=controller,
        start_time=previous_start.timestamp,
        target_depth_fsw=target_depth_fsw,
        round_up=round_up,
    )
    if anchor_depth is None:
        return None

    segment = DepthSegment(
        start_depth_fsw=anchor_depth,
        end_depth_fsw=target_depth_fsw,
        anchor_time=previous_leave.timestamp,
        rate_fsw_per_minute=60.0,
        round_up=round_up,
    )
    return interpolate_depth(segment, now=start_time)
