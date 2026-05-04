from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from ...contracts.surd_handoff import InWaterToSurdHandoff
from ...contracts.timers import TimerState
from .plan import SurdChamberPlan, SurdPenaltyKind


class SurdPhase(Enum):
    READY = auto()
    SURFACE_ASCENT_FROM_WATER_STOP = auto()
    SURFACE_UNDRESS = auto()
    SURFACE_TO_CHAMBER_50 = auto()
    SURFACE_INTERVAL_EXCEEDED = auto()
    CHAMBER_AT_50_WAITING_O2 = auto()
    CHAMBER_TRAVEL_TO_STOP = auto()
    CHAMBER_ON_O2 = auto()
    CHAMBER_OFF_O2 = auto()
    CHAMBER_AIR_BREAK = auto()
    CHAMBER_READY_TO_MOVE = auto()
    CHAMBER_TRAVEL_TO_SURFACE = auto()
    COMPLETE_CLEAN_TIME = auto()
    COMPLETE_DONE = auto()


@dataclass(frozen=True)
class SurdState:
    phase: SurdPhase = SurdPhase.READY
    handoff: InWaterToSurdHandoff | None = None
    penalty_kind: SurdPenaltyKind = SurdPenaltyKind.NONE
    surface_interval_timer: TimerState | None = None
    surface_ascent_timer: TimerState | None = None
    undress_timer: TimerState | None = None
    to_chamber_timer: TimerState | None = None
    chamber_travel_timer: TimerState | None = None
    chamber_travel_from_depth_fsw: int | None = None
    chamber_surface_ascent_timer: TimerState | None = None
    chamber_surface_ascent_from_depth_fsw: int | None = None
    chamber_surface_ascent_on_o2: bool | None = None
    move_ready_timer: TimerState | None = None
    o2_timer: TimerState | None = None
    continuous_o2_anchor_at: datetime | None = None
    off_o2_timer: TimerState | None = None
    air_break_timer: TimerState | None = None
    clean_time_timer: TimerState | None = None
    chamber_plan: SurdChamberPlan | None = None
    current_segment_index: int | None = None


def make_initial_state() -> SurdState:
    return SurdState()
