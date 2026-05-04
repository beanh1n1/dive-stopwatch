from __future__ import annotations

from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent, invalid_action_event
from .state import SurdState, make_initial_state
from .transitions.chamber import complete_to_surface, confirm_on_o2, end_air_break, move_chamber, reach_stop, start_air_break, toggle_off_o2
from .transitions.entry import start_from_handoff
from .transitions.surface_interval import leave_surface, reach_chamber_50, reach_surface


def reduce_action(state: SurdState, action: EngineAction, now: datetime) -> tuple[SurdState, tuple[AuditEvent, ...]]:
    if action is EngineAction.RESET:
        return make_initial_state(), ()
    if action is EngineAction.REACH_SURFACE:
        return reach_surface(state, now)
    if action is EngineAction.LEAVE_SURFACE:
        return leave_surface(state, now)
    if action is EngineAction.REACH_CHAMBER_50:
        return reach_chamber_50(state, now)
    if action is EngineAction.REACH_STOP:
        return reach_stop(state, now)
    if action is EngineAction.CONFIRM_ON_O2:
        return confirm_on_o2(state, now)
    if action is EngineAction.TOGGLE_OFF_O2:
        return toggle_off_o2(state, now)
    if action is EngineAction.MOVE_CHAMBER:
        return move_chamber(state, now)
    if action is EngineAction.START_AIR_BREAK:
        return start_air_break(state, now)
    if action is EngineAction.END_AIR_BREAK:
        return end_air_break(state, now)
    if action is EngineAction.COMPLETE_TO_SURFACE:
        return complete_to_surface(state, now)
    return state, (invalid_action_event(now, action.name),)


__all__ = ["reduce_action", "start_from_handoff"]
