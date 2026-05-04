from __future__ import annotations

from dataclasses import replace

from ....contracts.surd_handoff import SurdEntryKind
from ....contracts.timers import TimerState
from ..invariants import validate_state
from ..state import SurdPhase, SurdState


def start_from_handoff(state: SurdState, handoff) -> SurdState:
    if handoff.entry_kind is SurdEntryKind.L40_NORMAL:
        updated = replace(
            state,
            phase=SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP,
            handoff=handoff,
            surface_interval_timer=TimerState(started_at=handoff.handed_off_at),
            surface_ascent_timer=TimerState(started_at=handoff.handed_off_at),
        )
        validate_state(updated)
        return updated

    if handoff.entry_kind is SurdEntryKind.ADAPTER_30_20:
        updated = replace(
            state,
            phase=SurdPhase.SURFACE_TO_CHAMBER_50,
            handoff=handoff,
            surface_interval_timer=TimerState(started_at=handoff.handed_off_at),
            to_chamber_timer=TimerState(started_at=handoff.handed_off_at),
        )
        validate_state(updated)
        return updated

    if handoff.entry_kind is SurdEntryKind.SURFACE_DIRECT:
        updated = replace(
            state,
            phase=SurdPhase.SURFACE_UNDRESS,
            handoff=handoff,
            surface_interval_timer=TimerState(started_at=handoff.handed_off_at),
            undress_timer=TimerState(started_at=handoff.handed_off_at),
        )
        validate_state(updated)
        return updated

    raise ValueError(f"Unsupported SURD entry kind: {handoff.entry_kind!r}")
