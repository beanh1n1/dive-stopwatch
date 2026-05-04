from __future__ import annotations

from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent, invalid_action_event
from .state import AirState, make_initial_state
from .transitions.delay import end_delay, start_delay
from .transitions.gas_management import confirm_on_o2, convert_to_air, toggle_off_o2
from .transitions.hold import end_hold, start_hold
from .transitions.travel_stop import leave_bottom, leave_stop, leave_surface, reach_bottom, reach_stop, reach_surface


def reduce_action(state: AirState, action: EngineAction, now: datetime) -> tuple[AirState, tuple[AuditEvent, ...]]:
    if action is EngineAction.RESET:
        return make_initial_state(
            mode=state.mode,
            selected_surd=state.selected_surd,
            depth_text=state.depth_text,
            depth_fsw=state.depth_fsw,
        ), ()
    if action is EngineAction.LEAVE_SURFACE:
        return leave_surface(state, now)
    if action is EngineAction.START_HOLD:
        return start_hold(state, now)
    if action is EngineAction.END_HOLD:
        return end_hold(state, now)
    if action is EngineAction.REACH_BOTTOM:
        return reach_bottom(state, now)
    if action is EngineAction.LEAVE_BOTTOM:
        return leave_bottom(state, now)
    if action is EngineAction.REACH_STOP:
        return reach_stop(state, now)
    if action is EngineAction.LEAVE_STOP:
        return leave_stop(state, now)
    if action is EngineAction.REACH_SURFACE:
        return reach_surface(state, now)
    if action is EngineAction.CONFIRM_ON_O2:
        return confirm_on_o2(state, now)
    if action is EngineAction.TOGGLE_OFF_O2:
        return toggle_off_o2(state, now)
    if action is EngineAction.CONVERT_TO_AIR:
        return convert_to_air(state, now)
    if action is EngineAction.START_DELAY:
        return start_delay(state, now)
    if action is EngineAction.END_DELAY:
        return end_delay(state, now)
    return state, (invalid_action_event(now, action.name),)
