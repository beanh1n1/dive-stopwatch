from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
import math
from pathlib import Path
from typing import Literal


class DecoMode(str, Enum):
    AIR = "AIR"
    AIR_O2 = "AIR/O2"


GasType = Literal["air", "o2", "surface"]


@dataclass(frozen=True)
class ProfileStop:
    index: int
    depth_fsw: int
    duration_min: int
    gas: GasType


@dataclass(frozen=True)
class DiveProfile:
    mode: DecoMode
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int
    table_bottom_time_min: int | None
    time_to_first_stop_sec: int | None
    stops: tuple[ProfileStop, ...]
    total_ascent_time_sec: int | None
    repeat_group: str | None
    is_no_decompression: bool


@dataclass(frozen=True)
class DelayResult:
    profile: DiveProfile
    delay_min: int
    schedule_changed: bool
    outcome: str
    credited_o2_min: int = 0
    air_interruption_min: int = 0


@dataclass(frozen=True)
class TableRow:
    mode: DecoMode
    depth_fsw: int
    bottom_time_min: int
    time_to_first_stop_sec: int | None
    stops: tuple[ProfileStop, ...]
    total_ascent_time_sec: int | None
    repeat_group: str | None
    is_no_decompression: bool


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

_CSV_MODE_PATHS: dict[DecoMode, tuple[str, ...]] = {
    DecoMode.AIR: ("AIR.csv",),
    DecoMode.AIR_O2: ("AIR_O2.csv", "AIR.csv"),
}

_ROWS_BY_MODE: dict[DecoMode, dict[int, dict[int, TableRow]]] = {
    DecoMode.AIR: {},
    DecoMode.AIR_O2: {},
}
_LOADED = False

def build_profile(mode: DecoMode, depth_fsw: int, bottom_time_min: int) -> DiveProfile:
    if depth_fsw <= 0:
        raise ValueError("Depth must be positive.")
    if bottom_time_min <= 0:
        raise ValueError("Bottom time must be positive.")
    _ensure_loaded()

    return _row_to_profile(
        _lookup_row(mode, depth_fsw, bottom_time_min),
        input_depth_fsw=depth_fsw,
        input_bottom_time_min=bottom_time_min,
    )


def no_decompression_limit(mode: DecoMode, depth_fsw: int) -> int | None:
    _ensure_loaded()
    table = _rows_for_mode(mode)
    table_depth = _next_supported_depth(table, depth_fsw)
    limits = [bottom_time for bottom_time, row in table[table_depth].items() if row.is_no_decompression]
    return max(limits, default=None)


def apply_first_stop_delay(
    profile: DiveProfile,
    actual_time_to_first_stop_sec: int,
    delay_depth_fsw: int | None = None,
) -> DelayResult:

    planned_time = profile.time_to_first_stop_sec
    if planned_time is None or profile.is_no_decompression:
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="no_decompression")

    if actual_time_to_first_stop_sec < planned_time:
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="early_arrival")

    delay_seconds = actual_time_to_first_stop_sec - planned_time
    if delay_seconds <= 60:
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="ignore_delay")

    delay_min = _ceil_minutes(delay_seconds)
    if delay_depth_fsw is not None and delay_depth_fsw <= 50:
        updated = replace(
            profile,
            stops=tuple(replace(stop, duration_min=stop.duration_min + delay_min) if stop.index == 1 else stop for stop in profile.stops),
        ) if profile.stops else profile
        return DelayResult(profile=updated, delay_min=delay_min, schedule_changed=True, outcome="add_to_first_stop")

    recomputed = build_profile(profile.mode, profile.input_depth_fsw, profile.input_bottom_time_min + delay_min)
    current_depth_fsw = first_stop_depth(profile)
    missed = () if current_depth_fsw is None else tuple(stop for stop in recomputed.stops if stop.depth_fsw > current_depth_fsw)
    if missed:
        carry_min = sum(stop.duration_min for stop in missed)
        kept = [stop for stop in recomputed.stops if stop.depth_fsw <= current_depth_fsw]
        if kept:
            kept[0] = replace(kept[0], duration_min=kept[0].duration_min + carry_min)
            adjusted = replace(recomputed, stops=_reindex_stops(kept))
        else:
            adjusted = recomputed
    else:
        adjusted = recomputed
    return DelayResult(
        profile=adjusted,
        delay_min=delay_min,
        schedule_changed=_schedule_changed(profile, adjusted),
        outcome="recompute",
    )


def apply_between_stop_delay(
    profile: DiveProfile,
    actual_elapsed_sec: int,
    planned_elapsed_sec: int,
    delay_depth_fsw: int,
) -> DelayResult:

    delay_seconds = actual_elapsed_sec - planned_elapsed_sec
    if delay_seconds <= 60:
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="ignore_delay")
    delay_min = _ceil_minutes(delay_seconds)
    if delay_depth_fsw <= 50:
        return DelayResult(profile=profile, delay_min=delay_min, schedule_changed=False, outcome="ignore_delay")

    recomputed = build_profile(profile.mode, profile.input_depth_fsw, profile.table_bottom_time_min + delay_min)
    adjusted_stops = tuple(stop for stop in recomputed.stops if stop.depth_fsw <= delay_depth_fsw)
    adjusted = replace(recomputed, stops=_reindex_stops(adjusted_stops))
    planned_stops = tuple(stop for stop in profile.stops if stop.depth_fsw <= delay_depth_fsw)
    planned_remaining = replace(profile, stops=_reindex_stops(planned_stops))
    changed = _schedule_changed(planned_remaining, adjusted)
    return DelayResult(
        profile=adjusted,
        delay_min=delay_min,
        schedule_changed=changed,
        outcome="recompute" if changed else "ignore_delay",
    )


def apply_oxygen_travel_delay(
    profile: DiveProfile,
    from_stop_index: int,
    delay_elapsed_sec: int,
    o2_time_before_delay_sec: int,
) -> DelayResult:
    if delay_elapsed_sec <= 0:
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="ignore_delay")

    current_stop = stop_by_index(profile, from_stop_index)
    next_stop = next_stop_after(profile, from_stop_index)
    if (
        current_stop is None
        or next_stop is None
        or current_stop.gas != "o2"
        or next_stop.gas != "o2"
        or current_stop.depth_fsw != 30
        or next_stop.depth_fsw != 20
    ):
        return DelayResult(profile=profile, delay_min=0, schedule_changed=False, outcome="ignore_delay")

    delay_min = _ceil_minutes(delay_elapsed_sec)
    qualifying_o2_sec = min(delay_elapsed_sec, max((30 * 60) - max(o2_time_before_delay_sec, 0), 0))
    credited_o2_min = min(_ceil_minutes(qualifying_o2_sec), next_stop.duration_min) if qualifying_o2_sec > 0 else 0
    air_interruption_min = max(delay_min - credited_o2_min, 0)

    if credited_o2_min <= 0:
        return DelayResult(
            profile=profile,
            delay_min=delay_min,
            schedule_changed=False,
            outcome="o2_delay_credit",
            credited_o2_min=0,
            air_interruption_min=air_interruption_min,
        )

    adjusted_stops = []
    for stop in profile.stops:
        if stop.index != next_stop.index:
            adjusted_stops.append(stop)
            continue
        remaining_min = stop.duration_min - credited_o2_min
        if remaining_min > 0:
            adjusted_stops.append(replace(stop, duration_min=remaining_min))

    adjusted = replace(profile, stops=_reindex_stops(adjusted_stops))
    return DelayResult(
        profile=adjusted,
        delay_min=delay_min,
        schedule_changed=_schedule_changed(profile, adjusted),
        outcome="o2_delay_credit",
        credited_o2_min=credited_o2_min,
        air_interruption_min=air_interruption_min,
    )


def first_stop_depth(profile: DiveProfile) -> int | None:
    if not profile.stops:
        return None
    return profile.stops[0].depth_fsw


def stop_by_index(profile: DiveProfile, stop_index: int) -> ProfileStop | None:
    if stop_index <= 0:
        return None
    index = stop_index - 1
    if 0 <= index < len(profile.stops):
        return profile.stops[index]
    return None


def next_stop_after(profile: DiveProfile, stop_index: int | None) -> ProfileStop | None:
    if stop_index is None:
        return stop_by_index(profile, 1)
    return stop_by_index(profile, stop_index + 1)


def _reindex_stops(stops: tuple[ProfileStop, ...] | list[ProfileStop]) -> tuple[ProfileStop, ...]:
    return tuple(replace(stop, index=index) for index, stop in enumerate(stops, start=1))


def _schedule_changed(left: DiveProfile, right: DiveProfile) -> bool:
    return (
        left.table_depth_fsw != right.table_depth_fsw
        or left.table_bottom_time_min != right.table_bottom_time_min
        or _stop_shape(left.stops) != _stop_shape(right.stops)
    )


def _stop_shape(stops: tuple[ProfileStop, ...]) -> tuple[tuple[int, int], ...]:
    return tuple((stop.depth_fsw, stop.duration_min) for stop in stops)


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    for mode in _ROWS_BY_MODE:
        _ROWS_BY_MODE[mode].update(_load_rows(mode))
    _LOADED = True


def _load_rows(mode: DecoMode) -> dict[int, dict[int, TableRow]]:
    docs_root = Path(__file__).resolve().parents[3] / "docs"
    loaded: dict[int, dict[int, TableRow]] = {}
    seen_keys: set[tuple[int, int]] = set()
    allowed_gas_mix = {mode.value}
    if mode is DecoMode.AIR:
        allowed_gas_mix.add("")

    for file_name in _CSV_MODE_PATHS[mode]:
        with (docs_root / file_name).open(newline="") as handle:
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

                stop_minutes_by_depth: dict[int, int] = {}
                for column, stop_depth in _CSV_STOP_COLUMNS.items():
                    raw_value = raw_row.get(column, "").strip()
                    if not raw_value:
                        continue
                    stop_time = int(raw_value)
                    if stop_time > 0:
                        stop_minutes_by_depth[stop_depth] = stop_time

                loaded.setdefault(depth_fsw, {})[bottom_time_min] = TableRow(
                    mode=mode,
                    depth_fsw=depth_fsw,
                    bottom_time_min=bottom_time_min,
                    time_to_first_stop_sec=_parse_mmss(raw_row.get("time_to_first_stop")),
                    stops=_build_stops(mode, stop_minutes_by_depth),
                    total_ascent_time_sec=_parse_mmss(raw_row.get("total_ascent_time")),
                    repeat_group=(raw_row.get("repeat_group", "").strip() or None),
                    is_no_decompression=not stop_minutes_by_depth,
                )
                seen_keys.add(key)
    return loaded


def _parse_mmss(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    minutes_text, seconds_text = text.split(":", maxsplit=1)
    return (int(minutes_text) * 60) + int(seconds_text)


def _ceil_minutes(seconds: float) -> int:
    return max(math.ceil(seconds / 60.0), 0)


def _rows_for_mode(mode: DecoMode) -> dict[int, dict[int, TableRow]]:
    return _ROWS_BY_MODE[mode]


def _lookup_row(mode: DecoMode, depth_fsw: int, bottom_time_min: int) -> TableRow:
    table = _rows_for_mode(mode)
    table_depth = _next_supported_depth(table, depth_fsw)
    return table[table_depth][_next_supported_bottom_time(table[table_depth], bottom_time_min)]


def _next_supported_depth(table: dict[int, dict[int, TableRow]], depth_fsw: int) -> int:
    for supported_depth in sorted(table):
        if depth_fsw <= supported_depth:
            return supported_depth
    raise KeyError(f"No supported decompression depth for {depth_fsw} fsw")


def _next_supported_bottom_time(depth_rows: dict[int, TableRow], bottom_time_min: int) -> int:
    for supported_time in sorted(depth_rows):
        if bottom_time_min <= supported_time:
            return supported_time
    raise KeyError(f"No supported decompression row for bottom time {bottom_time_min} min")


def _row_to_profile(row: TableRow, *, input_depth_fsw: int, input_bottom_time_min: int) -> DiveProfile:
    return DiveProfile(
        mode=row.mode,
        input_depth_fsw=input_depth_fsw,
        input_bottom_time_min=input_bottom_time_min,
        table_depth_fsw=row.depth_fsw,
        table_bottom_time_min=row.bottom_time_min,
        time_to_first_stop_sec=row.time_to_first_stop_sec,
        stops=row.stops,
        total_ascent_time_sec=row.total_ascent_time_sec,
        repeat_group=row.repeat_group,
        is_no_decompression=row.is_no_decompression,
    )


def _build_stops(mode: DecoMode, stop_minutes_by_depth: dict[int, int]) -> tuple[ProfileStop, ...]:
    stops: list[ProfileStop] = []
    for index, depth in enumerate(sorted(stop_minutes_by_depth, reverse=True), start=1):
        gas: GasType = "o2" if mode is DecoMode.AIR_O2 and depth in {30, 20} else "air"
        stops.append(
            ProfileStop(
                index=index,
                depth_fsw=depth,
                duration_min=stop_minutes_by_depth[depth],
                gas=gas,
            )
        )
    return tuple(stops)
