from __future__ import annotations

from ...contracts.timers import elapsed, pause, remaining, resume
from ...domain.o2_breaks import break_due as shared_break_due
from ...domain.o2_breaks import break_due_remaining_sec as shared_break_due_remaining_sec
from .plan import SurdChamberSegment, SurdPenaltyKind
from .state import SurdState

SURD_ASCENT_SEC = 60
SURD_TO_CHAMBER_50_SEC = 40
SURD_CHAMBER_TRAVEL_SEC = 20
SURD_CHAMBER_ASCENT_FSW_PER_SEC = 30 / 60
SURD_AIR_BREAK_SEC = 5 * 60
SURD_O2_BREAK_TRIGGER_SEC = 30 * 60
SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC = 0
SURD_CLEAN_TIME_SEC = 10 * 60
SURD_SURFACE_INTERVAL_NORMAL_SEC = 5 * 60
SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC = 7 * 60


def current_segment(state: SurdState) -> SurdChamberSegment | None:
    if state.chamber_plan is None or state.current_segment_index is None:
        return None
    if state.current_segment_index < 0 or state.current_segment_index >= len(state.chamber_plan.segments):
        return None
    return state.chamber_plan.segments[state.current_segment_index]


def next_segment(state: SurdState) -> SurdChamberSegment | None:
    segment = current_segment(state)
    if state.chamber_plan is None or segment is None:
        return None
    next_index = segment.segment_index + 1
    if next_index >= len(state.chamber_plan.segments):
        return None
    return state.chamber_plan.segments[next_index]


def surface_interval_penalty_kind(interval_elapsed_sec: float) -> SurdPenaltyKind:
    if interval_elapsed_sec <= SURD_SURFACE_INTERVAL_NORMAL_SEC:
        return SurdPenaltyKind.NONE
    if interval_elapsed_sec <= SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC:
        return SurdPenaltyKind.PLUS_15_AT_50
    return SurdPenaltyKind.EXCEEDED


def continuous_o2_remaining_sec(state: SurdState, now) -> float | None:
    segment = current_segment(state)
    if segment is None or state.o2_timer is None:
        return None
    remaining = max(segment.duration_sec - elapsed(state.o2_timer, now), 0.0)
    next_index = segment.segment_index + 1
    while state.chamber_plan is not None and next_index < len(state.chamber_plan.segments):
        remaining += state.chamber_plan.segments[next_index].duration_sec
        next_index += 1
    return remaining


def air_break_due(state: SurdState, now) -> bool:
    if state.continuous_o2_anchor_at is None:
        return False
    return shared_break_due(
        continuous_elapsed_sec=max((now - state.continuous_o2_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=continuous_o2_remaining_sec(state, now),
        trigger_sec=SURD_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC,
    )


def air_break_due_remaining_sec(state: SurdState, now) -> float | None:
    if state.continuous_o2_anchor_at is None:
        return None
    return shared_break_due_remaining_sec(
        continuous_elapsed_sec=max((now - state.continuous_o2_anchor_at).total_seconds(), 0.0),
        remaining_o2_obligation_sec=continuous_o2_remaining_sec(state, now),
        trigger_sec=SURD_O2_BREAK_TRIGGER_SEC,
        required_remaining_exceeds_sec=SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC,
    )


__all__ = [
    "SURD_AIR_BREAK_SEC",
    "SURD_ASCENT_SEC",
    "SURD_CHAMBER_TRAVEL_SEC",
    "SURD_CHAMBER_ASCENT_FSW_PER_SEC",
    "SURD_TO_CHAMBER_50_SEC",
    "SURD_CLEAN_TIME_SEC",
    "SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC",
    "SURD_O2_BREAK_TRIGGER_SEC",
    "SURD_SURFACE_INTERVAL_NORMAL_SEC",
    "SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC",
    "air_break_due",
    "air_break_due_remaining_sec",
    "continuous_o2_remaining_sec",
    "current_segment",
    "elapsed",
    "next_segment",
    "pause",
    "remaining",
    "resume",
    "surface_interval_penalty_kind",
]
