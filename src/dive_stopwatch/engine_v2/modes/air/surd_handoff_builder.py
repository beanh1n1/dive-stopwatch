from __future__ import annotations

from datetime import datetime

from ...domain.air_o2_profiles import next_stop_after, stop_by_index
from ...contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from .rules import current_stop_remaining_sec
from .state import AirPhase, AirState


def can_build_surd_handoff(state: AirState) -> bool:
    if state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return False
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None:
        return False
    return current_stop.depth_fsw in {30, 20}


def can_build_normal_surd_handoff(state: AirState) -> bool:
    if state.phase is not AirPhase.AT_STOP or state.plan is None or state.plan.current_stop_index is None:
        return False
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    if current_stop is None:
        return False
    return current_stop.depth_fsw == 40


def can_build_surface_surd_handoff(state: AirState) -> bool:
    if not state.selected_surd or state.phase is not AirPhase.TRAVEL_TO_FIRST_STOP or state.plan is None:
        return False
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index)
    if next_stop is None:
        return False
    return next_stop.depth_fsw < 40


def build_surd_handoff(state: AirState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_surd_handoff(state):
        raise ValueError("AIR state is not eligible for SURD handoff.")
    assert state.plan is not None
    assert state.plan.current_stop_index is not None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    assert current_stop is not None
    profile = state.plan.profile
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.ADAPTER_30_20,
        source_mode=state.mode.value,
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        source_table_depth_fsw=profile.table_depth_fsw,
        source_table_bottom_time_min=profile.table_bottom_time_min,
        left_water_stop_depth_fsw=current_stop.depth_fsw,
        remaining_in_water_obligation_sec=current_stop_remaining_sec(state, now),
        handed_off_at=now,
        audit_tail=audit_tail,
    )


def build_normal_surd_handoff(state: AirState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_normal_surd_handoff(state):
        raise ValueError("AIR state is not eligible for normal SURD handoff.")
    assert state.plan is not None
    assert state.plan.current_stop_index is not None
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index)
    assert current_stop is not None
    profile = state.plan.profile
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.L40_NORMAL,
        source_mode=state.mode.value,
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        source_table_depth_fsw=profile.table_depth_fsw,
        source_table_bottom_time_min=profile.table_bottom_time_min,
        left_water_stop_depth_fsw=current_stop.depth_fsw,
        remaining_in_water_obligation_sec=0.0,
        handed_off_at=now,
        audit_tail=audit_tail,
    )


def build_surface_surd_handoff(state: AirState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_surface_surd_handoff(state):
        raise ValueError("AIR state is not eligible for direct surface SURD handoff.")
    assert state.plan is not None
    profile = state.plan.profile
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.SURFACE_DIRECT,
        source_mode=state.mode.value,
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        source_table_depth_fsw=profile.table_depth_fsw,
        source_table_bottom_time_min=profile.table_bottom_time_min,
        left_water_stop_depth_fsw=40,
        remaining_in_water_obligation_sec=0.0,
        handed_off_at=now,
        audit_tail=audit_tail,
    )
