from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from .dive_controller import DiveController
from .stopwatch_core import Stopwatch
from .tables import DecompressionMode


class ModeV2(Enum):
    STOPWATCH = auto()
    DIVE = auto()


class IntentV2(Enum):
    PRIMARY = auto()
    SECONDARY = auto()
    MODE = auto()
    RESET = auto()


class StatusV2(str, Enum):
    READY = "READY"
    DESCENT = "DESCENT"
    BOTTOM = "BOTTOM"
    TRAVELING = "TRAVELING"
    AT_STOP = "AT STOP"
    AT_O2_STOP = "AT O2 STOP"
    SURFACE = "SURFACE"
    RUNNING = "RUNNING"


@dataclass(frozen=True)
class AirBreakEventV2:
    kind: str
    index: int
    timestamp: datetime
    depth_fsw: int
    stop_number: int


@dataclass
class StateV2:
    mode: ModeV2 = ModeV2.STOPWATCH
    deco_mode: DecompressionMode = DecompressionMode.AIR
    stopwatch: Stopwatch = field(default_factory=Stopwatch)
    dive: DiveController = field(default_factory=DiveController)
    depth_text: str = ""
    first_o2_confirmed_at: datetime | None = None
    first_o2_confirmed_stop_number: int | None = None
    oxygen_segment_started_at: datetime | None = None
    air_break_events: list[AirBreakEventV2] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)

    def parsed_depth(self) -> int | None:
        raw = self.depth_text.strip()
        if not raw:
            return None
        try:
            depth = int(raw)
        except ValueError:
            return None
        return depth if depth > 0 else None


@dataclass(frozen=True)
class SnapshotV2:
    mode_text: str
    deco_mode_text: str
    status: StatusV2
    timer_kind: str
    primary: str
    depth: str
    remaining: str
    summary: str
    summary_targets_oxygen_stop: bool
    detail: str
    start_label: str
    secondary_label: str
    start_enabled: bool
    secondary_enabled: bool
