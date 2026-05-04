from __future__ import annotations

from .state import SurdPhase, SurdState


def validate_state(state: SurdState) -> None:
    if state.phase is not SurdPhase.READY:
        assert state.handoff is not None, "Non-ready SURD state requires handoff"
        assert state.surface_interval_timer is not None, "Non-ready SURD state requires surface interval timer"

    if state.phase is SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP:
        assert state.surface_ascent_timer is not None, "Surface ascent phase requires ascent timer"

    if state.phase is SurdPhase.SURFACE_UNDRESS:
        assert state.undress_timer is not None, "Undress phase requires undress timer"

    if state.phase is SurdPhase.SURFACE_TO_CHAMBER_50:
        assert state.to_chamber_timer is not None, "Travel-to-chamber phase requires chamber travel timer"

    if state.phase in {SurdPhase.CHAMBER_AT_50_WAITING_O2, SurdPhase.CHAMBER_READY_TO_MOVE, SurdPhase.CHAMBER_ON_O2, SurdPhase.CHAMBER_OFF_O2, SurdPhase.CHAMBER_AIR_BREAK, SurdPhase.CHAMBER_TRAVEL_TO_SURFACE, SurdPhase.COMPLETE_CLEAN_TIME, SurdPhase.COMPLETE_DONE}:
        assert state.chamber_plan is not None, "Chamber phases require chamber plan"
        assert state.current_segment_index is not None or state.phase in {SurdPhase.COMPLETE_CLEAN_TIME, SurdPhase.COMPLETE_DONE}, "Active chamber phases require current segment"

    if state.phase is SurdPhase.CHAMBER_READY_TO_MOVE:
        assert state.move_ready_timer is not None, "Ready-to-move phase requires move-ready timer"

    if state.phase is SurdPhase.CHAMBER_ON_O2:
        assert state.o2_timer is not None, "On-O2 phase requires O2 timer"

    if state.phase is SurdPhase.CHAMBER_OFF_O2:
        assert state.off_o2_timer is not None, "Off-O2 phase requires off-O2 timer"
        assert state.o2_timer is not None, "Off-O2 phase requires paused O2 timer"

    if state.phase is SurdPhase.CHAMBER_AIR_BREAK:
        assert state.air_break_timer is not None, "Air-break phase requires air-break timer"

    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE:
        assert state.chamber_surface_ascent_timer is not None, "Travel-to-surface phase requires ascent timer"
        assert state.chamber_surface_ascent_from_depth_fsw is not None, "Travel-to-surface phase requires start depth"
        assert state.chamber_surface_ascent_on_o2 is not None, "Travel-to-surface phase requires ascent gas state"

    if state.phase is SurdPhase.COMPLETE_CLEAN_TIME:
        assert state.clean_time_timer is not None, "Clean-time phase requires clean-time timer"
