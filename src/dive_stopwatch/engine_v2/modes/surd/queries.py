from __future__ import annotations

from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.view import EngineMode, EngineView, ObligationKind, TimerRole, TimerView, WarningKind
from ...domain.depth import linear_depth_fsw
from .rules import (
    SURD_AIR_BREAK_SEC,
    SURD_CLEAN_TIME_SEC,
    SURD_CHAMBER_ASCENT_FSW_PER_SEC,
    SURD_ASCENT_SEC,
    SURD_CHAMBER_TRAVEL_SEC,
    SURD_O2_BREAK_TRIGGER_SEC,
    SURD_SURFACE_INTERVAL_NORMAL_SEC,
    SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC,
    SURD_TO_CHAMBER_50_SEC,
    air_break_due,
    current_segment,
    elapsed,
    next_segment,
)
from .plan import SurdPenaltyKind
from .state import SurdPhase, SurdState


def derive_view(state: SurdState, now: datetime) -> EngineView:
    seg = current_segment(state)
    next_seg = next_segment(state)
    show_air_break_next = _show_air_break_next(state, now, seg, next_seg)
    next_depth_fsw = None if show_air_break_next else (None if next_seg is None else next_seg.depth_fsw)
    next_duration_min = None if show_air_break_next else (None if next_seg is None else int(next_seg.duration_sec / 60))
    return EngineView(
        mode=EngineMode.SURD,
        phase_name=state.phase.name,
        gas_state_name=_gas_state_name(state),
        committed_depth_fsw=None,
        display_depth_fsw=_display_depth_fsw(state, now, seg),
        obligation=_obligation(state, now),
        active_timer=_active_timer(state, now, seg),
        next_stop_depth_fsw=next_depth_fsw,
        next_stop_duration_min=next_duration_min,
        current_stop_depth_fsw=None if seg is None else seg.depth_fsw,
        current_stop_remaining_sec=_current_remaining(state, now, seg),
        available_actions=tuple(action.name for action in _available_actions(state, now)),
        warnings=_warnings(state, now),
        pending_action_text=_pending_action_text(state, now, seg, next_seg, show_air_break_next),
    )


def _gas_state_name(state: SurdState) -> str:
    return {
        SurdPhase.READY: "SURFACE",
        SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP: "SURFACE",
        SurdPhase.SURFACE_UNDRESS: "SURFACE",
        SurdPhase.SURFACE_TO_CHAMBER_50: "SURFACE",
        SurdPhase.SURFACE_INTERVAL_EXCEEDED: "SURFACE",
        SurdPhase.CHAMBER_AT_50_WAITING_O2: "WAITING_ON_O2",
        SurdPhase.CHAMBER_TRAVEL_TO_STOP: "AIR_BREAK" if state.air_break_timer is not None else "ON_O2",
        SurdPhase.CHAMBER_ON_O2: "ON_O2",
        SurdPhase.CHAMBER_OFF_O2: "OFF_O2",
        SurdPhase.CHAMBER_AIR_BREAK: "AIR_BREAK",
        SurdPhase.CHAMBER_READY_TO_MOVE: "OFF_O2",
        SurdPhase.CHAMBER_TRAVEL_TO_SURFACE: "ON_O2" if state.chamber_surface_ascent_on_o2 else "OFF_O2",
        SurdPhase.COMPLETE_CLEAN_TIME: "CLEAN_TIME",
        SurdPhase.COMPLETE_DONE: "COMPLETE",
    }[state.phase]


def _obligation(state: SurdState, now: datetime) -> ObligationKind:
    seg = current_segment(state)
    next_seg = next_segment(state)
    if state.phase is SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP:
        return ObligationKind.REACH_SURFACE
    if state.phase is SurdPhase.SURFACE_UNDRESS:
        return ObligationKind.LEAVE_SURFACE
    if state.phase is SurdPhase.SURFACE_TO_CHAMBER_50:
        return ObligationKind.REACH_CHAMBER_50
    if state.phase is SurdPhase.SURFACE_INTERVAL_EXCEEDED:
        return ObligationKind.NONE
    if state.phase is SurdPhase.CHAMBER_AT_50_WAITING_O2:
        return ObligationKind.CONFIRM_ON_O2
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_STOP:
        return ObligationKind.REACH_STOP
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE:
        return ObligationKind.REACH_SURFACE
    if state.phase is SurdPhase.CHAMBER_READY_TO_MOVE:
        return ObligationKind.MOVE_CHAMBER
    if state.phase is SurdPhase.CHAMBER_ON_O2 and seg is not None and state.o2_timer is not None:
        if elapsed(state.o2_timer, now) < seg.duration_sec:
            return ObligationKind.NONE
        if next_seg is None:
            return ObligationKind.COMPLETE_TO_SURFACE
        if air_break_due(state, now):
            return ObligationKind.START_AIR_BREAK
        return ObligationKind.MOVE_CHAMBER
    if state.phase is SurdPhase.CHAMBER_OFF_O2 and seg is not None and state.o2_timer is not None:
        if elapsed(state.o2_timer, now) >= seg.duration_sec:
            if next_seg is None:
                return ObligationKind.COMPLETE_TO_SURFACE
            if not air_break_due(state, now):
                return ObligationKind.MOVE_CHAMBER
        return ObligationKind.CONFIRM_ON_O2
    if state.phase is SurdPhase.CHAMBER_AIR_BREAK and state.air_break_timer is not None:
        if elapsed(state.air_break_timer, now) < SURD_AIR_BREAK_SEC:
            return ObligationKind.MOVE_CHAMBER if seg is not None and next_seg is not None and next_seg.depth_fsw != seg.depth_fsw else ObligationKind.NONE
        return ObligationKind.END_AIR_BREAK
    return ObligationKind.NONE


def _available_actions(state: SurdState, now: datetime) -> tuple[EngineAction, ...]:
    seg = current_segment(state)
    next_seg = next_segment(state)
    if state.phase is SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP:
        return (EngineAction.REACH_SURFACE, EngineAction.RESET)
    if state.phase is SurdPhase.SURFACE_UNDRESS:
        return (EngineAction.LEAVE_SURFACE, EngineAction.RESET)
    if state.phase is SurdPhase.SURFACE_TO_CHAMBER_50:
        return (EngineAction.REACH_CHAMBER_50, EngineAction.RESET)
    if state.phase is SurdPhase.SURFACE_INTERVAL_EXCEEDED:
        return (EngineAction.RESET,)
    if state.phase is SurdPhase.CHAMBER_AT_50_WAITING_O2:
        return (EngineAction.CONFIRM_ON_O2, EngineAction.RESET)
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_STOP:
        return (EngineAction.REACH_STOP, EngineAction.RESET)
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE:
        return (EngineAction.REACH_SURFACE, EngineAction.RESET)
    if state.phase is SurdPhase.CHAMBER_READY_TO_MOVE:
        return (EngineAction.MOVE_CHAMBER, EngineAction.RESET)
    if state.phase is SurdPhase.CHAMBER_ON_O2 and seg is not None and state.o2_timer is not None:
        actions = [EngineAction.TOGGLE_OFF_O2, EngineAction.RESET]
        if elapsed(state.o2_timer, now) >= seg.duration_sec:
            if next_seg is None:
                actions.insert(0, EngineAction.COMPLETE_TO_SURFACE)
            elif air_break_due(state, now):
                actions.insert(0, EngineAction.START_AIR_BREAK)
            else:
                actions.insert(0, EngineAction.MOVE_CHAMBER)
        return tuple(actions)
    if state.phase is SurdPhase.CHAMBER_OFF_O2 and seg is not None and state.o2_timer is not None:
        actions = [EngineAction.TOGGLE_OFF_O2, EngineAction.RESET]
        if elapsed(state.o2_timer, now) >= seg.duration_sec:
            if next_seg is None:
                actions.insert(0, EngineAction.COMPLETE_TO_SURFACE)
            elif not air_break_due(state, now):
                actions.insert(0, EngineAction.MOVE_CHAMBER)
        return tuple(actions)
    if state.phase is SurdPhase.CHAMBER_AIR_BREAK and state.air_break_timer is not None:
        actions = [EngineAction.RESET]
        if seg is not None and next_seg is not None and next_seg.depth_fsw != seg.depth_fsw:
            actions.insert(0, EngineAction.MOVE_CHAMBER)
        if elapsed(state.air_break_timer, now) >= SURD_AIR_BREAK_SEC:
            insert_index = 1 if actions and actions[0] is EngineAction.MOVE_CHAMBER else 0
            actions.insert(insert_index, EngineAction.END_AIR_BREAK)
        return tuple(actions)
    return (EngineAction.RESET,)


def _active_timer(state: SurdState, now: datetime, seg) -> TimerView | None:
    if state.phase in {SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP, SurdPhase.SURFACE_UNDRESS, SurdPhase.SURFACE_TO_CHAMBER_50, SurdPhase.SURFACE_INTERVAL_EXCEEDED, SurdPhase.CHAMBER_AT_50_WAITING_O2} and state.surface_interval_timer is not None:
        return TimerView(role=TimerRole.SURFACE_INTERVAL, elapsed_sec=elapsed(state.surface_interval_timer, now))
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_STOP and state.air_break_timer is not None:
        air_elapsed = elapsed(state.air_break_timer, now)
        return TimerView(role=TimerRole.AIR_BREAK, elapsed_sec=air_elapsed, remaining_sec=max(SURD_AIR_BREAK_SEC - air_elapsed, 0.0))
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_STOP and state.o2_timer is not None and seg is not None:
        o2_elapsed = elapsed(state.o2_timer, now)
        return TimerView(role=TimerRole.CHAMBER_SEGMENT, elapsed_sec=o2_elapsed, remaining_sec=max(seg.duration_sec - o2_elapsed, 0.0))
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE and state.chamber_surface_ascent_timer is not None:
        return TimerView(role=TimerRole.TRAVEL, elapsed_sec=elapsed(state.chamber_surface_ascent_timer, now))
    if state.phase is SurdPhase.CHAMBER_READY_TO_MOVE and state.move_ready_timer is not None:
        return TimerView(role=TimerRole.CHAMBER_SEGMENT, elapsed_sec=elapsed(state.move_ready_timer, now))
    if state.phase is SurdPhase.CHAMBER_ON_O2 and state.o2_timer is not None and seg is not None:
        o2_elapsed = elapsed(state.o2_timer, now)
        return TimerView(role=TimerRole.CHAMBER_SEGMENT, elapsed_sec=o2_elapsed, remaining_sec=max(seg.duration_sec - o2_elapsed, 0.0))
    if state.phase is SurdPhase.CHAMBER_OFF_O2 and state.off_o2_timer is not None:
        return TimerView(role=TimerRole.CHAMBER_SEGMENT, elapsed_sec=elapsed(state.off_o2_timer, now))
    if state.phase is SurdPhase.CHAMBER_AIR_BREAK and state.air_break_timer is not None:
        air_elapsed = elapsed(state.air_break_timer, now)
        return TimerView(role=TimerRole.AIR_BREAK, elapsed_sec=air_elapsed, remaining_sec=max(SURD_AIR_BREAK_SEC - air_elapsed, 0.0))
    if state.phase is SurdPhase.COMPLETE_CLEAN_TIME and state.clean_time_timer is not None:
        clean_elapsed = elapsed(state.clean_time_timer, now)
        return TimerView(role=TimerRole.CLEAN_TIME, elapsed_sec=clean_elapsed, remaining_sec=max(SURD_CLEAN_TIME_SEC - clean_elapsed, 0.0))
    return None


def _current_remaining(state: SurdState, now: datetime, seg) -> float | None:
    if seg is None or state.o2_timer is None or state.phase not in {SurdPhase.CHAMBER_TRAVEL_TO_STOP, SurdPhase.CHAMBER_ON_O2, SurdPhase.CHAMBER_OFF_O2}:
        return None
    return max(seg.duration_sec - elapsed(state.o2_timer, now), 0.0)


def _warnings(state: SurdState, now: datetime) -> tuple[WarningKind, ...]:
    if air_break_due(state, now):
        return (WarningKind.AIR_BREAK_DUE,)
    if state.surface_interval_timer is None:
        return (WarningKind.NONE,)
    interval_elapsed = elapsed(state.surface_interval_timer, now)
    if interval_elapsed > SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC or state.penalty_kind is SurdPenaltyKind.EXCEEDED:
        return (WarningKind.SURFACE_INTERVAL_EXCEEDED,)
    if interval_elapsed > SURD_SURFACE_INTERVAL_NORMAL_SEC or state.penalty_kind is SurdPenaltyKind.PLUS_15_AT_50:
        return (WarningKind.SURFACE_INTERVAL_PENALTY,)
    return (WarningKind.NONE,)


def _display_depth_fsw(state: SurdState, now: datetime, seg) -> int | None:
    if state.phase is SurdPhase.READY:
        return 0
    if state.phase is SurdPhase.SURFACE_ASCENT_FROM_WATER_STOP and state.surface_ascent_timer is not None and state.handoff is not None:
        return linear_depth_fsw(
            start_depth_fsw=state.handoff.left_water_stop_depth_fsw,
            end_depth_fsw=0,
            elapsed_sec=elapsed(state.surface_ascent_timer, now),
            rate_fsw_per_sec=state.handoff.left_water_stop_depth_fsw / max(SURD_ASCENT_SEC, 1),
        )
    if state.phase in {
        SurdPhase.SURFACE_UNDRESS,
        SurdPhase.SURFACE_INTERVAL_EXCEEDED,
        SurdPhase.COMPLETE_CLEAN_TIME,
        SurdPhase.COMPLETE_DONE,
    }:
        return 0
    if state.phase is SurdPhase.SURFACE_TO_CHAMBER_50 and state.to_chamber_timer is not None:
        return linear_depth_fsw(
            start_depth_fsw=0,
            end_depth_fsw=50,
            elapsed_sec=elapsed(state.to_chamber_timer, now),
            rate_fsw_per_sec=50 / max(SURD_TO_CHAMBER_50_SEC, 1),
        )
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_STOP and state.chamber_travel_timer is not None and seg is not None and state.chamber_travel_from_depth_fsw is not None:
        return linear_depth_fsw(
            start_depth_fsw=state.chamber_travel_from_depth_fsw,
            end_depth_fsw=seg.depth_fsw,
            elapsed_sec=elapsed(state.chamber_travel_timer, now),
            rate_fsw_per_sec=abs(state.chamber_travel_from_depth_fsw - seg.depth_fsw) / max(SURD_CHAMBER_TRAVEL_SEC, 1),
        )
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE and state.chamber_surface_ascent_timer is not None and state.chamber_surface_ascent_from_depth_fsw is not None:
        return linear_depth_fsw(
            start_depth_fsw=state.chamber_surface_ascent_from_depth_fsw,
            end_depth_fsw=0,
            elapsed_sec=elapsed(state.chamber_surface_ascent_timer, now),
            rate_fsw_per_sec=SURD_CHAMBER_ASCENT_FSW_PER_SEC,
        )
    if seg is not None:
        return seg.depth_fsw
    return 50


def _show_air_break_next(state: SurdState, now: datetime, seg, next_seg) -> bool:
    return bool(
        state.phase is SurdPhase.CHAMBER_ON_O2
        and seg is not None
        and next_seg is not None
        and state.o2_timer is not None
        and elapsed(state.o2_timer, now) >= seg.duration_sec
        and air_break_due(state, now)
    )


def _pending_action_text(state: SurdState, now: datetime, seg, next_seg, show_air_break_next: bool) -> str | None:
    if show_air_break_next:
        return "Air Break for 5 min"
    if state.phase is SurdPhase.CHAMBER_TRAVEL_TO_SURFACE:
        return "Reach Surface"
    if (
        state.phase is SurdPhase.CHAMBER_ON_O2
        and seg is not None
        and next_seg is not None
        and seg.duration_sec >= SURD_O2_BREAK_TRIGGER_SEC
    ):
        return "Air Break for 5 min"
    return None
