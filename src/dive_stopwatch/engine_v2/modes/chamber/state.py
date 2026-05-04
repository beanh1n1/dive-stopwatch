from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from ...contracts.chamber_handoff import SurdToChamberHandoff
from ...contracts.timers import TimerState


class ChamberPhase(Enum):
    READY = auto()
    DESCENT_TO_60 = auto()
    AT_STOP = auto()
    ON_O2 = auto()
    AIR_BREAK = auto()
    TRAVEL_TO_30 = auto()
    TRAVEL_TO_SURFACE = auto()
    COMPLETE_CLEAN_TIME = auto()
    COMPLETE_DONE = auto()


class ChamberGasState(Enum):
    AIR = auto()
    WAITING_ON_O2 = auto()
    ON_O2 = auto()
    AIR_BREAK = auto()


@dataclass(frozen=True)
class ChamberState:
    phase: ChamberPhase = ChamberPhase.READY
    gas_state: ChamberGasState = ChamberGasState.AIR
    selected_table: str | None = None
    treatment_handoff: SurdToChamberHandoff | None = None
    current_depth_fsw: int | None = 0
    stop_depth_fsw: int | None = None
    ready_on_o2: bool = False
    descent_timer: TimerState | None = None
    stop_wait_timer: TimerState | None = None
    o2_timer: TimerState | None = None
    air_break_timer: TimerState | None = None
    clean_time_timer: TimerState | None = None
    travel_timer: TimerState | None = None
    travel_from_depth_fsw: int | None = None
    travel_to_depth_fsw: int | None = None
    travel_rate_fpm: float | None = None
    o2_periods_60_completed: int = 0
    o2_periods_30_completed: int = 0
    pending_arrival_break_at_30: bool = False
    final_ascent_o2_ready_at_30: bool = False


def make_initial_state() -> ChamberState:
    return ChamberState()
