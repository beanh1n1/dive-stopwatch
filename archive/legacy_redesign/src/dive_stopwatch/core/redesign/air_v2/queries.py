from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...air_o2_profiles import next_stop_after, stop_by_index
from .state import (
    AirV2AvailableAction,
    AirV2GasState,
    AirV2Obligation,
    AirV2Phase,
    AirV2State,
    AirV2TimerKind,
)


@dataclass(frozen=True)
class AirV2SemanticView:
    phase: AirV2Phase
    gas_state: AirV2GasState
    obligation: AirV2Obligation
    available_actions: tuple[AirV2AvailableAction, ...]
    active_timer_kind: AirV2TimerKind | None
    active_timer_elapsed_sec: float | None
    current_depth_fsw: int | None
    current_stop_depth_fsw: int | None
    current_stop_duration_min: int | None
    current_stop_remaining_sec: float | None
    next_stop_depth_fsw: int | None
    next_stop_duration_min: int | None
    schedule_mode_text: str | None


def derive_semantic_view(state: AirV2State, now: datetime) -> AirV2SemanticView:
    current_stop = stop_by_index(state.plan.profile, state.plan.current_stop_index) if state.plan is not None and state.plan.current_stop_index is not None else None
    next_stop = next_stop_after(state.plan.profile, state.plan.current_stop_index) if state.plan is not None else None
    active_timer_elapsed_sec = None if state.active_timer is None else max((now - state.active_timer.started_at).total_seconds(), 0.0)
    return AirV2SemanticView(
        phase=state.phase,
        gas_state=state.gas_state,
        obligation=_obligation_for_phase(state.phase),
        available_actions=_available_actions_for_phase(state.phase),
        active_timer_kind=None if state.active_timer is None else state.active_timer.kind,
        active_timer_elapsed_sec=active_timer_elapsed_sec,
        current_depth_fsw=state.depth_fsw,
        current_stop_depth_fsw=None if current_stop is None else current_stop.depth_fsw,
        current_stop_duration_min=None if current_stop is None else current_stop.duration_min,
        current_stop_remaining_sec=_current_stop_remaining_sec(current_stop, active_timer_elapsed_sec, state.phase),
        next_stop_depth_fsw=None if next_stop is None else next_stop.depth_fsw,
        next_stop_duration_min=None if next_stop is None else next_stop.duration_min,
        schedule_mode_text=None if state.plan is None else state.plan.profile.mode.value,
    )


def _obligation_for_phase(phase: AirV2Phase) -> AirV2Obligation:
    return {
        AirV2Phase.READY: AirV2Obligation.LEAVE_SURFACE,
        AirV2Phase.DESCENT: AirV2Obligation.REACH_BOTTOM,
        AirV2Phase.BOTTOM: AirV2Obligation.LEAVE_BOTTOM,
        AirV2Phase.TRAVEL_TO_FIRST_STOP: AirV2Obligation.REACH_STOP,
        AirV2Phase.TRAVEL_TO_SURFACE: AirV2Obligation.REACH_SURFACE,
        AirV2Phase.AT_STOP: AirV2Obligation.LEAVE_STOP,
        AirV2Phase.COMPLETE: AirV2Obligation.NONE,
    }[phase]


def _available_actions_for_phase(phase: AirV2Phase) -> tuple[AirV2AvailableAction, ...]:
    return {
        AirV2Phase.READY: (AirV2AvailableAction.LEAVE_SURFACE, AirV2AvailableAction.RESET),
        AirV2Phase.DESCENT: (AirV2AvailableAction.REACH_BOTTOM, AirV2AvailableAction.RESET),
        AirV2Phase.BOTTOM: (AirV2AvailableAction.LEAVE_BOTTOM, AirV2AvailableAction.RESET),
        AirV2Phase.TRAVEL_TO_FIRST_STOP: (AirV2AvailableAction.REACH_STOP, AirV2AvailableAction.RESET),
        AirV2Phase.TRAVEL_TO_SURFACE: (AirV2AvailableAction.REACH_SURFACE, AirV2AvailableAction.RESET),
        AirV2Phase.AT_STOP: (AirV2AvailableAction.LEAVE_STOP, AirV2AvailableAction.RESET),
        AirV2Phase.COMPLETE: (AirV2AvailableAction.RESET,),
    }[phase]


def _current_stop_remaining_sec(current_stop, active_timer_elapsed_sec: float | None, phase: AirV2Phase) -> float | None:
    if current_stop is None or active_timer_elapsed_sec is None or phase is not AirV2Phase.AT_STOP:
        return None
    return max((current_stop.duration_min * 60) - active_timer_elapsed_sec, 0.0)
