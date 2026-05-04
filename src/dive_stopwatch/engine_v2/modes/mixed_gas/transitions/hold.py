from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ....contracts.actions import EngineAction
from ....contracts.events import AuditEvent, AuditEventKind, invalid_action_event
from ..invariants import validate_state
from ..state import MixedGasPhase, MixedGasState


def start_hold(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase not in {MixedGasPhase.DESCENT_TO_20_ON_AIR, MixedGasPhase.DESCENT_TO_BOTTOM} or state.active_hold_started_at is not None:
        return state, (invalid_action_event(now, EngineAction.START_HOLD.name),)
    updated = replace(
        state,
        active_hold_started_at=now,
        hold_index=state.hold_index + 1,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.HOLD_STARTED, at=now, payload={"hold_index": updated.hold_index}),)


def end_hold(state: MixedGasState, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if state.phase not in {MixedGasPhase.DESCENT_TO_20_ON_AIR, MixedGasPhase.DESCENT_TO_BOTTOM} or state.active_hold_started_at is None:
        return state, (invalid_action_event(now, EngineAction.END_HOLD.name),)
    held_sec = max((now - state.active_hold_started_at).total_seconds(), 0.0)
    updated = replace(
        state,
        active_hold_started_at=None,
        hold_elapsed_sec=state.hold_elapsed_sec + held_sec,
    )
    validate_state(updated)
    return updated, (AuditEvent(kind=AuditEventKind.HOLD_ENDED, at=now, payload={"hold_index": state.hold_index}),)
