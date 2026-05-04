from __future__ import annotations

from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent, invalid_action_event
from .state import MixedGasState, make_initial_state
from .transitions.delay import end_delay, start_delay
from .transitions.descent import confirm_bottom_mix, convert_to_air, leave_bottom, leave_surface, leave_twenty, reach_bottom, reach_prebottom_twenty
from .transitions.hold import end_hold, start_hold
from .transitions.travel_stop import confirm_50_50, confirm_on_o2, leave_stop, reach_stop, reach_surface, toggle_off_o2


def reduce_action(state: MixedGasState, action: EngineAction, now: datetime) -> tuple[MixedGasState, tuple[AuditEvent, ...]]:
    if action is EngineAction.RESET:
        return MixedGasState(selected_surd=state.selected_surd), ()
    if action is EngineAction.LEAVE_SURFACE:
        return leave_surface(state, now)
    if action is EngineAction.START_HOLD:
        return start_hold(state, now)
    if action is EngineAction.END_HOLD:
        return end_hold(state, now)
    if action is EngineAction.REACH_STOP:
        if state.phase.name == "DESCENT_TO_20_ON_AIR":
            return reach_prebottom_twenty(state, now)
        return reach_stop(state, now)
    if action is EngineAction.CONFIRM_BOTTOM_MIX:
        return confirm_bottom_mix(state, now)
    if action is EngineAction.CONVERT_TO_AIR:
        return convert_to_air(state, now)
    if action is EngineAction.LEAVE_STOP and state.phase.name == "AT_20_PREBOTTOM_SHIFT":
        return leave_twenty(state, now)
    if action is EngineAction.LEAVE_BOTTOM and state.phase.name == "AT_20_PREBOTTOM_SHIFT":
        return leave_bottom(state, now)
    if action is EngineAction.REACH_BOTTOM:
        return reach_bottom(state, now)
    if action is EngineAction.LEAVE_BOTTOM:
        return leave_bottom(state, now)
    if action is EngineAction.CONFIRM_50_50:
        return confirm_50_50(state, now)
    if action is EngineAction.CONFIRM_ON_O2:
        return confirm_on_o2(state, now)
    if action is EngineAction.TOGGLE_OFF_O2:
        return toggle_off_o2(state, now)
    if action is EngineAction.START_DELAY:
        return start_delay(state, now)
    if action is EngineAction.END_DELAY:
        return end_delay(state, now)
    if action is EngineAction.LEAVE_STOP:
        return leave_stop(state, now)
    if action is EngineAction.REACH_SURFACE:
        return reach_surface(state, now)
    return state, (invalid_action_event(now, action.name),)
