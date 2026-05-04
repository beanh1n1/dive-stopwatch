from __future__ import annotations

from datetime import datetime

from ...contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from .rules import current_stop, current_stop_remaining_sec, next_stop
from .state import MixedGasPhase, MixedGasState


def can_build_surd_handoff(state: MixedGasState) -> bool:
    if state.phase is not MixedGasPhase.AT_STOP:
        return False
    stop = current_stop(state)
    if stop is None:
        return False
    return stop.depth_fsw in {30, 20}


def can_build_normal_surd_handoff(state: MixedGasState) -> bool:
    if state.phase is not MixedGasPhase.AT_STOP:
        return False
    stop = current_stop(state)
    if stop is None:
        return False
    return stop.depth_fsw == 40


def can_build_surface_surd_handoff(state: MixedGasState) -> bool:
    if not state.selected_surd or state.phase is not MixedGasPhase.TRAVEL_TO_FIRST_STOP:
        return False
    upcoming = next_stop(state.plan, state.current_stop_index)
    if upcoming is None:
        return False
    return upcoming.depth_fsw < 40


def build_surd_handoff(state: MixedGasState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_surd_handoff(state):
        raise ValueError("Mixed Gas state is not eligible for SURD handoff.")
    assert state.plan is not None
    stop = current_stop(state)
    assert stop is not None
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.ADAPTER_30_20,
        source_mode="MIXED_GAS",
        input_depth_fsw=state.plan.input_depth_fsw,
        input_bottom_time_min=state.plan.input_bottom_time_min,
        source_table_depth_fsw=state.plan.table_depth_fsw,
        source_table_bottom_time_min=state.plan.table_bottom_time_min,
        left_water_stop_depth_fsw=stop.depth_fsw,
        remaining_in_water_obligation_sec=current_stop_remaining_sec(state, now),
        handed_off_at=now,
        audit_tail=audit_tail,
    )


def build_normal_surd_handoff(state: MixedGasState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_normal_surd_handoff(state):
        raise ValueError("Mixed Gas state is not eligible for normal SURD handoff.")
    assert state.plan is not None
    stop = current_stop(state)
    assert stop is not None
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.L40_NORMAL,
        source_mode="MIXED_GAS",
        input_depth_fsw=state.plan.input_depth_fsw,
        input_bottom_time_min=state.plan.input_bottom_time_min,
        source_table_depth_fsw=state.plan.table_depth_fsw,
        source_table_bottom_time_min=state.plan.table_bottom_time_min,
        left_water_stop_depth_fsw=stop.depth_fsw,
        remaining_in_water_obligation_sec=0.0,
        handed_off_at=now,
        audit_tail=audit_tail,
    )


def build_surface_surd_handoff(state: MixedGasState, *, now: datetime, audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    if not can_build_surface_surd_handoff(state):
        raise ValueError("Mixed Gas state is not eligible for direct surface SURD handoff.")
    assert state.plan is not None
    return InWaterToSurdHandoff(
        entry_kind=SurdEntryKind.SURFACE_DIRECT,
        source_mode="MIXED_GAS",
        input_depth_fsw=state.plan.input_depth_fsw,
        input_bottom_time_min=state.plan.input_bottom_time_min,
        source_table_depth_fsw=state.plan.table_depth_fsw,
        source_table_bottom_time_min=state.plan.table_bottom_time_min,
        left_water_stop_depth_fsw=40,
        remaining_in_water_obligation_sec=0.0,
        handed_off_at=now,
        audit_tail=audit_tail,
    )
