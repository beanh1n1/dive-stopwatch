from __future__ import annotations

from .dive_session import format_minutes_seconds
from .tables import lookup_repetitive_group_schedule


def stop_depth_for_number(stop_depths: list[int], stop_number: int) -> int | None:
    index = stop_number - 1
    if 0 <= index < len(stop_depths):
        return stop_depths[index]
    return 0 if index == len(stop_depths) else None


def next_stop_depth(stop_depths: list[int], stop_number: int) -> int:
    next_index = stop_number
    if 0 <= next_index < len(stop_depths):
        return stop_depths[next_index]
    return 0


def table_schedule_text(profile) -> str:
    if profile.table_bottom_time_min is None:
        return f"{profile.table_depth_fsw}/Unlimited"
    return f"{profile.table_depth_fsw}/{profile.table_bottom_time_min}"


def profile_line_text(profile, *, bottom_time_minutes: int | None) -> str:
    if profile.section == "no_decompression":
        if bottom_time_minutes is None:
            return f"{profile.table_depth_fsw}/--   --"
        repet_group, schedule_time = lookup_repetitive_group_schedule(
            profile.table_depth_fsw,
            bottom_time_minutes,
        )
        return f"{profile.table_depth_fsw}/{schedule_time}   {repet_group}"
    return f"{table_schedule_text(profile)}   {profile.repeat_group or '--'}"


def surface_table_summary(profile, *, bottom_time_minutes: int | None) -> str:
    if profile is None:
        return "--/--   --"
    return profile_line_text(profile, bottom_time_minutes=bottom_time_minutes)


def next_stop_text(profile, *, latest_arrival_stop_number: int | None) -> str:
    if profile.section == "no_decompression":
        return "Surface"

    if latest_arrival_stop_number is None:
        return f"{profile.first_stop_depth_fsw} fsw" if profile.first_stop_depth_fsw is not None else "--"

    stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
    next_depth = next_stop_depth(stop_depths, latest_arrival_stop_number)
    return "Surface" if next_depth == 0 else f"{next_depth} fsw"


def next_stop_required_time(profile, *, latest_arrival_stop_number: int | None) -> str:
    if profile.section == "no_decompression":
        return "--"
    next_stop = next_stop_text(profile, latest_arrival_stop_number=latest_arrival_stop_number)
    if next_stop == "Surface":
        return "--"
    next_depth = int(next_stop.split()[0])
    stop_time = profile.stops_fsw.get(next_depth)
    return f"{stop_time}m" if stop_time is not None else "--"


def next_stop_instruction(profile, *, latest_arrival_stop_number: int | None) -> str:
    next_stop = next_stop_text(profile, latest_arrival_stop_number=latest_arrival_stop_number)
    next_time = next_stop_required_time(profile, latest_arrival_stop_number=latest_arrival_stop_number)
    if next_stop == "Surface" or next_time == "--":
        return f"Next: {next_stop}"
    return f"Next: {next_stop} for {next_time}"


def current_stop_remaining_text(balance_seconds: float | None) -> str:
    if balance_seconds is None:
        return "--:--"
    return format_minutes_seconds(max(balance_seconds, 0.0))


def next_action_after_air_break(
    profile,
    *,
    latest_arrival_stop_number: int | None,
    current_stop_remaining: str,
) -> str:
    if latest_arrival_stop_number is None:
        return next_stop_instruction(profile, latest_arrival_stop_number=latest_arrival_stop_number)
    stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
    current_depth = stop_depth_for_number(stop_depths, latest_arrival_stop_number)
    if current_depth == 20:
        return f"Next: 20 fsw for {current_stop_remaining}"
    return next_stop_instruction(profile, latest_arrival_stop_number=latest_arrival_stop_number)
