from __future__ import annotations

from .state import AirPhase, AirState


def validate_state(state: AirState) -> None:
    if state.phase is AirPhase.AT_STOP:
        assert state.plan is not None, "AT_STOP requires a plan"
        assert state.plan.current_stop_index is not None, "AT_STOP requires current_stop_index"
        assert (
            state.stop_timer is not None
            or state.tsv_timer is not None
            or state.interruption_timer is not None
            or state.air_break_timer is not None
        ), "AT_STOP requires stop-related timer"
    if state.phase in {AirPhase.TRAVEL_TO_FIRST_STOP, AirPhase.TRAVEL_TO_SURFACE}:
        assert state.travel_timer is not None, "Travel requires travel_timer"
