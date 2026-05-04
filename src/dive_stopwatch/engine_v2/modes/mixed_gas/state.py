from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from ...contracts.timers import TimerState


class MixedGasPhase(Enum):
    READY = auto()
    DESCENT_TO_20_ON_AIR = auto()
    AT_20_PREBOTTOM_SHIFT = auto()
    DESCENT_TO_BOTTOM = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    AT_STOP = auto()
    COMPLETE = auto()


class MixedGasBreathingGas(Enum):
    AIR = auto()
    BOTTOM_MIX = auto()
    HELIOX_50_50 = auto()
    OXYGEN = auto()


class MixedGasShiftState(Enum):
    NONE = auto()
    AWAITING_BOTTOM_MIX_CONFIRM = auto()
    ABORT_READY_ON_AIR = auto()
    AWAITING_50_50_CONFIRM = auto()
    AWAITING_O2_CONFIRM = auto()
    OFF_O2 = auto()
    AIR_BREAK = auto()


class MixedGasTimerKind(Enum):
    BOTTOM = auto()
    TRAVEL = auto()
    STOP = auto()
    SHIFT = auto()
    AIR_BREAK = auto()
    CLEAN_TIME = auto()
    GRACE_WINDOW = auto()


@dataclass(frozen=True)
class MixedGasTimer:
    kind: MixedGasTimerKind
    timer: TimerState


@dataclass(frozen=True)
class MixedGasStop:
    index: int
    depth_fsw: int
    gas: str
    duration_min: int


@dataclass(frozen=True)
class MixedGasPlan:
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int | None
    table_bottom_time_min: int | None
    stops: tuple[MixedGasStop, ...]
    is_no_decompression: bool = False


@dataclass(frozen=True)
class MixedGasOxygenState:
    continuous_anchor_at: datetime | None = None


class MixedGasDelayStatus(Enum):
    INACTIVE = auto()
    ACTIVE = auto()
    RESOLVED = auto()


@dataclass(frozen=True)
class MixedGasDelayState:
    status: MixedGasDelayStatus = MixedGasDelayStatus.INACTIVE
    started_at: datetime | None = None
    depth_fsw: int | None = None
    branch: str | None = None
    paused_travel_sec: float = 0.0


@dataclass(frozen=True)
class MixedGasState:
    selected_surd: bool = False
    phase: MixedGasPhase = MixedGasPhase.READY
    depth_text: str = ""
    depth_fsw: int | None = None
    bottom_mix_o2_text: str = ""
    bottom_mix_o2_percent: float | None = None
    breathing_gas: MixedGasBreathingGas = MixedGasBreathingGas.AIR
    shift_state: MixedGasShiftState = MixedGasShiftState.NONE
    active_hold_started_at: datetime | None = None
    hold_elapsed_sec: float = 0.0
    hold_index: int = 0
    surface_timer: MixedGasTimer | None = None
    bottom_timer: MixedGasTimer | None = None
    travel_timer: MixedGasTimer | None = None
    travel_start_depth_fsw: int | None = None
    stop_timer: MixedGasTimer | None = None
    shift_timer: MixedGasTimer | None = None
    interruption_timer: MixedGasTimer | None = None
    air_break_timer: MixedGasTimer | None = None
    clean_time_timer: MixedGasTimer | None = None
    grace_window_timer: MixedGasTimer | None = None
    pending_bottom_anchor_at: datetime | None = None
    plan: MixedGasPlan | None = None
    current_stop_index: int | None = None
    oxygen: MixedGasOxygenState = field(default_factory=MixedGasOxygenState)
    delay: MixedGasDelayState = field(default_factory=MixedGasDelayState)


def make_initial_state() -> MixedGasState:
    return MixedGasState()
