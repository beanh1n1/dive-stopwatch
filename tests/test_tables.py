import csv
import re
from pathlib import Path
import unittest

from dive_stopwatch.core.profiles import DecoMode, DelayOutcome, apply_between_stop_delay, apply_first_stop_delay, build_profile, no_decompression_limit


DOCS = Path(__file__).resolve().parents[1] / "docs"
AUDIT = DOCS / "CSV_BOUNDARY_AUDIT.md"
STOP_COLUMNS = [
    "stop_130",
    "stop_120",
    "stop_110",
    "stop_100",
    "stop_90",
    "stop_80",
    "stop_70",
    "stop_60",
    "stop_50",
    "stop_40",
    "stop_30",
    "stop_20",
]


def _rows(name: str) -> list[dict[str, str]]:
    with (DOCS / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _depths(name: str) -> set[int]:
    return {int(row["depth_fsw"]) for row in _rows(name)}


def _row(name: str, depth_fsw: int, bottom_time_min: int) -> dict[str, str]:
    for row in _rows(name):
        if int(row["depth_fsw"]) == depth_fsw and int(row["bottom_time_min"]) == bottom_time_min:
            return row
    raise KeyError((name, depth_fsw, bottom_time_min))


def _parse_mmss_or_none(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    minutes_text, seconds_text = text.split(":", maxsplit=1)
    return (int(minutes_text) * 60) + int(seconds_text)


_AUDIT_GAP_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*Gap\s*\|$")


def _audit_gap_rows() -> dict[str, list[tuple[int, int, int]]]:
    rows: dict[str, list[tuple[int, int, int]]] = {}
    current_name: str | None = None

    for line in AUDIT.read_text().splitlines():
        stripped = line.strip()
        if stripped == "## AIR.csv":
            current_name = "AIR.csv"
            continue
        if stripped == "## AIR_O2.csv":
            current_name = "AIR_O2.csv"
            continue
        if current_name is None:
            continue

        match = _AUDIT_GAP_ROW_RE.match(stripped)
        if not match:
            continue

        depth_fsw, max_no_d, first_deco, _gap = map(int, match.groups())
        rows.setdefault(current_name, []).append((depth_fsw, max_no_d, first_deco))

    return rows


class CsvSourceOfTruthTests(unittest.TestCase):
    def test_no_decompression_rows_have_blank_deco_fields(self) -> None:
        for name in ("AIR.csv", "AIR_O2.csv"):
            for row in _rows(name):
                if row.get("section", "").strip() != "no_decompression":
                    continue
                self.assertEqual(row.get("time_to_first_stop", "").strip(), "")
                self.assertEqual(row.get("total_ascent_time", "").strip(), "")
                self.assertEqual(row.get("chamber_o2_periods", "").strip(), "")
                for column in STOP_COLUMNS:
                    self.assertEqual(row.get(column, "").strip(), "")

    def test_air_boundary_row_is_explicit_no_decompression_source(self) -> None:
        row = _row("AIR.csv", 30, 371)
        self.assertEqual(row["gas_mix"], "AIR")
        self.assertEqual(row["repeat_group"], "Z")
        self.assertEqual(row["section"], "no_decompression")
        self.assertEqual(row["time_to_first_stop"].strip(), "")

    def test_air_o2_terminal_no_decompression_row_is_explicit_source(self) -> None:
        row = _row("AIR_O2.csv", 50, 89)
        self.assertEqual(row["gas_mix"], "AIR/O2")
        self.assertEqual(row["repeat_group"], "L")
        self.assertEqual(row["section"], "no_decompression")
        self.assertEqual(row["time_to_first_stop"].strip(), "")

    def test_all_gap_boundaries_round_to_first_deco_row(self) -> None:
        audit_rows = _audit_gap_rows()
        for name, mode in (("AIR.csv", DecoMode.AIR), ("AIR_O2.csv", DecoMode.AIR_O2)):
            for depth_fsw, max_no_d, first_deco in audit_rows[name]:
                with self.subTest(mode=mode.value, depth_fsw=depth_fsw, bottom_time_min=max_no_d):
                    no_deco_profile = build_profile(mode, depth_fsw, max_no_d)
                    self.assertTrue(no_deco_profile.is_no_decompression)
                    self.assertEqual(no_deco_profile.table_depth_fsw, depth_fsw)
                    self.assertEqual(no_deco_profile.table_bottom_time_min, max_no_d)

                with self.subTest(mode=mode.value, depth_fsw=depth_fsw, bottom_time_min=max_no_d + 1):
                    first_deco_profile = build_profile(mode, depth_fsw, max_no_d + 1)
                    self.assertEqual(first_deco_profile.table_depth_fsw, depth_fsw)
                    self.assertEqual(first_deco_profile.table_bottom_time_min, first_deco)

    def test_every_audited_gap_minute_between_max_no_d_and_first_deco_rounds_to_first_deco_row(self) -> None:
        audit_rows = _audit_gap_rows()
        for name, mode in (("AIR.csv", DecoMode.AIR), ("AIR_O2.csv", DecoMode.AIR_O2)):
            for depth_fsw, max_no_d, first_deco in audit_rows[name]:
                for bottom_time_min in range(max_no_d + 1, first_deco):
                    with self.subTest(mode=mode.value, depth_fsw=depth_fsw, bottom_time_min=bottom_time_min):
                        profile = build_profile(mode, depth_fsw, bottom_time_min)
                        self.assertEqual(profile.table_depth_fsw, depth_fsw)
                        self.assertEqual(profile.table_bottom_time_min, first_deco)


class CoreTableRegressionTests(unittest.TestCase):
    def test_air_and_air_o2_depth_ladders_match_after_75_fsw_correction(self) -> None:
        air_depths = _depths("AIR.csv")
        air_o2_depths = _depths("AIR_O2.csv")
        self.assertEqual(air_depths, air_o2_depths)

    def test_every_csv_row_round_trips_through_build_profile(self) -> None:
        for name, mode in (("AIR.csv", DecoMode.AIR), ("AIR_O2.csv", DecoMode.AIR_O2)):
            for raw_row in _rows(name):
                depth_fsw = int(raw_row["depth_fsw"])
                bottom_time_min = int(raw_row["bottom_time_min"])

                with self.subTest(mode=mode.value, depth_fsw=depth_fsw, bottom_time_min=bottom_time_min):
                    profile = build_profile(mode, depth_fsw, bottom_time_min)
                    expected_stops: list[tuple[int, int, str]] = []
                    for column in STOP_COLUMNS:
                        raw_value = raw_row.get(column, "").strip()
                        if not raw_value or int(raw_value) <= 0:
                            continue
                        stop_depth = int(column.removeprefix("stop_"))
                        stop_gas = "o2" if mode is DecoMode.AIR_O2 and stop_depth in {30, 20} else "air"
                        expected_stops.append((stop_depth, int(raw_value), stop_gas))

                    self.assertEqual(profile.input_depth_fsw, depth_fsw)
                    self.assertEqual(profile.input_bottom_time_min, bottom_time_min)
                    self.assertEqual(profile.table_depth_fsw, depth_fsw)
                    self.assertEqual(profile.table_bottom_time_min, bottom_time_min)
                    self.assertEqual(profile.time_to_first_stop_sec, _parse_mmss_or_none(raw_row.get("time_to_first_stop")))
                    self.assertEqual(profile.total_ascent_time_sec, _parse_mmss_or_none(raw_row.get("total_ascent_time")))
                    self.assertEqual(profile.repeat_group, (raw_row.get("repeat_group", "").strip() or None))
                    self.assertEqual(profile.is_no_decompression, not expected_stops)
                    self.assertEqual([(stop.depth_fsw, stop.duration_min, stop.gas) for stop in profile.stops], expected_stops)

    def test_no_decompression_limit_matches_csv_rows_across_supported_depths(self) -> None:
        for name, mode in (("AIR.csv", DecoMode.AIR), ("AIR_O2.csv", DecoMode.AIR_O2)):
            depths: dict[int, list[int]] = {}
            for raw_row in _rows(name):
                depth_fsw = int(raw_row["depth_fsw"])
                bottom_time_min = int(raw_row["bottom_time_min"])
                positive_stops = [
                    int(raw_row.get(column, "").strip())
                    for column in STOP_COLUMNS
                    if raw_row.get(column, "").strip() and int(raw_row.get(column, "").strip()) > 0
                ]
                if positive_stops:
                    continue
                depths.setdefault(depth_fsw, []).append(bottom_time_min)

            for depth_fsw, limits in sorted(depths.items()):
                with self.subTest(mode=mode.value, depth_fsw=depth_fsw):
                    self.assertEqual(no_decompression_limit(mode, depth_fsw), max(limits))

    def test_requests_in_the_71_to_75_band_round_to_80_after_75_fsw_correction(self) -> None:
        for requested_depth in range(71, 76):
            with self.subTest(requested_depth=requested_depth):
                air_profile = build_profile(DecoMode.AIR, requested_depth, 50)
                air_o2_profile = build_profile(DecoMode.AIR_O2, requested_depth, 50)
                self.assertEqual(air_profile.table_depth_fsw, 80)
                self.assertEqual(air_o2_profile.table_depth_fsw, 80)
                self.assertEqual(air_profile.table_bottom_time_min, 50)
                self.assertEqual(air_o2_profile.table_bottom_time_min, 50)

    def test_air_no_decompression_profile_uses_merged_csv_row(self) -> None:
        profile = build_profile(DecoMode.AIR, 31, 23)
        self.assertTrue(profile.is_no_decompression)
        self.assertEqual(profile.table_depth_fsw, 35)
        self.assertEqual(profile.table_bottom_time_min, 23)
        self.assertEqual(profile.time_to_first_stop_sec, None)
        self.assertEqual(profile.repeat_group, "B")
        self.assertEqual(profile.stops, ())

    def test_air_standard_decompression_profile_uses_csv_row(self) -> None:
        profile = build_profile(DecoMode.AIR, 30, 380)
        self.assertFalse(profile.is_no_decompression)
        self.assertEqual(profile.table_depth_fsw, 30)
        self.assertEqual(profile.table_bottom_time_min, 380)
        self.assertEqual(profile.time_to_first_stop_sec, 20)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(20, 5, "air")])
        self.assertEqual(profile.repeat_group, "Z")

    def test_air_o2_profile_uses_seed_row(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 90, 120)
        self.assertEqual(profile.table_depth_fsw, 90)
        self.assertEqual(profile.table_bottom_time_min, 120)
        self.assertEqual(profile.time_to_first_stop_sec, 100)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(40, 2, "air"), (30, 14, "o2"), (20, 70, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 5920)

    def test_manual_example_air_o2_profile_rounds_to_150_40(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 39)
        self.assertEqual(profile.table_depth_fsw, 150)
        self.assertEqual(profile.table_bottom_time_min, 40)
        self.assertEqual(profile.time_to_first_stop_sec, 200)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(50, 2, "air"), (40, 6, "air"), (30, 7, "o2"), (20, 35, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 3560)

    def test_air_profile_rounds_depth_and_time_up_conservatively(self) -> None:
        profile = build_profile(DecoMode.AIR, 131, 89)
        self.assertEqual(profile.table_depth_fsw, 140)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop_sec, 160)
        self.assertEqual(profile.stops[0].depth_fsw, 60)
        self.assertEqual(profile.stops[0].duration_min, 12)

    def test_air_profile_can_round_into_deeper_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 171, 69)
        self.assertEqual(profile.table_depth_fsw, 180)
        self.assertEqual(profile.table_bottom_time_min, 70)
        self.assertEqual(profile.time_to_first_stop_sec, 200)
        self.assertEqual(profile.stops[0].depth_fsw, 80)
        self.assertEqual(profile.stops[0].duration_min, 4)

    def test_air_200_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 200, 25)
        self.assertEqual(profile.table_depth_fsw, 200)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 260)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(70, 1, "air"), (60, 5, "air"), (50, 6, "air"), (40, 6, "air"), (30, 7, "air"), (20, 85, "air")])
        self.assertEqual(profile.repeat_group, "Z")

    def test_air_o2_200_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 200, 25)
        self.assertEqual(profile.table_depth_fsw, 200)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 260)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(70, 1, "air"), (60, 5, "air"), (50, 6, "air"), (40, 6, "air"), (30, 4, "o2"), (20, 32, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 3860)

    def test_air_210_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 210, 30)
        self.assertEqual(profile.table_depth_fsw, 210)
        self.assertEqual(profile.table_bottom_time_min, 30)
        self.assertEqual(profile.time_to_first_stop_sec, 260)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(80, 2, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 6, "air"), (30, 26, "air"), (20, 163, "air")])
        self.assertEqual(profile.repeat_group, "Z")

    def test_air_o2_210_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 210, 30)
        self.assertEqual(profile.table_depth_fsw, 210)
        self.assertEqual(profile.table_bottom_time_min, 30)
        self.assertEqual(profile.time_to_first_stop_sec, 260)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(80, 2, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 6, "air"), (30, 13, "o2"), (20, 45, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 5600)

    def test_air_220_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 220, 25)
        self.assertEqual(profile.table_depth_fsw, 220)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 280)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(80, 1, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 6, "air"), (30, 14, "air"), (20, 133, "air")])
        self.assertEqual(profile.repeat_group, "Z")

    def test_air_o2_220_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 220, 25)
        self.assertEqual(profile.table_depth_fsw, 220)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 280)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(80, 1, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 6, "air"), (30, 7, "o2"), (20, 41, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 4960)

    def test_air_250_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 250, 25)
        self.assertEqual(profile.table_depth_fsw, 250)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 300)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(100, 1, "air"), (90, 4, "air"), (80, 4, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 10, "air"), (30, 28, "air"), (20, 189, "air")])
        self.assertEqual(profile.total_ascent_time_sec, 15520)

    def test_air_o2_250_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 250, 25)
        self.assertEqual(profile.table_depth_fsw, 250)
        self.assertEqual(profile.table_bottom_time_min, 25)
        self.assertEqual(profile.time_to_first_stop_sec, 300)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(100, 1, "air"), (90, 4, "air"), (80, 4, "air"), (70, 5, "air"), (60, 6, "air"), (50, 6, "air"), (40, 10, "air"), (30, 14, "o2"), (20, 51, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 6720)

    def test_air_300_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR, 300, 20)
        self.assertEqual(profile.table_depth_fsw, 300)
        self.assertEqual(profile.table_bottom_time_min, 20)
        self.assertEqual(profile.time_to_first_stop_sec, 360)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(120, 2, "air"), (110, 2, "air"), (100, 2, "air"), (90, 4, "air"), (80, 5, "air"), (70, 5, "air"), (60, 5, "air"), (50, 6, "air"), (40, 16, "air"), (30, 28, "air"), (20, 219, "air")])
        self.assertEqual(profile.total_ascent_time_sec, 18040)

    def test_air_o2_300_fsw_profile_uses_new_manual_rows(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 300, 20)
        self.assertEqual(profile.table_depth_fsw, 300)
        self.assertEqual(profile.table_bottom_time_min, 20)
        self.assertEqual(profile.time_to_first_stop_sec, 360)
        self.assertEqual([(s.depth_fsw, s.duration_min, s.gas) for s in profile.stops], [(120, 2, "air"), (110, 2, "air"), (100, 2, "air"), (90, 4, "air"), (80, 5, "air"), (70, 5, "air"), (60, 5, "air"), (50, 6, "air"), (40, 16, "air"), (30, 14, "o2"), (20, 59, "o2")])
        self.assertEqual(profile.total_ascent_time_sec, 8220)

    def test_air_o2_assigns_oxygen_only_at_30_and_20(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 39)
        gases = {stop.depth_fsw: stop.gas for stop in profile.stops}
        self.assertEqual(gases[50], "air")
        self.assertEqual(gases[40], "air")
        self.assertEqual(gases[30], "o2")
        self.assertEqual(gases[20], "o2")

    def test_air_o2_gas_assignment_constraints_hold_across_decompression_rows(self) -> None:
        cases = (
            (30, 380),
            (40, 170),
            (90, 120),
            (145, 39),
        )
        for depth_fsw, bottom_time_min in cases:
            with self.subTest(depth_fsw=depth_fsw, bottom_time_min=bottom_time_min):
                profile = build_profile(DecoMode.AIR_O2, depth_fsw, bottom_time_min)
                o2_depths = [stop.depth_fsw for stop in profile.stops if stop.gas == "o2"]
                self.assertTrue(o2_depths)
                self.assertEqual(o2_depths, [depth for depth in (30, 20) if depth in o2_depths])
                self.assertTrue(all(stop.depth_fsw <= 30 for stop in profile.stops if stop.gas == "o2"))

    def test_first_stop_delay_shallow_adds_time_to_first_stop(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 60)
        result = apply_first_stop_delay(profile=profile, actual_time_to_first_stop_sec=380, delay_depth_fsw=40)
        self.assertEqual(result.outcome, DelayOutcome.ADD_TO_FIRST_STOP)
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(30, 31), (20, 142)])

    def test_first_stop_delay_deep_recomputes_schedule(self) -> None:
        profile = build_profile(DecoMode.AIR, 121, 55)
        result = apply_first_stop_delay(profile=profile, actual_time_to_first_stop_sec=241, delay_depth_fsw=60)
        self.assertEqual(result.outcome, DelayOutcome.RECOMPUTE)
        self.assertEqual(result.delay_min, 2)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 130)
        self.assertEqual(result.profile.table_bottom_time_min, 60)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(40, 12), (30, 28), (20, 170)])

    def test_between_stops_delay_deep_recomputes_remaining_schedule(self) -> None:
        profile = build_profile(DecoMode.AIR, 171, 60)
        result = apply_between_stop_delay(profile=profile, actual_elapsed_sec=250, planned_elapsed_sec=60, delay_depth_fsw=70)
        self.assertEqual(result.outcome, DelayOutcome.RECOMPUTE)
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 180)
        self.assertEqual(result.profile.table_bottom_time_min, 70)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(70, 12), (60, 21), (50, 24), (40, 25), (30, 48), (20, 499)])


if __name__ == "__main__":
    unittest.main()
