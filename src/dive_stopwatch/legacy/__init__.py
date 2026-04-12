"""Minimal legacy compatibility surface kept during v2 transition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AirBreakEvent:
    kind: str
    index: int
    timestamp: datetime
    depth_fsw: int
    stop_number: int


__all__ = ["AirBreakEvent"]
