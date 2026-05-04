from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from .events import AuditEvent


class SurdEntryKind(Enum):
    L40_NORMAL = auto()
    ADAPTER_30_20 = auto()
    SURFACE_DIRECT = auto()


@dataclass(frozen=True)
class InWaterToSurdHandoff:
    entry_kind: SurdEntryKind
    source_mode: str
    input_depth_fsw: int
    input_bottom_time_min: int
    source_table_depth_fsw: int | None
    source_table_bottom_time_min: int | None
    left_water_stop_depth_fsw: int | None
    remaining_in_water_obligation_sec: float | None
    handed_off_at: datetime
    audit_tail: tuple[AuditEvent, ...] = ()


__all__ = ["InWaterToSurdHandoff", "SurdEntryKind"]
