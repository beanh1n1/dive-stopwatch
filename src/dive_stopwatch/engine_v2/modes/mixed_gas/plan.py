from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .state import MixedGasPlan, MixedGasStop

_SCHEDULES_CSV_NAME = "mixed_gas_table_12_4_schedules.csv"
_CSV_STOP_COLUMNS = (
    ("stop_190", 190),
    ("stop_180", 180),
    ("stop_170", 170),
    ("stop_160", 160),
    ("stop_150", 150),
    ("stop_140", 140),
    ("stop_130", 130),
    ("stop_120", 120),
    ("stop_110", 110),
    ("stop_100", 100),
    ("stop_90", 90),
    ("stop_80", 80),
    ("stop_70", 70),
    ("stop_60", 60),
    ("stop_50", 50),
    ("stop_40", 40),
    ("stop_30", 30),
    ("stop_20", 20),
)
_GAS_MIX_RANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-/]\s*(\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class _ScheduleRow:
    depth_fsw: int
    bottom_time_min: int
    gas_mix_min_percent: float
    gas_mix_max_percent: float
    chamber_o2_half_periods: int | None
    is_no_decompression: bool
    stops: tuple[MixedGasStop, ...]


def build_mixed_gas_plan(
    *,
    depth_fsw: int,
    bottom_time_min: int,
    bottom_mix_o2_percent: float | None,
    data_dir: Path | None = None,
) -> MixedGasPlan | None:
    rows = _load_review_rows(_data_dir(data_dir))
    table_depth_fsw = _next_supported_depth(rows, depth_fsw)
    if table_depth_fsw is None:
        return None
    candidates = [
        row
        for row in rows
        if row.depth_fsw == table_depth_fsw
        and _matches_bottom_mix(row, bottom_mix_o2_percent)
    ]
    if not candidates:
        return None
    row = _next_supported_bottom_time_row(candidates, bottom_time_min)
    if row is None:
        return None

    return MixedGasPlan(
        input_depth_fsw=depth_fsw,
        input_bottom_time_min=bottom_time_min,
        table_depth_fsw=row.depth_fsw,
        table_bottom_time_min=row.bottom_time_min,
        stops=row.stops,
        is_no_decompression=row.is_no_decompression,
    )


def supported_bottom_mix_range_for_depth(
    depth_fsw: int | None,
    *,
    data_dir: Path | None = None,
) -> tuple[float, float] | None:
    if depth_fsw is None:
        return None
    all_rows = _load_review_rows(_data_dir(data_dir))
    table_depth_fsw = _next_supported_depth(all_rows, depth_fsw)
    if table_depth_fsw is None:
        return None
    rows = [row for row in all_rows if row.depth_fsw == table_depth_fsw]
    if not rows:
        return None
    low = min(row.gas_mix_min_percent for row in rows)
    high = max(row.gas_mix_max_percent for row in rows)
    return (low, high)


def is_supported_bottom_mix_for_depth(
    *,
    depth_fsw: int | None,
    bottom_mix_o2_percent: float | None,
    data_dir: Path | None = None,
) -> bool:
    if depth_fsw is None or bottom_mix_o2_percent is None:
        return False
    supported_range = supported_bottom_mix_range_for_depth(depth_fsw, data_dir=data_dir)
    if supported_range is None:
        return False
    low, high = supported_range
    return low <= bottom_mix_o2_percent <= high


def max_supported_depth_for_bottom_mix(
    bottom_mix_o2_percent: float | None,
    *,
    data_dir: Path | None = None,
) -> int | None:
    if bottom_mix_o2_percent is None:
        return None
    rows = [
        row
        for row in _load_review_rows(_data_dir(data_dir))
        if _matches_bottom_mix(row, bottom_mix_o2_percent)
    ]
    if not rows:
        return None
    return max(row.depth_fsw for row in rows)


def mixed_gas_chamber_o2_half_periods(
    *,
    depth_fsw: int,
    bottom_time_min: int,
    bottom_mix_o2_percent: float | None = None,
    data_dir: Path | None = None,
) -> int | None:
    rows = _load_review_rows(_data_dir(data_dir))
    table_depth_fsw = _next_supported_depth(rows, depth_fsw)
    if table_depth_fsw is None:
        return None
    candidates = [
        row
        for row in rows
        if row.depth_fsw == table_depth_fsw
        and _matches_bottom_mix(row, bottom_mix_o2_percent)
    ]
    if not candidates:
        return None
    row = _next_supported_bottom_time_row(candidates, bottom_time_min)
    if row is None:
        return None
    return row.chamber_o2_half_periods


def _data_dir(override: Path | None) -> Path:
    if override is not None:
        return override
    docs_dir = Path(__file__).resolve().parents[5] / "docs"
    tables_dir = docs_dir / "Tables"
    if (tables_dir / _SCHEDULES_CSV_NAME).exists():
        return tables_dir
    return docs_dir


def _load_review_rows(data_dir: Path) -> tuple[_ScheduleRow, ...]:
    path = data_dir / _SCHEDULES_CSV_NAME
    if not path.exists():
        return ()

    rows: list[_ScheduleRow] = []
    seen_keys: set[tuple[int, int, float, float]] = set()
    with path.open(newline="") as handle:
        for raw_row in csv.DictReader(handle):
            if not any((value or "").strip() for value in raw_row.values()):
                continue

            depth_fsw = _require_int(raw_row.get("depth_fsw"), "depth_fsw")
            bottom_time_min = _require_int(raw_row.get("bottom_time_min"), "bottom_time_min")
            gas_mix_min_percent, gas_mix_max_percent = _require_gas_mix_range(raw_row.get("gas_mix"))
            key = (depth_fsw, bottom_time_min, gas_mix_min_percent, gas_mix_max_percent)
            if key in seen_keys:
                raise ValueError(f"duplicate mixed-gas schedule row: {key}")
            seen_keys.add(key)

            stops = _load_stops(raw_row)
            section = (raw_row.get("section") or "").strip().lower()
            is_no_decompression = section == "no_decompression" or not stops
            if section == "no_decompression" and stops:
                raise ValueError(f"mixed-gas no-decompression row has stop values at depth {depth_fsw} time {bottom_time_min}")

            rows.append(
                _ScheduleRow(
                    depth_fsw=depth_fsw,
                    bottom_time_min=bottom_time_min,
                    gas_mix_min_percent=gas_mix_min_percent,
                    gas_mix_max_percent=gas_mix_max_percent,
                    chamber_o2_half_periods=_parse_half_periods(raw_row.get("chamber_o2_periods")),
                    is_no_decompression=is_no_decompression,
                    stops=stops,
                )
            )

    return tuple(rows)


def _load_stops(raw_row: dict[str, str]) -> tuple[MixedGasStop, ...]:
    stops: list[MixedGasStop] = []
    index = 1
    for column, stop_depth in _CSV_STOP_COLUMNS:
        raw_value = (raw_row.get(column) or "").strip()
        if not raw_value:
            continue
        duration_min = int(raw_value)
        if duration_min <= 0:
            continue
        stops.append(
            MixedGasStop(
                index=index,
                depth_fsw=stop_depth,
                gas=_gas_for_stop_depth(stop_depth),
                duration_min=duration_min,
            )
        )
        index += 1
    return tuple(stops)


def _gas_for_stop_depth(depth_fsw: int) -> str:
    if depth_fsw >= 100:
        return "bottom_mix"
    if depth_fsw >= 40:
        return "50_50"
    return "o2"


def _matches_bottom_mix(row: _ScheduleRow, bottom_mix_o2_percent: float | None) -> bool:
    if bottom_mix_o2_percent is None:
        return True
    return row.gas_mix_min_percent <= bottom_mix_o2_percent <= row.gas_mix_max_percent


def _next_supported_bottom_time_row(rows: list[_ScheduleRow], bottom_time_min: int) -> _ScheduleRow | None:
    for row in sorted(rows, key=lambda item: item.bottom_time_min):
        if bottom_time_min <= row.bottom_time_min:
            return row
    return None


def _next_supported_depth(rows: tuple[_ScheduleRow, ...], depth_fsw: int) -> int | None:
    for supported_depth in sorted({row.depth_fsw for row in rows}):
        if depth_fsw <= supported_depth:
            return supported_depth
    return None


def _require_int(value: str | None, field_name: str) -> int:
    parsed = _parse_int(value)
    if parsed is None:
        raise ValueError(f"mixed-gas {field_name} missing")
    return parsed


def _require_gas_mix_range(value: str | None) -> tuple[float, float]:
    text = (value or "").strip()
    if not text:
        raise ValueError("mixed-gas gas_mix missing")

    match = _GAS_MIX_RANGE_RE.match(text)
    if match:
        low = float(match.group(1))
        high = float(match.group(2))
        return (min(low, high), max(low, high))

    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) == 2:
            low = float(parts[0])
            high = float(parts[1])
            return (min(low, high), max(low, high))

    value_float = float(text)
    return (value_float, value_float)


def _parse_int(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    return int(text)


def _parse_half_periods(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    return int(round(float(text) * 2))
