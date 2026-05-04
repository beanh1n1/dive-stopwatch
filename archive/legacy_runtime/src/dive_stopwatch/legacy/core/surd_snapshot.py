from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SurfaceSnapshot:
    mode_text: str
    status_text: str
    status_value_kind: str
    primary_text: str
    primary_value_kind: str
    depth_text: str
    summary_text: str
    summary_value_kind: str
    detail_text: str
    detail_kind: str
    primary_button_label: str
    secondary_button_label: str
    primary_button_enabled: bool
    secondary_button_enabled: bool


def build_surd_snapshot(
    *,
    state,
    elapsed_sec: float,
    format_tenths: Callable[[float], str],
    format_mmss: Callable[[float], str],
    l40_to_surface_sec: int,
    max_surface_interval_sec: int,
    undress_sec: int,
    chamber_air_break_sec: int,
    surface_interval_penalty_max_sec: int,
    clean_time_sec: int,
    current_surd_o2_segment: Callable[[object], object | None],
    next_surd_o2_segment: Callable[[object], object | None],
    current_o2_summary: Callable[[object | None], str],
    current_o2_elapsed_sec: Callable[[object, float], float],
    off_o2_elapsed_sec: Callable[[object, float], float],
) -> SurfaceSnapshot:
    phase_name = state.phase.name
    primary_text = format_tenths(elapsed_sec)
    primary_value_kind = "default"
    summary_text = "Surface decompression draft"
    summary_value_kind = "default"
    depth_text = "SURFACE"
    detail_text = ""
    detail_kind = "default"
    primary_button_label = ""
    secondary_button_label = ""
    primary_button_enabled = False
    secondary_button_enabled = False
    status_text = "CLEAN TIME" if phase_name == "COMPLETE" else phase_name.replace("_", " ")
    status_value_kind = "default"
    if phase_name == "SURFACE_INTERVAL" and state.handoff is not None:
        subphase_name = getattr(state.interval_subphase, "name", "ASCENT_TO_SURFACE")
        if subphase_name == "ASCENT_TO_SURFACE":
            status_text = "40 -> Surface"
            status_value_kind = "surd_travel"
            current_depth = max(int(round(40 - ((40 / max(l40_to_surface_sec, 1)) * min(elapsed_sec, l40_to_surface_sec)))), 0)
            depth_text = "Surface" if current_depth <= 0 else f"{current_depth} fsw"
            summary_text = "Next: Undress"
            summary_value_kind = "surd_travel"
            primary_button_label = "Reach Surface"
            primary_button_enabled = True
        elif subphase_name == "UNDRESS":
            status_text = "Undress"
            status_value_kind = "surd_travel"
            depth_text = "Surface"
            summary_text = "Next: Surface -> 50 fsw"
            summary_value_kind = "surd_travel"
            primary_button_label = "Leave Surface"
            primary_button_enabled = True
        else:
            status_text = "Surface -> 50 fsw"
            status_value_kind = "surd_travel"
            depth_text = "50 fsw"
            summary_text = "Next: 50 fsw"
            summary_value_kind = "surd_travel"
            primary_button_label = "Reach Bottom"
            primary_button_enabled = True
        if max_surface_interval_sec < elapsed_sec <= surface_interval_penalty_max_sec:
            status_value_kind = "warning"
            summary_text = "Next: Chamber 50 with penalty"
            summary_value_kind = "warning"
            detail_text = "05:00-07:00 adds 15 min O2 at 50"
        elif elapsed_sec > surface_interval_penalty_max_sec:
            status_value_kind = "air_break"
            summary_text = "Surface interval exceeded"
            summary_value_kind = "air_break"
            detail_text = "Apply >07:00 penalty path"
        if max_surface_interval_sec < elapsed_sec <= surface_interval_penalty_max_sec:
            primary_value_kind = "warning"
        elif elapsed_sec > surface_interval_penalty_max_sec:
            primary_value_kind = "air_break"
    elif phase_name == "CHAMBER_OXYGEN":
        current_segment = current_surd_o2_segment(state)
        next_segment = next_surd_o2_segment(state)
        segment_elapsed_sec = current_o2_elapsed_sec(state, elapsed_sec)
        segment_duration_sec = 0 if current_segment is None else current_segment.duration_sec
        segment_remaining_sec = max(segment_duration_sec - segment_elapsed_sec, 0.0)
        off_o2_elapsed = off_o2_elapsed_sec(state, elapsed_sec)
        depth_text = f"{state.current_chamber_depth_fsw or 50} fsw"
        status_text = f"{state.current_chamber_depth_fsw or 50} fsw"
        if current_segment is not None and state.current_o2_segment_started_at is None:
            summary_text = f"Next: {current_segment.depth_fsw} fsw for {int(current_segment.duration_sec / 60)} min"
            secondary_button_label = "On O2"
            secondary_button_enabled = True
        else:
            summary_text = current_o2_summary(current_segment)
            detail_text = f"O2 {format_mmss(segment_elapsed_sec)} | {format_mmss(segment_remaining_sec)} left"
            detail_kind = "o2"
            primary_value_kind = "o2"
            status_text = f"{current_segment.depth_fsw} fsw O2" if current_segment is not None else status_text
            secondary_button_label = "Off O2"
            secondary_button_enabled = current_segment is not None and state.off_o2_started_at is None
        if state.off_o2_started_at is not None:
            status_text = "OFF O2"
            status_value_kind = "off_o2"
            primary_text = format_tenths(off_o2_elapsed)
            primary_value_kind = "off_o2"
            summary_text = "Next: On O2"
            summary_value_kind = "o2"
            detail_text = f"Off O2 {format_mmss(off_o2_elapsed)} | {format_mmss(segment_remaining_sec)} left"
            detail_kind = "off_o2"
            secondary_button_label = "On O2"
            secondary_button_enabled = current_segment is not None
        elif current_segment is not None and state.current_o2_segment_started_at is not None:
            status_value_kind = "o2"
            if current_segment.period_number == 1 and current_segment.depth_fsw == 50 and next_segment is not None:
                summary_text = f"Next: {next_segment.depth_fsw} fsw for {int(next_segment.duration_sec / 60)} min"
        if (
            current_segment is not None
            and state.current_o2_segment_started_at is not None
            and state.off_o2_started_at is None
            and current_segment.depth_fsw == 50
            and current_segment.period_number == 1
            and next_segment is not None
            and next_segment.depth_fsw != current_segment.depth_fsw
            and segment_elapsed_sec >= segment_duration_sec
        ):
            summary_text = "Next: Move chamber to 40 fsw"
            detail_text = "First 50 fsw segment complete"
            primary_button_label = "Chamber 40"
            primary_button_enabled = True
        elif current_segment is not None and segment_elapsed_sec >= segment_duration_sec:
            if next_segment is not None and next_segment.period_number > current_segment.period_number:
                summary_text = "Next: Start air break"
                detail_text = (
                    "First O2 period complete"
                    if current_segment.period_number == 1
                    else "O2 period complete"
                )
                primary_button_label = "Start Air Break"
                primary_button_enabled = True
            else:
                summary_text = "Next: Surface"
                detail_text = "Final O2 period complete"
                primary_button_label = "Reach Surface"
                primary_button_enabled = True
    elif phase_name == "CHAMBER_AIR_BREAK":
        next_segment = next_surd_o2_segment(state)
        air_break_elapsed_sec = max(
            elapsed_sec - max((state.current_air_break_started_at - state.phase_started_at).total_seconds(), 0.0),
            0.0,
        ) if state.phase_started_at and state.current_air_break_started_at else 0.0
        air_break_remaining_sec = max(chamber_air_break_sec - air_break_elapsed_sec, 0.0)
        depth_text = f"{state.current_chamber_depth_fsw or 40} fsw"
        status_text = f"{state.current_chamber_depth_fsw or 40} fsw Air Break"
        status_value_kind = "air_break"
        summary_text = "Chamber air break"
        primary_value_kind = "air_break"
        detail_text = f"Air {format_mmss(air_break_elapsed_sec)} | {format_mmss(air_break_remaining_sec)} left"
        detail_kind = "air_break"
        if air_break_elapsed_sec >= chamber_air_break_sec:
            next_period_number = None if next_segment is None else next_segment.period_number
            next_depth = None if next_segment is None else next_segment.depth_fsw
            if next_depth == 30 and state.current_chamber_depth_fsw == 40:
                summary_text = "Next: Move chamber to 30 fsw"
                detail_text = "Air break complete"
                primary_button_label = "Chamber 30"
            elif next_period_number is not None:
                summary_text = f"Next: Resume O2 period {next_period_number}"
                detail_text = "Air break complete"
                primary_button_label = "Resume O2"
            primary_button_enabled = next_period_number is not None
    elif phase_name == "COMPLETE":
        clean_remaining_sec = max(clean_time_sec - elapsed_sec, 0.0)
        primary_text = format_mmss(clean_remaining_sec)
        depth_text = "Surface"
        summary_text = ""
        detail_text = ""
        detail_kind = "air_break"

    return SurfaceSnapshot(
        mode_text="SURFACE",
        status_text=status_text,
        status_value_kind=status_value_kind,
        primary_text=primary_text,
        primary_value_kind=primary_value_kind,
        depth_text=depth_text,
        summary_text=summary_text,
        summary_value_kind=summary_value_kind,
        detail_text=detail_text,
        detail_kind=detail_kind,
        primary_button_label=primary_button_label,
        secondary_button_label=secondary_button_label,
        primary_button_enabled=primary_button_enabled,
        secondary_button_enabled=secondary_button_enabled,
    )
