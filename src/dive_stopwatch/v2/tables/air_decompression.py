"""Air decompression table lookups backed by the canonical AIR CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path

from dive_stopwatch.v2.delay_rules import evaluate_between_stops_delay_rule, evaluate_first_stop_delay_rule
from dive_stopwatch.v2.dive_session import DiveSession, ceil_minutes
from .no_decompression import lookup_repetitive_group

__all__ = [
    "AirDecoRow",
    "AirO2OxygenShiftPlan",
    "BasicAirDecompressionProfile",
    "BetweenStopsDelayEvaluation",
    "DecompressionMode",
    "FirstStopArrivalEvaluation",
    "available_air_decompression_depths",
    "air_o2_oxygen_stop_depths",
    "available_decompression_depths",
    "available_air_o2_decompression_depths",
    "build_air_o2_oxygen_shift_plan",
    "build_basic_air_decompression_profile",
    "build_basic_air_decompression_profile_for_session",
    "build_basic_decompression_profile",
    "build_basic_decompression_profile_for_session",
    "build_basic_air_o2_decompression_profile",
    "build_basic_air_o2_decompression_profile_for_session",
    "evaluate_between_stops_delay",
    "evaluate_first_stop_arrival",
    "lookup_air_decompression_row",
    "lookup_decompression_row",
    "lookup_air_o2_decompression_row",
    "planned_travel_time_to_first_stop_seconds",
]


class DecompressionMode(str, Enum):
    AIR = "AIR"
    AIR_O2 = "AIR/O2"


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
    mode: DecompressionMode = DecompressionMode.AIR


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
    mode: DecompressionMode = DecompressionMode.AIR


@dataclass(frozen=True)
class AirO2OxygenShiftPlan:
    first_oxygen_stop_depth_fsw: int | None
    oxygen_stop_depths_fsw: tuple[int, ...]
    travel_shift_vent_starts_on_arrival: bool
    travel_shift_vent_start_depth_fsw: int | None


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


@dataclass(frozen=True)
class BetweenStopsDelayEvaluation:
    max_depth_fsw: int
    planned_profile: BasicAirDecompressionProfile
    active_profile: BasicAirDecompressionProfile
    actual_elapsed_seconds: float
    planned_elapsed_seconds: int
    delay_seconds: float
    rounded_delay_minutes: int
    delay_depth_fsw: int
    outcome: str
    schedule_changed: bool


AIR_DECOMPRESSION_TABLE: dict[int, dict[int, AirDecoRow]] = {}
AIR_O2_DECOMPRESSION_TABLE: dict[int, dict[int, AirDecoRow]] = {}

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


_CSV_MODE_PATHS: dict[DecompressionMode, tuple[str, ...]] = {
    DecompressionMode.AIR: ("air_decompression_air.csv",),
    DecompressionMode.AIR_O2: ("air_decompression_air_o2.csv", "air_decompression_air.csv"),
}


def _load_csv_rows(mode: DecompressionMode) -> dict[int, dict[int, AirDecoRow]]:
    """Load decompression rows for a specific mode from one or more CSV sources."""

    docs_root = Path(__file__).resolve().parents[4] / "docs"
    loaded: dict[int, dict[int, AirDecoRow]] = {}
    seen_keys: set[tuple[int, int]] = set()
    allowed_gas_mix = {mode.value}
    if mode is DecompressionMode.AIR:
        allowed_gas_mix.add("")

    for file_name in _CSV_MODE_PATHS[mode]:
        csv_path = docs_root / file_name
        if not csv_path.exists():
            continue

        with csv_path.open(newline="") as handle:
            for raw_row in csv.DictReader(handle):
                if not any((value or "").strip() for value in raw_row.values()):
                    continue
                if raw_row.get("gas_mix", "").strip() not in allowed_gas_mix:
                    continue

                depth_fsw = int(raw_row["depth_fsw"])
                bottom_time_min = int(raw_row["bottom_time_min"])
                key = (depth_fsw, bottom_time_min)
                if key in seen_keys:
                    continue

                stops_fsw: dict[int, int] = {}
                for column, stop_depth in _CSV_STOP_COLUMNS.items():
                    raw_value = raw_row.get(column, "").strip()
                    if not raw_value:
                        continue
                    stop_time = int(raw_value)
                    # Treat 0 placeholders the same as blank cells.
                    if stop_time <= 0:
                        continue
                    stops_fsw[stop_depth] = stop_time
                chamber_text = raw_row.get("chamber_o2_periods", "").strip()
                chamber_o2_periods = float(chamber_text) if chamber_text else 0.0
                repeat_group = raw_row.get("repeat_group", "").strip() or None
                total_ascent_time = raw_row.get("total_ascent_time", "").strip() or None
                section = raw_row.get("section", "").strip() or "csv_import"

                loaded.setdefault(depth_fsw, {})[bottom_time_min] = AirDecoRow(
                    depth_fsw=depth_fsw,
                    bottom_time_min=bottom_time_min,
                    time_to_first_stop=raw_row["time_to_first_stop"].strip(),
                    stops_fsw=stops_fsw,
                    total_ascent_time=total_ascent_time,
                    chamber_o2_periods=chamber_o2_periods,
                    repeat_group=repeat_group,
                    section=section,
                    mode=mode,
                )
                seen_keys.add(key)
    return loaded


AIR_DECOMPRESSION_TABLE.update(_load_csv_rows(DecompressionMode.AIR))
AIR_O2_DECOMPRESSION_TABLE.update(_load_csv_rows(DecompressionMode.AIR_O2))


def _table_for_mode(mode: DecompressionMode) -> dict[int, dict[int, AirDecoRow]]:
    if mode is DecompressionMode.AIR:
        return AIR_DECOMPRESSION_TABLE
    if mode is DecompressionMode.AIR_O2:
        return AIR_O2_DECOMPRESSION_TABLE
    raise KeyError(f"Unsupported decompression mode: {mode.value}")


def available_air_decompression_depths() -> list[int]:
    return sorted(AIR_DECOMPRESSION_TABLE.keys())


def available_air_o2_decompression_depths() -> list[int]:
    return available_decompression_depths(DecompressionMode.AIR_O2)


def available_decompression_depths(mode: DecompressionMode) -> list[int]:
    return sorted(_table_for_mode(mode).keys())


def lookup_air_decompression_row(depth_fsw: int, bottom_time_min: int) -> AirDecoRow:
    return lookup_decompression_row(DecompressionMode.AIR, depth_fsw, bottom_time_min)


def lookup_air_o2_decompression_row(depth_fsw: int, bottom_time_min: int) -> AirDecoRow:
    return lookup_decompression_row(DecompressionMode.AIR_O2, depth_fsw, bottom_time_min)


def lookup_decompression_row(
    mode: DecompressionMode,
    depth_fsw: int,
    bottom_time_min: int,
) -> AirDecoRow:
    depth_rows = _table_for_mode(mode).get(depth_fsw)
    if depth_rows is None:
        raise KeyError(f"Unsupported {mode.value} decompression depth: {depth_fsw} fsw")

    row = depth_rows.get(bottom_time_min)
    if row is None:
        raise KeyError(
            f"Unsupported {mode.value} decompression bottom time {bottom_time_min} min at {depth_fsw} fsw"
        )
    return row


def build_basic_air_decompression_profile(
    max_depth_fsw: int,
    bottom_time_min: int,
) -> BasicAirDecompressionProfile:
    return build_basic_decompression_profile(DecompressionMode.AIR, max_depth_fsw, bottom_time_min)


def build_basic_air_o2_decompression_profile(
    max_depth_fsw: int,
    bottom_time_min: int,
) -> BasicAirDecompressionProfile:
    return build_basic_decompression_profile(DecompressionMode.AIR_O2, max_depth_fsw, bottom_time_min)


def build_basic_decompression_profile(
    mode: DecompressionMode,
    max_depth_fsw: int,
    bottom_time_min: int,
) -> BasicAirDecompressionProfile:
    """Build a conservative first-pass AIR deco profile."""

    if max_depth_fsw <= 0:
        raise ValueError("Max depth must be positive.")
    if bottom_time_min <= 0:
        raise ValueError("Bottom time must be positive.")

    table = _table_for_mode(mode)
    table_depth = _next_supported_depth(mode, max_depth_fsw)
    first_supported_time = min(table[table_depth])
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
            mode=mode,
        )

    table_bottom_time = _next_supported_bottom_time(mode, table_depth, bottom_time_min)
    row = lookup_decompression_row(mode, table_depth, table_bottom_time)
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
        mode=mode,
    )


def build_basic_air_decompression_profile_for_session(
    max_depth_fsw: int,
    session: DiveSession,
) -> BasicAirDecompressionProfile:
    return build_basic_decompression_profile_for_session(DecompressionMode.AIR, max_depth_fsw, session)


def build_basic_air_o2_decompression_profile_for_session(
    max_depth_fsw: int,
    session: DiveSession,
) -> BasicAirDecompressionProfile:
    return build_basic_decompression_profile_for_session(DecompressionMode.AIR_O2, max_depth_fsw, session)


def build_basic_decompression_profile_for_session(
    mode: DecompressionMode,
    max_depth_fsw: int,
    session: DiveSession,
) -> BasicAirDecompressionProfile:
    """Build a profile using the bottom time already captured by the dive session."""

    return build_basic_decompression_profile(
        mode=mode,
        max_depth_fsw=max_depth_fsw,
        bottom_time_min=session.bottom_time_minutes(),
    )


def evaluate_first_stop_arrival(
    max_depth_fsw: int,
    session: DiveSession,
    actual_tt1st_seconds: float,
    delay_depth_fsw: int | None = None,
    mode: DecompressionMode = DecompressionMode.AIR,
) -> FirstStopArrivalEvaluation:
    """Apply first-stop arrival timing rules to the planned AIR schedule."""

    planned_profile = build_basic_decompression_profile_for_session(mode, max_depth_fsw, session)
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

    delay_rule = evaluate_first_stop_delay_rule(
        actual_tt1st_seconds=actual_tt1st_seconds,
        planned_tt1st_seconds=planned_tt1st_seconds,
        delay_depth_fsw=delay_depth_fsw,
    )

    if delay_rule.outcome == "early_arrival":
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=planned_tt1st_seconds,
            delay_seconds=delay_rule.delay_seconds,
            rounded_delay_minutes=0,
            stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
            outcome="early_arrival",
            schedule_changed=False,
            missed_deeper_stop=False,
        )

    if delay_rule.outcome == "ignore_delay":
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=planned_tt1st_seconds,
            delay_seconds=delay_rule.delay_seconds,
            rounded_delay_minutes=0,
            stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
            outcome="ignore_delay",
            schedule_changed=False,
            missed_deeper_stop=False,
        )

    if delay_rule.outcome == "add_to_first_stop":
        active_profile = _add_delay_to_first_stop(planned_profile, delay_rule.rounded_delay_minutes)
        return FirstStopArrivalEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=active_profile,
            actual_tt1st_seconds=actual_tt1st_seconds,
            planned_tt1st_seconds=planned_tt1st_seconds,
            delay_seconds=delay_rule.delay_seconds,
            rounded_delay_minutes=delay_rule.rounded_delay_minutes,
            stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
            outcome="add_to_first_stop",
            schedule_changed=True,
            missed_deeper_stop=False,
        )

    recomputed_profile = build_basic_decompression_profile(
        mode=mode,
        max_depth_fsw=max_depth_fsw,
        bottom_time_min=session.bottom_time_minutes() + delay_rule.rounded_delay_minutes,
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
        delay_seconds=delay_rule.delay_seconds,
        rounded_delay_minutes=delay_rule.rounded_delay_minutes,
        stop_timer_starts_after_seconds=stop_timer_starts_after_seconds,
        outcome="recompute",
        schedule_changed=schedule_changed,
        missed_deeper_stop=missed_deeper_stop,
    )


def evaluate_between_stops_delay(
    max_depth_fsw: int,
    session: DiveSession,
    planned_profile: BasicAirDecompressionProfile,
    actual_elapsed_seconds: float,
    planned_elapsed_seconds: int,
    delay_depth_fsw: int,
    mode: DecompressionMode = DecompressionMode.AIR,
) -> BetweenStopsDelayEvaluation:
    """Apply between-stop or leaving-stop delay rules to an AIR schedule."""

    delay_rule = evaluate_between_stops_delay_rule(
        actual_elapsed_seconds=actual_elapsed_seconds,
        planned_elapsed_seconds=planned_elapsed_seconds,
        delay_depth_fsw=delay_depth_fsw,
    )

    if delay_rule.outcome == "ignore_delay":
        return BetweenStopsDelayEvaluation(
            max_depth_fsw=max_depth_fsw,
            planned_profile=planned_profile,
            active_profile=planned_profile,
            actual_elapsed_seconds=actual_elapsed_seconds,
            planned_elapsed_seconds=planned_elapsed_seconds,
            delay_seconds=delay_rule.delay_seconds,
            rounded_delay_minutes=0,
            delay_depth_fsw=delay_depth_fsw,
            outcome="ignore_delay",
            schedule_changed=False,
        )
    base_bottom_time = planned_profile.table_bottom_time_min or session.bottom_time_minutes()
    recomputed_profile = build_basic_decompression_profile(
        mode=mode,
        max_depth_fsw=max_depth_fsw,
        bottom_time_min=base_bottom_time + delay_rule.rounded_delay_minutes,
    )
    active_profile = _discard_missed_deeper_stops(recomputed_profile, delay_depth_fsw)
    remaining_planned_profile = _discard_missed_deeper_stops(planned_profile, delay_depth_fsw)
    schedule_changed = _profiles_require_schedule_change(remaining_planned_profile, active_profile)
    return BetweenStopsDelayEvaluation(
        max_depth_fsw=max_depth_fsw,
        planned_profile=planned_profile,
        active_profile=active_profile,
        actual_elapsed_seconds=actual_elapsed_seconds,
        planned_elapsed_seconds=planned_elapsed_seconds,
        delay_seconds=delay_rule.delay_seconds,
        rounded_delay_minutes=delay_rule.rounded_delay_minutes,
        delay_depth_fsw=delay_depth_fsw,
        outcome="recompute" if schedule_changed else "ignore_delay",
        schedule_changed=schedule_changed,
    )


def _next_supported_depth(mode: DecompressionMode, depth_fsw: int) -> int:
    for supported_depth in available_decompression_depths(mode):
        if depth_fsw <= supported_depth:
            return supported_depth
    raise KeyError(f"No supported {mode.value} decompression table for depth {depth_fsw} fsw")


def _next_supported_bottom_time(mode: DecompressionMode, depth_fsw: int, bottom_time_min: int) -> int:
    for supported_time in sorted(_table_for_mode(mode)[depth_fsw].keys()):
        if bottom_time_min <= supported_time:
            return supported_time
    raise KeyError(
        f"No supported {mode.value} decompression row for bottom time {bottom_time_min} min at {depth_fsw} fsw"
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


def air_o2_oxygen_stop_depths(profile: BasicAirDecompressionProfile) -> tuple[int, ...]:
    """Return the AIR/O2 stop depths performed on oxygen."""

    if profile.mode is not DecompressionMode.AIR_O2:
        return ()
    return tuple(depth for depth in (30, 20) if depth in profile.stops_fsw)


def build_air_o2_oxygen_shift_plan(profile: BasicAirDecompressionProfile) -> AirO2OxygenShiftPlan:
    """Describe when Travel/Shift/Vent begins for an AIR/O2 ascent."""

    oxygen_stop_depths = air_o2_oxygen_stop_depths(profile)
    if not oxygen_stop_depths:
        return AirO2OxygenShiftPlan(
            first_oxygen_stop_depth_fsw=None,
            oxygen_stop_depths_fsw=(),
            travel_shift_vent_starts_on_arrival=False,
            travel_shift_vent_start_depth_fsw=None,
        )

    first_oxygen_stop_depth = oxygen_stop_depths[0]
    if profile.first_stop_depth_fsw == first_oxygen_stop_depth:
        return AirO2OxygenShiftPlan(
            first_oxygen_stop_depth_fsw=first_oxygen_stop_depth,
            oxygen_stop_depths_fsw=oxygen_stop_depths,
            travel_shift_vent_starts_on_arrival=True,
            travel_shift_vent_start_depth_fsw=first_oxygen_stop_depth,
        )

    if first_oxygen_stop_depth == 30 and 40 in profile.stops_fsw:
        return AirO2OxygenShiftPlan(
            first_oxygen_stop_depth_fsw=first_oxygen_stop_depth,
            oxygen_stop_depths_fsw=oxygen_stop_depths,
            travel_shift_vent_starts_on_arrival=False,
            travel_shift_vent_start_depth_fsw=40,
        )

    return AirO2OxygenShiftPlan(
        first_oxygen_stop_depth_fsw=first_oxygen_stop_depth,
        oxygen_stop_depths_fsw=oxygen_stop_depths,
        travel_shift_vent_starts_on_arrival=True,
        travel_shift_vent_start_depth_fsw=first_oxygen_stop_depth,
    )


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


def _discard_missed_deeper_stops(
    profile: BasicAirDecompressionProfile,
    resume_depth_fsw: int,
) -> BasicAirDecompressionProfile:
    if not profile.stops_fsw:
        return profile
    remaining_stops = {
        stop_depth: stop_time
        for stop_depth, stop_time in profile.stops_fsw.items()
        if stop_depth <= resume_depth_fsw
    }
    if not remaining_stops:
        return profile

    first_stop_depth_fsw = max(remaining_stops)
    return BasicAirDecompressionProfile(
        input_depth_fsw=profile.input_depth_fsw,
        input_bottom_time_min=profile.input_bottom_time_min,
        table_depth_fsw=profile.table_depth_fsw,
        table_bottom_time_min=profile.table_bottom_time_min,
        time_to_first_stop=profile.time_to_first_stop,
        first_stop_depth_fsw=first_stop_depth_fsw,
        first_stop_time_min=remaining_stops[first_stop_depth_fsw],
        stops_fsw=remaining_stops,
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
