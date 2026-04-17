from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .profiles import DiveProfile, next_stop_after, no_decompression_limit, stop_by_index

if TYPE_CHECKING:
    from .engine import EngineState


CLEAN_TIME_SEC = 10 * 60


@dataclass(frozen=True)
class Snapshot:
    mode_text: str
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
    remaining_display_text: str
    summary_text: str
    summary_prefix_text: str
    summary_value_text: str
    summary_value_kind: str
    banner_text: str
    banner_kind: str
    detail_text: str
    primary_button_label: str
    secondary_button_label: str
    primary_button_enabled: bool
    secondary_button_enabled: bool


def create_snapshot(state: EngineState, now: datetime) -> Snapshot:
    from . import engine as eng

    phase = state.dive.phase
    if state.deco_mode is None:
        status_text = "RUNNING" if state.stopwatch.running else "READY"
        primary_text = eng.format_tenths(
            state.stopwatch.elapsed_before_start_sec + (now - state.stopwatch.started_at).total_seconds()
            if state.stopwatch.running and state.stopwatch.started_at is not None
            else state.stopwatch.elapsed_before_start_sec
        )
        depth_text = remaining_text = summary_text = ""
        detail_text = "" if state.stopwatch.lap_count == 0 else f"Laps: {state.stopwatch.lap_count}"
        primary_label, secondary_label, primary_enabled, secondary_enabled = (
            "Start/Stop",
            "Lap" if state.stopwatch.running else "Reset",
            True,
            True,
        )
    else:
        view = eng._dive_view(state, now)
        active_break = state.dive.oxygen.active_air_break
        rs = eng.find_latest_event(state.dive.events, "RS")
        clean_remaining = _clean_time_remaining(rs, now)
        status_text = "CLEAN TIME" if phase is eng.DivePhase.SURFACE and clean_remaining is not None else "AT O2 STOP" if view.at_o2_stop else {
            eng.DivePhase.READY: "READY",
            eng.DivePhase.DESCENT: "DESCENT",
            eng.DivePhase.BOTTOM: "BOTTOM",
            eng.DivePhase.TRAVEL: "TRAVELING",
            eng.DivePhase.AT_STOP: "AT STOP",
            eng.DivePhase.SURFACE: "SURFACE",
        }[phase]

        if phase is eng.DivePhase.READY:
            primary_text = "00:00.0"
        elif phase in {eng.DivePhase.DESCENT, eng.DivePhase.BOTTOM}:
            primary_text = eng.format_tenths((now - view.ls.timestamp).total_seconds()) if view.ls is not None else "--:--.-"
        elif view.at_stop:
            if view.awaiting_o2 and view.at_o2_stop:
                tsv_anchor = _transfer_surface_interval_anchor(state)
                primary_text = f"TSV {eng.format_tenths((now - tsv_anchor.timestamp).total_seconds())}" if tsv_anchor is not None else "--:--.-"
            else:
                primary_text = eng.format_tenths((now - (active_break or view.stop_anchor)).total_seconds()) if (active_break or view.stop_anchor) is not None else "--:--.-"
        elif phase is eng.DivePhase.TRAVEL:
            anchor_event = eng._travel_anchor_event(state)
            anchor = anchor_event.timestamp if anchor_event is not None else None
            primary_text = eng.format_tenths((now - anchor).total_seconds()) if anchor is not None else "--:--.-"
        elif phase is eng.DivePhase.SURFACE and clean_remaining is not None:
            primary_text = eng.format_mmss(clean_remaining)
        else:
            primary_text = "SURFACE"

        if phase is eng.DivePhase.SURFACE:
            depth_text = _final_table_schedule(view.profile) or ("Max -- fsw" if view.depth is None else f"{view.depth} fsw")
        elif phase is eng.DivePhase.BOTTOM:
            depth_text = "__ fsw" if view.depth is None else f"{view.depth} fsw"
        elif view.at_stop:
            depth_text = f"{view.current_stop.depth_fsw} fsw" if view.current_stop is not None else "--"
        elif phase in {eng.DivePhase.DESCENT, eng.DivePhase.TRAVEL}:
            estimate = eng.estimate_current_depth(state, now)
            depth_text = f"{estimate} fsw" if estimate is not None else "--"
        elif view.depth is None:
            depth_text = "Max -- fsw"
        else:
            depth_text = f"{view.depth} fsw"

        bottom_depth_timer_text = ""
        if view.air_break_remaining is not None:
            remaining_text = f"Air Break: {eng.format_mmss(view.air_break_remaining)} left"
        elif phase is eng.DivePhase.BOTTOM and view.depth is None:
            remaining_text = ""
            bottom_depth_timer_text = ""
        elif phase is eng.DivePhase.BOTTOM and view.profile is not None:
            if view.ls is None:
                remaining_text = ""
            elif view.profile.is_no_decompression:
                if view.depth is not None and view.depth <= 20:
                    remaining_text = ""
                    bottom_depth_timer_text = ""
                else:
                    limit_min = no_decompression_limit(state.deco_mode, view.depth) if state.deco_mode is not None and view.depth is not None else None
                    if limit_min is None:
                        remaining_text = ""
                    else:
                        remaining = (limit_min * 60) - (now - view.ls.timestamp).total_seconds()
                        remaining_text = f"Bottom: {eng.format_mmss(max(remaining, 0.0))} left"
                        bottom_depth_timer_text = eng.format_mmss(max(remaining, 0.0)) + " remaining"
            elif view.profile.table_bottom_time_min is None:
                remaining_text = ""
            else:
                remaining = (view.profile.table_bottom_time_min * 60) - (now - view.ls.timestamp).total_seconds()
                remaining_text = f"Bottom: {eng.format_mmss(max(remaining, 0.0))} left"
                bottom_depth_timer_text = eng.format_mmss(max(remaining, 0.0)) + " remaining"
        elif view.at_stop:
            remaining_text = "" if view.stop_remaining is None else f"Stop: {eng.format_mmss(view.stop_remaining)} left" if view.stop_remaining >= 0 else f"Stop: +{eng.format_mmss(abs(view.stop_remaining))}"
        else:
            remaining_text = ""

        if phase is eng.DivePhase.SURFACE and clean_remaining is not None:
            summary_text = ""
        elif phase is eng.DivePhase.SURFACE:
            summary_text = ""
        elif phase is eng.DivePhase.BOTTOM and view.depth is None:
            summary_text = "Next: Input Max Depth for table/schedule"
        elif view.profile is None:
            summary_text = "Next: --"
        elif phase is eng.DivePhase.SURFACE or view.profile.is_no_decompression:
            summary_text = "Next: Surface"
        elif view.air_break_remaining is not None:
            summary_text = f"Next: O2 for {eng.format_mmss(view.resume_o2_remaining or 0.0)}"
        elif view.air_break_due is not None and (view.stop_remaining is None or view.stop_remaining > view.air_break_due):
            summary_text = f"Next: Air break in {eng.format_mmss(view.air_break_due)}"
        else:
            summary_text = "Next: Surface" if view.next_stop is None else f"Next: {view.next_stop.depth_fsw} fsw for {view.next_stop.duration_min}m"

        active_hold = eng._active_descent_hold(state)
        detail_text = (
            f"H{active_hold[0]}   {eng.format_mmss((now - active_hold[1]).total_seconds())}" if active_hold is not None else
            f"D{state.dive.active_delay.index} ({state.dive.active_delay.depth_fsw} fsw)   {eng.format_mmss((now - state.dive.active_delay.started_at).total_seconds())}" if state.dive.active_delay is not None else
            "" if active_break is not None else
            ""
        )

        if phase is eng.DivePhase.READY:
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("Leave Surface", "", True, False)
        elif phase is eng.DivePhase.DESCENT:
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("Reach Bottom", "Stop Hold" if active_hold is not None else "Hold", True, True)
        elif phase is eng.DivePhase.BOTTOM:
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("Leave Bottom", "", True, False)
        elif phase is eng.DivePhase.TRAVEL:
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("Reach Surface" if view.next_stop is None else "Reach Stop", "Stop Delay" if state.dive.active_delay is not None else "Delay", True, view.profile is not None)
        elif phase is eng.DivePhase.SURFACE:
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("", "", False, False)
        else:
            secondary_label = "On O2" if view.awaiting_o2 or view.air_break_remaining is not None else "Off O2" if view.can_break else ""
            primary_label, secondary_label, primary_enabled, secondary_enabled = ("Leave Stop", secondary_label, True, bool(secondary_label))

    if state.deco_mode is None:
        status_value_text = status_text.title()
        status_value_kind = "default"
        primary_value_text = primary_text
        primary_value_kind = "default"
        depth_timer_text = ""
        depth_timer_kind = "default"
        remaining_display_text = remaining_text
        summary_prefix_text = summary_text
        summary_value_text = ""
        summary_value_kind = "default"
        banner_text = ""
        banner_kind = "default"
    else:
        if view.air_break_remaining is not None:
            status_value_text, status_value_kind = ("Air Break", "air_break")
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
        primary_value_kind = "air_break" if view.air_break_remaining is not None else "o2" if status_value_kind == "o2" else "default"

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

        remaining_display_text = "Stop elapsed" if view.at_stop and view.stop_remaining is not None and view.stop_remaining < 0 else "" if depth_timer_text else remaining_text

        if view.air_break_due is not None and (view.stop_remaining is None or view.stop_remaining > view.air_break_due):
            summary_prefix_text = "Next: Air break in "
            summary_value_text = eng.format_mmss(view.air_break_due)
            summary_value_kind = "air_break"
        elif view.air_break_remaining is not None:
            summary_prefix_text = "Next: O2 for "
            summary_value_text = eng.format_mmss(view.resume_o2_remaining or 0.0)
            summary_value_kind = "o2"
        elif view.next_stop is not None:
            summary_prefix_text = f"Next: {view.next_stop.depth_fsw} fsw for "
            summary_value_text = f"{view.next_stop.duration_min} min"
            summary_value_kind = "o2" if view.next_stop.gas == "o2" else "default"
        else:
            summary_prefix_text = summary_text
            summary_value_text = ""
            summary_value_kind = "default"

        banner_text = _delay_banner_text(state)
        banner_kind = "delay" if banner_text else "default"

    return Snapshot(
        mode_text="STOPWATCH" if state.deco_mode is None else state.deco_mode.value,
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
        remaining_display_text=remaining_display_text,
        summary_text=summary_text,
        summary_prefix_text=summary_prefix_text,
        summary_value_text=summary_value_text,
        summary_value_kind=summary_value_kind,
        banner_text=banner_text,
        banner_kind=banner_kind,
        detail_text=detail_text,
        primary_button_label=primary_label,
        secondary_button_label=secondary_label,
        primary_button_enabled=primary_enabled,
        secondary_button_enabled=secondary_enabled,
    )


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


def _delay_banner_text(state: EngineState) -> str:
    recompute = state.dive.last_delay_recompute
    if recompute is None or not recompute.schedule_changed:
        return ""
    return f"{_delay_rule_sentence(recompute)}   New profile: {_final_table_schedule(recompute.after_profile)}"


def _delay_rule_sentence(recompute) -> str:
    if recompute.outcome == "add_to_first_stop":
        return "Delay > 1 min, <= 50 fsw"
    if recompute.outcome == "recompute":
        return "Delay > 1 min, > 50 fsw"
    if recompute.outcome == "early_arrival":
        return "Early arrival, profile unchanged"
    if recompute.outcome == "ignore_delay":
        return "Delay did not change profile"
    return "Profile recomputed"
