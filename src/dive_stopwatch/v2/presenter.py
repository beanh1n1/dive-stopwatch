from __future__ import annotations

import math
from datetime import datetime

from .dive_controller import DivePhase
from .models import SnapshotV2, StateV2, StatusV2
from .stopwatch_core import format_hhmmss


def format_tenths(seconds: float) -> str:
    clamped = max(seconds, 0.0)
    total_tenths = math.floor((clamped * 10) + 1e-9)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"


def status_from_state(state: StateV2, *, now: datetime, at_o2_stop: bool) -> StatusV2:
    if state.mode.name == "STOPWATCH":
        return StatusV2.RUNNING if state.stopwatch.running else StatusV2.READY

    phase = state.dive.phase
    if phase is DivePhase.READY:
        return StatusV2.READY
    if phase is DivePhase.DESCENT:
        return StatusV2.DESCENT
    if phase is DivePhase.BOTTOM:
        return StatusV2.BOTTOM
    if phase is DivePhase.CLEAN_TIME:
        return StatusV2.SURFACE
    if phase is DivePhase.ASCENT and state.dive._at_stop:
        return StatusV2.AT_O2_STOP if at_o2_stop else StatusV2.AT_STOP
    return StatusV2.TRAVELING


def build_snapshot(
    *,
    state: StateV2,
    now: datetime,
    status: StatusV2,
    timer_kind: str,
    primary_text: str,
    depth_text: str,
    remaining_text: str,
    summary_text: str,
    summary_targets_oxygen_stop: bool,
    detail_text: str,
    start_label: str,
    secondary_label: str,
    start_enabled: bool,
    secondary_enabled: bool,
) -> SnapshotV2:
    mode_text = "STOPWATCH" if state.mode.name == "STOPWATCH" else "DIVE"
    return SnapshotV2(
        mode_text=mode_text,
        deco_mode_text=state.deco_mode.value,
        status=status,
        timer_kind=timer_kind,
        primary=primary_text,
        depth=depth_text,
        remaining=remaining_text,
        summary=summary_text,
        summary_targets_oxygen_stop=summary_targets_oxygen_stop,
        detail=detail_text,
        start_label=start_label,
        secondary_label=secondary_label,
        start_enabled=start_enabled,
        secondary_enabled=secondary_enabled,
    )


def stopwatch_primary_text(state: StateV2) -> str:
    return format_hhmmss(state.stopwatch.display_time())
