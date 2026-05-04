from __future__ import annotations

from datetime import datetime

from ...contracts.timers import elapsed
from ...contracts.chamber_handoff import SurdToChamberHandoff
from ...domain.depth import linear_depth_fsw
from .rules import SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC, SURD_TO_CHAMBER_50_SEC
from .state import SurdPhase, SurdState


def can_build_chamber_handoff(state: SurdState, *, now: datetime) -> bool:
    if state.phase is SurdPhase.SURFACE_INTERVAL_EXCEEDED:
        return True
    return (
        state.phase is SurdPhase.SURFACE_TO_CHAMBER_50
        and state.surface_interval_timer is not None
        and elapsed(state.surface_interval_timer, now) > SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC
    )


def build_chamber_handoff(state: SurdState, *, now: datetime, audit_tail: tuple = ()) -> SurdToChamberHandoff:
    assert can_build_chamber_handoff(state, now=now)
    assert state.handoff is not None
    assert state.surface_interval_timer is not None
    entry_depth_fsw = 50
    if state.phase is SurdPhase.SURFACE_TO_CHAMBER_50 and state.to_chamber_timer is not None:
        entry_depth_fsw = linear_depth_fsw(
            start_depth_fsw=0,
            end_depth_fsw=50,
            elapsed_sec=elapsed(state.to_chamber_timer, now),
            rate_fsw_per_sec=50 / max(SURD_TO_CHAMBER_50_SEC, 1),
        )
    return SurdToChamberHandoff(
        trigger="SURFACE_INTERVAL_EXCEEDED",
        surface_interval_elapsed_sec=elapsed(state.surface_interval_timer, now),
        entry_depth_fsw=entry_depth_fsw,
        source_entry_kind=state.handoff.entry_kind,
        input_depth_fsw=state.handoff.input_depth_fsw,
        input_bottom_time_min=state.handoff.input_bottom_time_min,
        handed_off_at=now,
        audit_tail=audit_tail,
    )
