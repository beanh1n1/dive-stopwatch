from __future__ import annotations

from dataclasses import dataclass

from .dive_session import ceil_minutes


@dataclass(frozen=True)
class FirstStopDelayRuleDecision:
    delay_seconds: float | None
    rounded_delay_minutes: int
    outcome: str


@dataclass(frozen=True)
class BetweenStopsDelayRuleDecision:
    delay_seconds: float
    rounded_delay_minutes: int
    outcome: str


def evaluate_first_stop_delay_rule(
    *,
    actual_tt1st_seconds: float,
    planned_tt1st_seconds: int | None,
    delay_depth_fsw: int | None,
) -> FirstStopDelayRuleDecision:
    if planned_tt1st_seconds is None:
        return FirstStopDelayRuleDecision(
            delay_seconds=None,
            rounded_delay_minutes=0,
            outcome="no_planned_tt1st",
        )

    if actual_tt1st_seconds < planned_tt1st_seconds:
        return FirstStopDelayRuleDecision(
            delay_seconds=actual_tt1st_seconds - planned_tt1st_seconds,
            rounded_delay_minutes=0,
            outcome="early_arrival",
        )

    delay_seconds = actual_tt1st_seconds - planned_tt1st_seconds
    if delay_seconds <= 60:
        return FirstStopDelayRuleDecision(
            delay_seconds=delay_seconds,
            rounded_delay_minutes=0,
            outcome="ignore_delay",
        )

    rounded_delay_minutes = ceil_minutes(delay_seconds)
    if delay_depth_fsw is not None and delay_depth_fsw <= 50:
        return FirstStopDelayRuleDecision(
            delay_seconds=delay_seconds,
            rounded_delay_minutes=rounded_delay_minutes,
            outcome="add_to_first_stop",
        )

    return FirstStopDelayRuleDecision(
        delay_seconds=delay_seconds,
        rounded_delay_minutes=rounded_delay_minutes,
        outcome="recompute",
    )


def evaluate_between_stops_delay_rule(
    *,
    actual_elapsed_seconds: float,
    planned_elapsed_seconds: int,
    delay_depth_fsw: int,
) -> BetweenStopsDelayRuleDecision:
    delay_seconds = actual_elapsed_seconds - planned_elapsed_seconds
    if delay_seconds <= 60:
        return BetweenStopsDelayRuleDecision(
            delay_seconds=delay_seconds,
            rounded_delay_minutes=0,
            outcome="ignore_delay",
        )

    if delay_depth_fsw <= 50:
        return BetweenStopsDelayRuleDecision(
            delay_seconds=delay_seconds,
            rounded_delay_minutes=0,
            outcome="ignore_delay",
        )

    return BetweenStopsDelayRuleDecision(
        delay_seconds=delay_seconds,
        rounded_delay_minutes=ceil_minutes(delay_seconds),
        outcome="recompute",
    )
