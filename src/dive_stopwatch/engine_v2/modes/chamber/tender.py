from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChamberTenderView:
    required_o2_at_30_sec: float
    oxygen_on_ascent: bool
    stay_near_chamber_sec: float
    no_fly_surface_interval_sec: float
