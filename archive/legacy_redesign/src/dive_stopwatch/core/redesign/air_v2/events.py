from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto


class AirV2EventKind(Enum):
    LEFT_SURFACE = auto()
    REACHED_BOTTOM = auto()
    LEFT_BOTTOM = auto()
    REACHED_STOP = auto()
    LEFT_STOP = auto()
    REACHED_SURFACE = auto()
    INVALID_ACTION = auto()


@dataclass(frozen=True)
class AirV2Event:
    kind: AirV2EventKind
    at: datetime
    detail: str = ""
