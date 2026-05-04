from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from ...domain.air_o2_profiles import DecoMode, DelayOutcome, DiveProfile
from ...contracts.timers import TimerState


class AirPhase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    AT_STOP = auto()
    COMPLETE = auto()


class AirGasState(Enum):
    AIR = auto()
    WAITING_ON_O2 = auto()
    ON_O2 = auto()
    INTERRUPTED_O2 = auto()
    AIR_BREAK = auto()


class AirTimerKind(Enum):
    BOTTOM = auto()
    TRAVEL = auto()
    STOP = auto()
    TSV = auto()
    INTERRUPTION = auto()
    AIR_BREAK = auto()
    CLEAN_TIME = auto()


@dataclass(frozen=True)
class AirTimer:
    kind: AirTimerKind
    timer: TimerState


@dataclass(frozen=True)
class AirPlan:
    profile: DiveProfile
    current_stop_index: int | None = None


class AirDelayStatus(Enum):
    INACTIVE = auto()
    ACTIVE = auto()
    RESOLVED = auto()


@dataclass(frozen=True)
class AirDelayState:
    status: AirDelayStatus = AirDelayStatus.INACTIVE
    started_at: datetime | None = None
    depth_fsw: int | None = None
    outcome: DelayOutcome | None = None
    paused_travel_sec: float = 0.0


@dataclass(frozen=True)
class AirOxygenState:
    first_confirmed_at: datetime | None = None
    continuous_anchor_at: datetime | None = None


@dataclass(frozen=True)
class AirState:
    mode: DecoMode
    selected_surd: bool = False
    phase: AirPhase = AirPhase.READY
    depth_text: str = ""
    depth_fsw: int | None = None
    gas_state: AirGasState = AirGasState.AIR
    active_hold_started_at: datetime | None = None
    hold_elapsed_sec: float = 0.0
    hold_index: int = 0
    surface_timer: AirTimer | None = None
    bottom_timer: AirTimer | None = None
    travel_timer: AirTimer | None = None
    stop_timer: AirTimer | None = None
    tsv_timer: AirTimer | None = None
    interruption_timer: AirTimer | None = None
    air_break_timer: AirTimer | None = None
    clean_time_timer: AirTimer | None = None
    plan: AirPlan | None = None
    oxygen: AirOxygenState = field(default_factory=AirOxygenState)
    delay: AirDelayState = field(default_factory=AirDelayState)
    audit_offset: int = 0


def make_initial_state(
    *,
    mode: DecoMode,
    selected_surd: bool = False,
    depth_text: str = "",
    depth_fsw: int | None = None,
) -> AirState:
    return AirState(mode=mode, selected_surd=selected_surd, depth_text=depth_text, depth_fsw=depth_fsw)
