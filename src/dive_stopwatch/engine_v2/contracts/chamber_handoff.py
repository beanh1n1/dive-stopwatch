from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .events import AuditEvent
from .surd_handoff import SurdEntryKind


@dataclass(frozen=True)
class SurdToChamberHandoff:
    trigger: str
    surface_interval_elapsed_sec: float
    entry_depth_fsw: int
    source_entry_kind: SurdEntryKind
    input_depth_fsw: int
    input_bottom_time_min: int
    handed_off_at: datetime
    audit_tail: tuple[AuditEvent, ...] = ()
