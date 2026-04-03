"""Air decompression table lookups backed by the canonical AIR CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import math
from pathlib import Path

from dive_stopwatch.dive_session import DiveSession, ceil_minutes
from dive_stopwatch.tables.no_decompression import lookup_repetitive_group

__all__ = [
    "AirDecoRow",
    "BasicAirDecompressionProfile",
    "FirstStopArrivalEvaluation",
    "available_air_decompression_depths",
    "build_basic_air_decompression_profile",
    "build_basic_air_decompression_profile_for_session",
    "evaluate_first_stop_arrival",
    "lookup_air_decompression_row",
    "planned_travel_time_to_first_stop_seconds",
]


@dataclass(frozen=True)
class AirDecoRow:
    depth_fsw: int
    bottom_time_min: int
    time_to_first_stop: str
    stops_fsw: dict[int, int]
    total_ascent_time: str | None
    chamber_o2_periods: float
    repeat_group: str | None
    section: str


@dataclass(frozen=True)
class BasicAirDecompressionProfile:
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int
    table_bottom_time_min: int | None
    time_to_first_stop: str | None
    first_stop_depth_fsw: int | None
    first_stop_time_min: int | None
    stops_fsw: dict[int, int]
    total_ascent_time: str | None
    chamber_o2_periods: float | None
    repeat_group: str | None
    section: str


@dataclass(frozen=True)
class FirstStopArrivalEvaluation:
    max_depth_fsw: int
    planned_profile: BasicAirDecompressionProfile
    active_profile: BasicAirDecompressionProfile
    actual_tt1st_seconds: float
    planned_tt1st_seconds: int | None
    delay_seconds: float | None
    rounded_delay_minutes: int
    stop_timer_starts_after_seconds: float
    outcome: str
    schedule_changed: bool
    missed_deeper_stop: bool


AIR_DECOMPRESSION_TABLE: dict[int, dict[int, AirDecoRow]] = {}

_CSV_STOP_COLUMNS = {
    "stop_130": 130,
    "stop_120": 120,
    "stop_110": 110,
    "stop_100": 100,
    "stop_90": 90,
    "stop_80": 80,
    "stop_70": 70,
    "stop_60": 60,
    "stop_50": 50,
    "stop_40": 40,
    "stop_30": 30,
    "stop_20": 20,
}


def _load_csv_air_rows() -> dict[int, dict[int, AirDecoRow]]:
    """Load AIR rows from the canonical CSV."""

    csv_path = Path(__file__).resolve().parents[3] / "docs" / "air_decompression_air.csv"
    if not csv_path.exists():
        return {}

    loaded: dict[int, dict[int, AirDecoRow]] = {}
    with csv_path.open(newline="") as handle:
        for raw_row in csv.DictReader(handle):
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            if raw_row.get("gas_mix", "").strip() not in {"", "AIR"}:
                continue

            depth_fsw = int(raw_row["depth_fsw"])
            bottom_time_min = int(raw_row["bottom_time_min"])
            stops_fsw = {
                stop_depth: int(raw_row[column])
                for column, stop_depth in _CSV_STOP_COLUMNS.items()
                if raw_row.get(column, "").strip()
            }
            chamber_text = raw_row.get("chamber_o2_periods", "").strip()
            chamber_o2_periods = float(chamber_text) if chamber_text else 0.0
            repeat_group = raw_row.get("repeat_group", "").strip() or None

            loaded.setdefault(depth_fsw, {})[bottom_time_min] = AirDecoRow(
                depth_fsw=depth_fsw,
                bottom_time_min=bottom_time_min,
                time_to_first_stop=raw_row["time_to_first_stop"].strip(),
                stops_fsw=stops_fsw,
                total_ascent_time=None,
                chamber_o2_periods=chamber_o2_periods,
                repeat_group=repeat_group,
                section="csv_import",
            )
    return loaded


AIR_DECOMPRESSION_TABLE.update(_load_csv_air_rows())


def available_air_decompression_depths() -> list[int]:
    return sorted(AIR_DECOMPRESSION_TABLE.keys())


def lookup_air_decompression_row(depth_fsw: int, bottom_time_min: int) -> AirDecoRow:
    depth_rows = AIR_DECOMPRESSION_TABLE.get(depth_fsw)
    if depth_rows is None:
        raise KeyError(f"Unsupported air decompression depth: {depth_fsw} fsw")

    row = depth_rows.get(bottom_time_min)
    if row is None:
        raise KeyError(
            f"Unsupported air decompression bottom time {bottom_time_min} min at {depth_fsw} fsw"
        )
    return row


def build_basic_air_decompression_profile(
    max_depth_fsw: int,
    bottom_time_min: int,
) -> BasicAirDecompressionProfile:
    """Build a conservative first-pass AIR deco profile."""

    if max_depth_fsw <= 0:
        raise ValueError("Max depth must be positive.")
    if bottom_time_min <= 0:
        raise ValueError("Bottom time must be positive.")

    table_depth = _next_supported_depth(max_depth_fsw)
    first_supported_time = min(AIR_DECOMPRESSION_TABLE[table_depth])
    if bottom_time_min < first_supported_time:
        no_deco_depth = _next_no_decompression_depth(max_depth_fsw)
        return BasicAirDecompressionProfile(
            input_depth_fsw=max_depth_fsw,
            input_bottom_time_min=bottom_time_min,
            table_depth_fsw=no_deco_depth,
            table_bottom_time_min=None,
            time_to_first_stop=None,
            first_stop_depth_fsw=None,
            first_stop_time_min=None,
            stops_fsw={},
            total_ascent_time=None,
            chamber_o2_periods=None,
            repeat_group=lookup_repetitive_group(no_deco_depth, bottom_time_min),
            section="no_decompression",
        )

    table_bottom_time = _next_supported_bottom_time(table_depth, bottom_time_min)
    row = lookup_air_decompression_row(table_depth, table_bottom_time)
    first_stop_depth = max(row.stops_fsw) if row.stops_fsw else None
    first_stop_time = row.stops_fsw.get(first_stop_depth) if first_stop_depth is not None else None

    return BasicAirDecompressionProfile(
        input_depth_fsw=max_depth_fsw,
        input_bottom_time_min=bottom_time_min,
        table_depth_fsw=table_depth,
        table_bottom_time_min=table_bottom_time,
        time_to_first_stop=row.time_to_first_stop,
        first_stop_depth_fsw=first_stop_depth,
        first_stop_time_min=first_stop_time,
        stops_fsw=dict(row.stops_fsw),
        total_ascent_time=row.total_ascent_time,
        chamber_o2_periods=row.chamber_o2_periods,
        repeat_group=row.repeat_group,
        section=row.section,
    )


def build_basic_air_decompression_profile_for_session(
    max_depth_fsw: int,
    session: DiveSession,
) -> BasicAirDecompressionProfile:
    """Build a profile using the bottom time already captured by the dive session."""

    return build_basic_air_decompression_profile(
        max_depth_fsw=max_depth_fsw,
        bottom_time_min=session.bottom_time_minutes(),
    )


def evaluate_first_stop_arrival(
    max_depth_fsw: int,
    session: DiveSession,
    actual_tt1st_seconds: float,
    delay_zone: str | None = None,
) -> FirstStopArrivalEvaluation:
    """Apply first-stop arrival timing rules to the planned AIR schedule."""

    planned_profile = build_basic_air_decompression_profile_for_session(max_depth_fsw, session)
    if planned_profile.section == "no_decompression":
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=None,
            delay_seconds=None,
            rounded_delay_minutes=0,
            stop_timer_starts_after_seconds=actual_tt1st_seconds,
            outcome="no_decompression",
            schedule_changed=False,
            missed_deeper_stop=False,
        )

    planned_tt1st_seconds = planned_travel_time_to_first_stop_seconds(max_depth_fsw, planned_profile)
    if planned_tt1st_seconds is None:
        raise ValueError("Planned AIR decompression profile is missing a first stop.")
    stop_timer_starts_after_seconds = max(actual_tt1st_seconds, float(planned_tt1st_seconds))

    if actual_tt1st_seconds < planned_tt1st_seconds:
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=planned_tt1st_seconds,
            delay_seconds=actual_tt1st_seconds - planned_tt1st_seconds,
            rounded_delay_minutes=0,
            stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
            outcome="early_arrival",
            schedule_changed=False,
            missed_deeper_stop=False,
        )

    delay_seconds = actual_tt1st_seconds - planned_tt1st_seconds
    if delay_seconds <= 60:
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=planned_tt1st_seconds,
            delay_seconds=delay_seconds,
            rounded_delay_minutes=0,
            stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
            outcome="ignore_delay",
            schedule_changed=False,
            missed_deeper_stop=False,
        )

    if planned_profile.first_stop_depth_fsw is not None and planned_profile.first_stop_depth_fsw < 50:
        rounded_delay_minutes = ceil_minutes(delay_seconds)
        if delay_zone == "shallower_than_50":
            active_profile = _add_delay_to_first_stop(planned_profile, rounded_delay_minutes)
            return FirstStopArrivalEvaluation(
                max_depth_fsw=max_depth_fsw,
                planned_profile=planned_profile,
                active_profile=active_profile,
                actual_tt1st_seconds=actual_tt1st_seconds,
                planned_tt1st_seconds=planned_tt1st_seconds,
                delay_seconds=delay_seconds,
                rounded_delay_minutes=rounded_delay_minutes,
                stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
                outcome="add_to_first_stop",
                schedule_changed=True,
                missed_deeper_stop=False,
            )
        if delay_zone not in {None, "deeper_than_50"}:
            raise ValueError("Unsupported delay zone.")
        if delay_zone is None:
            return FirstStopArrivalEvaluation(
                max_depth_fsw=max_depth_fsw,
                planned_profile=planned_profile,
                active_profile=planned_profile,
                actual_tt1st_seconds=actual_tt1st_seconds,
                planned_tt1st_seconds=planned_tt1st_seconds,
                delay_seconds=delay_seconds,
                rounded_delay_minutes=rounded_delay_minutes,
                stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
                outcome="delay_zone_required",
                schedule_changed=False,
                missed_deeper_stop=False,
            )

    rounded_delay_minutes = ceil_minutes(delay_seconds)
    recomputed_profile = build_basic_air_decompression_profile(
        max_depth_fsw=max_depth_fsw,
        bottom_time_min=session.bottom_time_minutes() + rounded_delay_minutes,
    )
    active_profile = _apply_missed_deeper_stops(recomputed_profile, planned_profile.first_stop_depth_fsw)
    schedule_changed = _profiles_require_schedule_change(planned_profile, active_profile)
    missed_deeper_stop = (
        recomputed_profile.first_stop_depth_fsw is not None
        and planned_profile.first_stop_depth_fsw is not None
        and recomputed_profile.first_stop_depth_fsw > planned_profile.first_stop_depth_fsw
    )
    return FirstStopArrivalEvaluation(
        max_depth_fsw=max_depth_fsw,
        planned_profile=planned_profile,
        active_profile=active_profile,
        actual_tt1st_seconds=actual_tt1st_seconds,
        planned_tt1st_seconds=planned_tt1st_seconds,
        delay_seconds=delay_seconds,
        rounded_delay_minutes=rounded_delay_minutes,
        stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
        outcome="recompute",
        schedule_changed=schedule_changed,
        missed_deeper_stop=missed_deeper_stop,
    )


def _next_supported_depth(depth_fsw: int) -> int:
    for supported_depth in available_air_decompression_depths():
        if depth_fsw <= supported_depth:
            return supported_depth
    raise KeyError(f"No supported air decompression table for depth {depth_fsw} fsw")


def _next_supported_bottom_time(depth_fsw: int, bottom_time_min: int) -> int:
    for supported_time in sorted(AIR_DECOMPRESSION_TABLE[depth_fsw].keys()):
        if bottom_time_min <= supported_time:
            return supported_time
    raise KeyError(
        f"No supported air decompression row for bottom time {bottom_time_min} min at {depth_fsw} fsw"
    )


def _next_no_decompression_depth(depth_fsw: int) -> int:
    supported_depths = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
    for supported_depth in supported_depths:
        if depth_fsw <= supported_depth:
            return supported_depth
    raise KeyError(f"No supported no-decompression table for depth {depth_fsw} fsw")


def _parse_minutes_seconds(display: str) -> int:
    minutes_text, seconds_text = display.split(":", maxsplit=1)
    return (int(minutes_text) * 60) + int(seconds_text)


def planned_travel_time_to_first_stop_seconds(
    max_depth_fsw: int,
    profile: BasicAirDecompressionProfile,
) -> int | None:
    first_stop_depth = profile.first_stop_depth_fsw
    if first_stop_depth is None:
        return None
    travel_distance = max(max_depth_fsw - first_stop_depth, 0)
    return math.ceil((travel_distance / 30) * 60)


def _add_delay_to_first_stop(
    profile: BasicAirDecompressionProfile,
    rounded_delay_minutes: int,
) -> BasicAirDecompressionProfile:
    first_stop_depth = profile.first_stop_depth_fsw
    first_stop_time = profile.first_stop_time_min
    if first_stop_depth is None or first_stop_time is None:
        return profile
    updated_stops = dict(profile.stops_fsw)
    updated_stops[first_stop_depth] = first_stop_time + rounded_delay_minutes
    return BasicAirDecompressionProfile(
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        table_depth_fsw=profile.table_depth_fsw,
        table_bottom_time_min=profile.table_bottom_time_min,
        time_to_first_stop=profile.time_to_first_stop,
        first_stop_depth_fsw=first_stop_depth,
        first_stop_time_min=updated_stops[first_stop_depth],
        stops_fsw=updated_stops,
        total_ascent_time=profile.total_ascent_time,
        chamber_o2_periods=profile.chamber_o2_periods,
        repeat_group=profile.repeat_group,
        section=profile.section,
    )


def _apply_missed_deeper_stops(
    profile: BasicAirDecompressionProfile,
    current_depth_fsw: int | None,
) -> BasicAirDecompressionProfile:
    if current_depth_fsw is None or not profile.stops_fsw:
        return profile
    if profile.first_stop_depth_fsw is None or profile.first_stop_depth_fsw <= current_depth_fsw:
        return profile

    merged_stops = dict(profile.stops_fsw)
    carry_time = sum(
        stop_time for stop_depth, stop_time in merged_stops.items() if stop_depth > current_depth_fsw
    )
    merged_stops = {
        stop_depth: stop_time
        for stop_depth, stop_time in merged_stops.items()
        if stop_depth <= current_depth_fsw
    }
    merged_stops[current_depth_fsw] = merged_stops.get(current_depth_fsw, 0) + carry_time
    first_stop_depth_fsw = max(merged_stops)
    return BasicAirDecompressionProfile(
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        table_depth_fsw=profile.table_depth_fsw,
        table_bottom_time_min=profile.table_bottom_time_min,
        time_to_first_stop=profile.time_to_first_stop,
        first_stop_depth_fsw=first_stop_depth_fsw,
        first_stop_time_min=merged_stops[first_stop_depth_fsw],
        stops_fsw=merged_stops,
        total_ascent_time=profile.total_ascent_time,
        chamber_o2_periods=profile.chamber_o2_periods,
        repeat_group=profile.repeat_group,
        section=profile.section,
    )


def _profiles_require_schedule_change(
    planned: BasicAirDecompressionProfile,
    active: BasicAirDecompressionProfile,
) -> bool:
    return any(
        (
            planned.table_depth_fsw != active.table_depth_fsw,
            planned.table_bottom_time_min != active.table_bottom_time_min,
            planned.time_to_first_stop != active.time_to_first_stop,
            planned.first_stop_depth_fsw != active.first_stop_depth_fsw,
            planned.first_stop_time_min != active.first_stop_time_min,
            planned.stops_fsw != active.stops_fsw,
            planned.chamber_o2_periods != active.chamber_o2_periods,
            planned.repeat_group != active.repeat_group,
            planned.section != active.section,
        )
    )
