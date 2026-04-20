from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .profiles import DiveProfile, build_profile, next_stop_after, no_decompression_limit, stop_by_index
from .profiles import DelayOutcome

if TYPE_CHECKING:
    from .engine import EngineState


CLEAN_TIME_SEC = 10 * 60


@dataclass(frozen=True)
class Snapshot:
    mode_text: str
    profile_schedule_text: str
    status_text: str
    status_value_text: str
    status_value_kind: str
    primary_text: str
    primary_value_text: str
    primary_value_kind: str
    depth_text: str
    depth_timer_text: str
    depth_timer_kind: str
    remaining_text: str
    summary_text: str
    summary_value_kind: str
    detail_text: str
    primary_button_label: str
    secondary_button_label: str
    primary_button_enabled: bool
    secondary_button_enabled: bool


def create_snapshot(state: EngineState, now: datetime) -> Snapshot:
    from . import engine as eng

    phase = state.dive.phase
    view = eng._dive_view(state, now)
    active_break = state.dive.oxygen.active_air_break
    rs = eng.find_latest_event(state.dive.events, "RS")
    clean_remaining = _clean_time_remaining(rs, now)
    status_text = _build_status_text(eng, phase, clean_remaining, view)
    primary_text = _build_primary_text(eng, state, now, phase, clean_remaining, view, active_break)
    depth_text = _build_depth_text(eng, state, now, phase, view)
    remaining_text, bottom_depth_timer_text = _build_remaining_fields(eng, state, now, phase, view)
    summary_text = _build_summary_text(eng, state, phase, clean_remaining, view)
    detail_text = _build_detail_text(eng, state, now, active_break)
    primary_label, secondary_label, primary_enabled, secondary_enabled = _build_dive_button_fields(
        eng, state, phase, view, active_break
    )

    if view.air_break_remaining is not None:
        status_value_text, status_value_kind = ("Air Break", "air_break")
    elif view.off_o2_stop:
        status_value_text, status_value_kind = ("Off O2", "off_o2")
    elif view.traveling_on_o2:
        status_value_text, status_value_kind = ("On O2/ Traveling", "o2")
    elif view.waiting_at_o2_stop:
        status_value_text, status_value_kind = ("TSV", "default")
    elif view.on_o2_stop:
        status_value_text, status_value_kind = ("On O2", "o2")
    else:
        status_value_text = status_text.title()
        status_value_kind = "default"

    primary_value_text = primary_text.removeprefix("TSV ")
    primary_value_kind = "air_break" if view.air_break_remaining is not None else "off_o2" if view.off_o2_stop else "o2" if status_value_kind == "o2" else "default"

    if view.traveling_on_o2:
        depth_timer_text = _o2_travel_stop_remaining_text(state, now, view.profile)
        depth_timer_kind = "o2" if depth_timer_text else "default"
    else:
        travel_remaining = _travel_remaining_text(state, now, view.profile)
        if travel_remaining is not None and not view.traveling_to_o2:
            depth_timer_text = travel_remaining
            depth_timer_kind = "default"
        elif bottom_depth_timer_text:
            depth_timer_text = bottom_depth_timer_text
            depth_timer_kind = "default"
        elif view.waiting_at_o2_stop and view.current_stop is not None:
            depth_timer_text = f"{view.current_stop.duration_min:02d}:00 left"
            depth_timer_kind = "o2"
        elif view.at_stop and view.stop_remaining is not None:
            depth_timer_text = f"{eng.format_mmss(view.stop_remaining)} left" if view.stop_remaining >= 0 else f"+{eng.format_mmss(abs(view.stop_remaining))}"
            depth_timer_kind = "o2" if view.current_stop is not None and view.current_stop.gas == "o2" else "default"
        elif view.air_break_remaining is not None:
            depth_timer_text = f"{eng.format_mmss(view.air_break_remaining)} left"
            depth_timer_kind = "air_break"
        else:
            depth_timer_text = ""
            depth_timer_kind = "default"

    if view.air_break_due is not None and (view.stop_remaining is None or view.stop_remaining > view.air_break_due):
        summary_value_kind = "air_break"
    elif view.air_break_remaining is not None:
        summary_value_kind = "o2"
    elif view.off_o2_stop:
        summary_value_kind = "o2"
    elif view.next_stop is not None:
        summary_value_kind = "o2" if view.next_stop.gas == "o2" else "default"
    else:
        summary_value_kind = "default"

    return Snapshot(
        mode_text=state.deco_mode.value,
        profile_schedule_text=_final_table_schedule(view.profile),
        status_text=status_text,
        status_value_text=status_value_text,
        status_value_kind=status_value_kind,
        primary_text=primary_text,
        primary_value_text=primary_value_text,
        primary_value_kind=primary_value_kind,
        depth_text=depth_text,
        depth_timer_text=depth_timer_text,
        depth_timer_kind=depth_timer_kind,
        remaining_text=remaining_text,
        summary_text=summary_text,
        summary_value_kind=summary_value_kind,
        detail_text=detail_text,
        primary_button_label=primary_label,
        secondary_button_label=secondary_label,
        primary_button_enabled=primary_enabled,
        secondary_button_enabled=secondary_enabled,
    )


def _build_status_text(eng, phase, clean_remaining: float | None, view) -> str:
    if phase is eng.DivePhase.SURFACE and clean_remaining is not None:
        return "CLEAN TIME"
    if view.at_o2_stop:
        return "AT O2 STOP"
    return {
        eng.DivePhase.READY: "READY",
        eng.DivePhase.DESCENT: "DESCENT",
        eng.DivePhase.BOTTOM: "BOTTOM",
        eng.DivePhase.TRAVEL: "TRAVELING",
        eng.DivePhase.AT_STOP: "AT STOP",
        eng.DivePhase.SURFACE: "SURFACE",
    }[phase]


def _build_primary_text(eng, state: EngineState, now: datetime, phase, clean_remaining: float | None, view, active_break: datetime | None) -> str:
    if phase is eng.DivePhase.READY:
        return "00:00.0"
    if phase in {eng.DivePhase.DESCENT, eng.DivePhase.BOTTOM}:
        return eng.format_tenths((now - view.ls.timestamp).total_seconds()) if view.ls is not None else "--:--.-"
    if view.at_stop:
        if view.awaiting_o2 and view.at_o2_stop:
            tsv_anchor = _transfer_surface_interval_anchor(state)
            return f"TSV {eng.format_tenths((now - tsv_anchor.timestamp).total_seconds())}" if tsv_anchor is not None else "--:--.-"
        if state.dive.oxygen.off_o2_started_at is not None:
            return eng.format_tenths((now - state.dive.oxygen.off_o2_started_at).total_seconds())
        if active_break is not None:
            return eng.format_tenths((now - active_break).total_seconds())
        if view.current_stop is not None and view.stop_remaining is not None:
            elapsed_sec = (view.current_stop.duration_min * 60) - view.stop_remaining
            return eng.format_tenths(max(elapsed_sec, 0.0))
        return eng.format_tenths((now - view.stop_anchor).total_seconds()) if view.stop_anchor is not None else "--:--.-"
    if phase is eng.DivePhase.TRAVEL:
        anchor_event = eng._travel_anchor_event(state)
        anchor = anchor_event.timestamp if anchor_event is not None else None
        return eng.format_tenths((now - anchor).total_seconds()) if anchor is not None else "--:--.-"
    if phase is eng.DivePhase.SURFACE and clean_remaining is not None:
        return eng.format_mmss(clean_remaining)
    return "SURFACE"


def _build_depth_text(eng, state: EngineState, now: datetime, phase, view) -> str:
    if phase is eng.DivePhase.SURFACE:
        return _final_table_schedule(view.profile) or ("Max -- fsw" if view.depth is None else f"{view.depth} fsw")
    if phase is eng.DivePhase.BOTTOM:
        return "__ fsw" if view.depth is None else f"{view.depth} fsw"
    if view.at_stop:
        return f"{view.current_stop.depth_fsw} fsw" if view.current_stop is not None else "--"
    if phase in {eng.DivePhase.DESCENT, eng.DivePhase.TRAVEL}:
        estimate = eng.estimate_current_depth(state, now)
        return f"{estimate} fsw" if estimate is not None else "--"
    if view.depth is None:
        return "Max -- fsw"
    return f"{view.depth} fsw"


def _build_remaining_fields(eng, state: EngineState, now: datetime, phase, view) -> tuple[str, str]:
    bottom_depth_timer_text = ""
    if view.air_break_remaining is not None:
        return f"Air Break: {eng.format_mmss(view.air_break_remaining)} left", bottom_depth_timer_text
    if phase is eng.DivePhase.BOTTOM and view.depth is None:
        return "", bottom_depth_timer_text
    if phase is eng.DivePhase.BOTTOM and view.profile is not None:
        if view.ls is None:
            return "", bottom_depth_timer_text
        if view.profile.is_no_decompression:
            if view.depth is not None and view.depth <= 20:
                return "", bottom_depth_timer_text
            limit_min = no_decompression_limit(state.deco_mode, view.depth) if state.deco_mode is not None and view.depth is not None else None
            if limit_min is None:
                return "", bottom_depth_timer_text
            remaining = (limit_min * 60) - (now - view.ls.timestamp).total_seconds()
            formatted = eng.format_mmss(max(remaining, 0.0))
            return "", formatted + " remaining"
        if view.profile.table_bottom_time_min is None:
            return "", bottom_depth_timer_text
        remaining = (view.profile.table_bottom_time_min * 60) - (now - view.ls.timestamp).total_seconds()
        formatted = eng.format_mmss(max(remaining, 0.0))
        return "", formatted + " remaining"
    if view.at_stop:
        if view.stop_remaining is None:
            return "", bottom_depth_timer_text
        return "", bottom_depth_timer_text
    return "", bottom_depth_timer_text


def _build_summary_text(eng, state: EngineState, phase, clean_remaining: float | None, view) -> str:
    if phase is eng.DivePhase.SURFACE and clean_remaining is not None:
        return ""
    if phase is eng.DivePhase.SURFACE:
        return ""
    if phase is eng.DivePhase.READY:
        preview = _ready_no_decompression_preview(eng, state, view)
        return preview if preview is not None else "Next: --"
    if phase is eng.DivePhase.BOTTOM and view.depth is None:
        return "Next: Input Max Depth for table/schedule"
    if view.profile is None:
        return "Next: --"
    if phase is eng.DivePhase.SURFACE or view.profile.is_no_decompression:
        return "Next: Surface"
    if view.air_break_remaining is not None:
        return f"Next: O2 for {eng.format_mmss(view.resume_o2_remaining or 0.0)}"
    if view.off_o2_stop:
        return "Next: On O2"
    if view.air_break_due is not None and (view.stop_remaining is None or view.stop_remaining > view.air_break_due):
        return f"Next: Air break in {eng.format_mmss(view.air_break_due)}"
    return "Next: Surface" if view.next_stop is None else f"Next: {view.next_stop.depth_fsw} fsw for {view.next_stop.duration_min} min"


def _build_detail_text(eng, state: EngineState, now: datetime, active_break: datetime | None) -> str:
    active_hold = eng._active_descent_hold(state)
    if active_hold is not None:
        return f"H{active_hold[0]}   {eng.format_mmss((now - active_hold[1]).total_seconds())}"
    if state.dive.active_delay is not None:
        return f"D{state.dive.active_delay.index} ({state.dive.active_delay.depth_fsw} fsw)   {eng.format_mmss((now - state.dive.active_delay.started_at).total_seconds())}"
    if active_break is not None:
        return ""
    return ""


def _ready_no_decompression_preview(eng, state: EngineState, view) -> str | None:
    if view.depth is None or state.deco_mode is None:
        return None
    limit_min = no_decompression_limit(state.deco_mode, view.depth)
    if limit_min is None:
        return None
    preview_profile = build_profile(state.deco_mode, view.depth, limit_min)
    repeat_group = f" {preview_profile.repeat_group}" if preview_profile.repeat_group else ""
    return f"No-D Limit: {preview_profile.table_depth_fsw} / {preview_profile.table_bottom_time_min}{repeat_group}"


def _build_dive_button_fields(eng, state: EngineState, phase, view, active_break: datetime | None) -> tuple[str, str, bool, bool]:
    active_hold = eng._active_descent_hold(state)
    if phase is eng.DivePhase.READY:
        return "Leave Surface", "", True, False
    if phase is eng.DivePhase.DESCENT:
        return "Reach Bottom", "Stop Hold" if active_hold is not None else "Hold", True, True
    if phase is eng.DivePhase.BOTTOM:
        return "Leave Bottom", "", True, False
    if phase is eng.DivePhase.TRAVEL:
        return "Reach Surface" if view.next_stop is None else "Reach Stop", "Stop Delay" if state.dive.active_delay is not None else "Delay", True, view.profile is not None
    if phase is eng.DivePhase.SURFACE:
        return "", "", False, False
    if view.off_o2_stop:
        return "Convert to Air", "On O2", True, True
    if view.awaiting_o2 or view.air_break_remaining is not None:
        secondary_label = "On O2"
    elif view.on_o2_stop:
        secondary_label = "Off O2"
    else:
        secondary_label = ""
    return "Leave Stop", secondary_label, True, bool(secondary_label)


def _travel_remaining_text(state: EngineState, now: datetime, profile: DiveProfile | None) -> str | None:
    from . import engine as eng

    if state.dive.phase is not eng.DivePhase.TRAVEL or profile is None or state.dive.current_stop_index is None:
        return None
    current_stop = stop_by_index(profile, state.dive.current_stop_index)
    next_stop = next_stop_after(profile, state.dive.current_stop_index)
    if current_stop is None or next_stop is None:
        return None
    anchor_event = eng._travel_anchor_event(state)
    if anchor_event is None:
        return None
    planned_elapsed_sec = int(abs(current_stop.depth_fsw - next_stop.depth_fsw) * 2)
    elapsed_sec = eng._travel_progress_seconds(state, now, anchor_event.timestamp)
    remaining_sec = max(planned_elapsed_sec - elapsed_sec, 0.0)
    return f"{int(remaining_sec // 60):02d}:{int(remaining_sec % 60):02d} left"


def _o2_travel_stop_remaining_text(state: EngineState, now: datetime, profile: DiveProfile | None) -> str | None:
    from . import engine as eng

    if state.dive.phase is not eng.DivePhase.TRAVEL or profile is None or state.dive.current_stop_index is None:
        return None
    current_stop = stop_by_index(profile, state.dive.current_stop_index)
    next_stop = next_stop_after(profile, state.dive.current_stop_index)
    if current_stop is None or next_stop is None or current_stop.gas != "o2" or next_stop.gas != "o2":
        return None
    anchor_event = eng._travel_anchor_event(state)
    if anchor_event is None:
        return None
    elapsed_sec = eng._travel_progress_seconds(state, now, anchor_event.timestamp)
    remaining_sec = max((next_stop.duration_min * 60) - elapsed_sec, 0.0)
    return f"{int(remaining_sec // 60):02d}:{int(remaining_sec % 60):02d} left"


def _transfer_surface_interval_anchor(state: EngineState):
    from . import engine as eng

    if state.dive.current_stop_index is None:
        return eng.find_latest_event(state.dive.events, "LB")
    if state.dive.current_stop_index == 1:
        current_stop = stop_by_index(state.dive.profile, 1) if state.dive.profile is not None else None
        if current_stop is not None and current_stop.gas == "o2":
            return eng.find_latest_event(state.dive.events, "R1")
        return eng.find_latest_event(state.dive.events, "LB")
    return eng.find_latest_event(state.dive.events, f"L{state.dive.current_stop_index - 1}")


def _clean_time_remaining(rs, now: datetime) -> float | None:
    if rs is None:
        return None
    remaining = CLEAN_TIME_SEC - max((now - rs.timestamp).total_seconds(), 0.0)
    return remaining if remaining > 0 else None


def _final_table_schedule(profile: DiveProfile | None) -> str:
    if profile is None or profile.table_bottom_time_min is None:
        return ""
    repeat_group = f" {profile.repeat_group}" if profile.repeat_group else ""
    return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}{repeat_group}"
