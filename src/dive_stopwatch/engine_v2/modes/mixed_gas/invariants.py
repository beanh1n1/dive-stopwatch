from __future__ import annotations

from .state import MixedGasDelayStatus, MixedGasPhase, MixedGasShiftState, MixedGasState


def validate_state(state: MixedGasState) -> None:
    if state.phase is MixedGasPhase.DESCENT_TO_20_ON_AIR:
        assert state.surface_timer is not None, "Descent-to-20 phase requires surface timer"
    if state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT:
        assert state.surface_timer is not None, "20-fsw phase requires surface timer"
    if state.phase is MixedGasPhase.DESCENT_TO_BOTTOM:
        assert state.travel_timer is not None or state.surface_timer is not None, "Descent-to-bottom requires travel timer"
    if state.phase is MixedGasPhase.BOTTOM:
        assert state.bottom_timer is not None, "Bottom phase requires bottom timer"
    if state.phase in {MixedGasPhase.TRAVEL_TO_FIRST_STOP, MixedGasPhase.TRAVEL_TO_SURFACE}:
        assert state.travel_timer is not None, "Travel phase requires travel timer"
    if state.phase is MixedGasPhase.AT_STOP:
        assert state.plan is not None, "Stop phase requires plan"
        assert state.current_stop_index is not None, "Stop phase requires current stop index"
    if state.shift_state is MixedGasShiftState.AWAITING_BOTTOM_MIX_CONFIRM:
        assert state.phase is MixedGasPhase.AT_20_PREBOTTOM_SHIFT, "Bottom-mix confirm only valid at 20 fsw"
    if state.shift_state is MixedGasShiftState.ABORT_READY_ON_AIR:
        assert state.phase in {MixedGasPhase.AT_20_PREBOTTOM_SHIFT, MixedGasPhase.TRAVEL_TO_SURFACE}, "Abort-ready air state only valid at 20 fsw or abort ascent"
    if state.delay.status is MixedGasDelayStatus.ACTIVE:
        assert state.delay.started_at is not None, "Active mixed-gas delay requires started_at"
        assert state.delay.depth_fsw is not None, "Active mixed-gas delay requires frozen depth"
