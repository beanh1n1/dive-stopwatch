import csv
from pathlib import Path
import unittest

from dive_stopwatch.minimal.profiles import DecoMode, apply_between_stop_delay, apply_first_stop_delay, build_profile


DOCS = Path(__file__).resolve().parents[1] / "docs"
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


def _row(name: str, depth_fsw: int, bottom_time_min: int) -> dict[str, str]:
    for row in _rows(name):
        if int(row["depth_fsw"]) == depth_fsw and int(row["bottom_time_min"]) == bottom_time_min:
            return row
    raise KeyError((name, depth_fsw, bottom_time_min))


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


class MinimalTableRegressionTests(unittest.TestCase):
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

    def test_air_o2_assigns_oxygen_only_at_30_and_20(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 39)
        gases = {stop.depth_fsw: stop.gas for stop in profile.stops}
        self.assertEqual(gases[50], "air")
        self.assertEqual(gases[40], "air")
        self.assertEqual(gases[30], "o2")
        self.assertEqual(gases[20], "o2")

    def test_first_stop_delay_shallow_adds_time_to_first_stop(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 60)
        result = apply_first_stop_delay(profile=profile, actual_time_to_first_stop_sec=380, delay_depth_fsw=40)
        self.assertEqual(result.outcome, "add_to_first_stop")
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(30, 31), (20, 142)])

    def test_first_stop_delay_deep_recomputes_schedule(self) -> None:
        profile = build_profile(DecoMode.AIR, 121, 55)
        result = apply_first_stop_delay(profile=profile, actual_time_to_first_stop_sec=241, delay_depth_fsw=60)
        self.assertEqual(result.outcome, "recompute")
        self.assertEqual(result.delay_min, 2)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 130)
        self.assertEqual(result.profile.table_bottom_time_min, 60)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(40, 12), (30, 28), (20, 170)])

    def test_between_stops_delay_deep_recomputes_remaining_schedule(self) -> None:
        profile = build_profile(DecoMode.AIR, 171, 60)
        result = apply_between_stop_delay(profile=profile, actual_elapsed_sec=250, planned_elapsed_sec=60, delay_depth_fsw=70)
        self.assertEqual(result.outcome, "recompute")
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 180)
        self.assertEqual(result.profile.table_bottom_time_min, 70)
        self.assertEqual([(s.depth_fsw, s.duration_min) for s in result.profile.stops], [(70, 12), (60, 21), (50, 24), (40, 25), (30, 48), (20, 499)])


if __name__ == "__main__":
    unittest.main()
