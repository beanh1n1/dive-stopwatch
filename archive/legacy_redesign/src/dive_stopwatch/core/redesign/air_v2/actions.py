from __future__ import annotations

from enum import Enum, auto


class AirV2Action(Enum):
    LEAVE_SURFACE = auto()
    REACH_BOTTOM = auto()
    LEAVE_BOTTOM = auto()
    REACH_STOP = auto()
    LEAVE_STOP = auto()
    CONFIRM_ON_O2 = auto()
    TOGGLE_OFF_O2 = auto()
    TOGGLE_DELAY = auto()
    CONVERT_TO_AIR = auto()
    REACH_SURFACE = auto()
    RESET = auto()
