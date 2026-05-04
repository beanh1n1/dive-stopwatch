from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from ...air_o2_profiles import DecoMode, DiveProfile
from .events import AirV2Event


class AirV2Phase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    AT_STOP = auto()
    COMPLETE = auto()


class AirV2GasState(Enum):
    AIR = auto()
    WAITING_ON_O2 = auto()
    ON_O2 = auto()
    OFF_O2 = auto()
    AIR_BREAK = auto()


class AirV2Obligation(Enum):
    NONE = auto()
    LEAVE_SURFACE = auto()
    REACH_BOTTOM = auto()
    LEAVE_BOTTOM = auto()
    REACH_STOP = auto()
    REACH_SURFACE = auto()
    LEAVE_STOP = auto()


class AirV2TimerKind(Enum):
    BOTTOM = auto()
    TRAVEL = auto()
    STOP = auto()


class AirV2AvailableAction(Enum):
    LEAVE_SURFACE = auto()
    REACH_BOTTOM = auto()
    LEAVE_BOTTOM = auto()
    REACH_STOP = auto()
    REACH_SURFACE = auto()
    LEAVE_STOP = auto()
    RESET = auto()


@dataclass(frozen=True)
class AirV2Timer:
    kind: AirV2TimerKind
    started_at: datetime


@dataclass(frozen=True)
class AirV2Plan:
    profile: DiveProfile
    current_stop_index: int | None = None


@dataclass(frozen=True)
class AirV2State:
    mode: DecoMode
    phase: AirV2Phase = AirV2Phase.READY
    depth_text: str = ""
    depth_fsw: int | None = None
    gas_state: AirV2GasState = AirV2GasState.AIR
    active_timer: AirV2Timer | None = None
    plan: AirV2Plan | None = None
    events: tuple[AirV2Event, ...] = field(default_factory=tuple)


def make_initial_state(*, mode: DecoMode = DecoMode.AIR, depth_text: str = "", depth_fsw: int | None = None) -> AirV2State:
    return AirV2State(mode=mode, depth_text=depth_text, depth_fsw=depth_fsw)
