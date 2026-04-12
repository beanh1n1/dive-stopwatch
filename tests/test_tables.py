from datetime import datetime
import unittest

from dive_stopwatch.v2.tables.air_decompression import (
    DecompressionMode,
    air_o2_oxygen_stop_depths,
    available_air_decompression_depths,
    available_air_o2_decompression_depths,
    available_decompression_depths,
    build_air_o2_oxygen_shift_plan,
    build_basic_air_decompression_profile,
    build_basic_air_decompression_profile_for_session,
    build_basic_air_o2_decompression_profile,
    build_basic_decompression_profile,
    evaluate_between_stops_delay,
    evaluate_first_stop_arrival,
    lookup_air_decompression_row,
    lookup_air_o2_decompression_row,
    lookup_decompression_row,
    planned_travel_time_to_first_stop_seconds,
)
from dive_stopwatch.v2.dive_session import DiveSession
from dive_stopwatch.v2.tables.no_decompression import (
    lookup_no_decompression_limit,
    lookup_repetitive_group,
    lookup_repetitive_group_schedule,
)


class NoDecompressionTableTests(unittest.TestCase):
    def test_lookup_no_stop_limit(self) -> None:
        self.assertEqual(lookup_no_decompression_limit(50), 92)
        self.assertIsNone(lookup_no_decompression_limit(10))

    def test_lookup_repetitive_group_for_exact_threshold(self) -> None:
        self.assertEqual(lookup_repetitive_group(30, 145), "J")
        self.assertEqual(lookup_repetitive_group(55, 74), "Z")

    def test_lookup_repetitive_group_uses_max_group_for_unlimited_rows(self) -> None:
        self.assertEqual(lookup_repetitive_group(15, 500), "I")
        self.assertEqual(lookup_repetitive_group(20, 999), "L")

    def test_lookup_deeper_no_stop_limits(self) -> None:
        self.assertEqual(lookup_no_decompression_limit(70), 48)
        self.assertEqual(lookup_no_decompression_limit(190), 5)

    def test_lookup_deeper_repetitive_groups(self) -> None:
        self.assertEqual(lookup_repetitive_group(100, 21), "G")
        self.assertEqual(lookup_repetitive_group(180, 5), "B")
        self.assertEqual(lookup_repetitive_group(190, 5), "Z")

    def test_lookup_repetitive_group_schedule_returns_rounded_table_row(self) -> None:
        self.assertEqual(lookup_repetitive_group_schedule(60, 4), ("A", 7))
        self.assertEqual(lookup_repetitive_group_schedule(100, 22), ("Z", 25))


class AirDecompressionTableTests(unittest.TestCase):
    def test_supported_depths_are_exposed(self) -> None:
        self.assertEqual(
            available_air_decompression_depths(),
            [30, 35, 40, 45, 50, 55, 60, 75, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190],
        )

    def test_supported_air_o2_depths_are_exposed(self) -> None:
        self.assertEqual(available_air_o2_decompression_depths(), [30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190])
        self.assertEqual(available_decompression_depths(DecompressionMode.AIR_O2), [30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190])

    def test_lookup_standard_air_row(self) -> None:
        row = lookup_air_decompression_row(30, 371)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "csv_import")

    def test_zero_minute_stop_placeholders_are_ignored(self) -> None:
        air_row = lookup_air_decompression_row(30, 371)
        air_o2_row = lookup_air_o2_decompression_row(30, 371)
        self.assertEqual(air_row.stops_fsw, {})
        self.assertEqual(air_o2_row.stops_fsw, {})

    def test_lookup_air_o2_seed_row(self) -> None:
        row = lookup_air_o2_decompression_row(90, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {40: 2, 30: 14, 20: 70})
        self.assertEqual(row.total_ascent_time, "98:40")
        self.assertEqual(row.chamber_o2_periods, 0.0)
        self.assertEqual(row.section, "surd_o2_required")

    def test_lookup_air_o2_30_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(30, 420)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "0:20")
        self.assertEqual(row.stops_fsw, {20: 5})
        self.assertEqual(row.total_ascent_time, "6:00")
        self.assertEqual(row.repeat_group, "Z")

    def test_lookup_air_o2_40_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(40, 300)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "0:40")
        self.assertEqual(row.stops_fsw, {20: 33})
        self.assertEqual(row.total_ascent_time, "34:20")

    def test_lookup_air_o2_45_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(45, 270)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "0:50")
        self.assertEqual(row.stops_fsw, {20: 45})
        self.assertEqual(row.total_ascent_time, "51:30")

    def test_lookup_air_o2_50_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(50, 300)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {20: 74})
        self.assertEqual(row.total_ascent_time, "85:40")

    def test_lookup_air_o2_60_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(60, 170)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:20")
        self.assertEqual(row.stops_fsw, {20: 53})
        self.assertEqual(row.total_ascent_time, "60:00")

    def test_lookup_air_o2_70_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(70, 180)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:20")
        self.assertEqual(row.stops_fsw, {30: 2, 20: 83})
        self.assertEqual(row.total_ascent_time, "97:00")

    def test_lookup_air_o2_80_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(80, 150)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {30: 10, 20: 80})
        self.assertEqual(row.total_ascent_time, "102:20")

    def test_lookup_air_o2_90_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(90, 150)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {40: 11, 30: 17, 20: 94})
        self.assertEqual(row.total_ascent_time, "139:40")

    def test_lookup_air_o2_100_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(100, 150)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {50: 3, 40: 26, 30: 23, 20: 109})
        self.assertEqual(row.total_ascent_time, "183:40")

    def test_lookup_air_o2_110_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(110, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:00")
        self.assertEqual(row.stops_fsw, {20: 14})
        self.assertEqual(row.total_ascent_time, "17:40")

    def test_lookup_air_o2_110_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(110, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:00")
        self.assertEqual(row.stops_fsw, {50: 10, 40: 26, 30: 18, 20: 101})
        self.assertEqual(row.total_ascent_time, "173:00")

    def test_lookup_air_o2_120_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(120, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:20")
        self.assertEqual(row.stops_fsw, {20: 20})
        self.assertEqual(row.total_ascent_time, "24:00")

    def test_lookup_air_o2_120_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(120, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:00")
        self.assertEqual(row.stops_fsw, {60: 3, 50: 23, 40: 25, 30: 24, 20: 113})
        self.assertEqual(row.total_ascent_time, "211:00")

    def test_lookup_air_o2_130_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(130, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:20")
        self.assertEqual(row.stops_fsw, {30: 3, 20: 23})
        self.assertEqual(row.total_ascent_time, "30:00")

    def test_lookup_air_o2_130_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(130, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:20")
        self.assertEqual(row.stops_fsw, {70: 17, 60: 24, 50: 27, 40: 29, 20: 130})
        self.assertEqual(row.total_ascent_time, "255:20")

    def test_lookup_air_o2_140_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(140, 30)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:40")
        self.assertEqual(row.stops_fsw, {30: 4, 20: 19})
        self.assertEqual(row.total_ascent_time, "27:20")

    def test_lookup_air_o2_140_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(140, 80)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:40")
        self.assertEqual(row.stops_fsw, {60: 2, 50: 24, 40: 25, 30: 15, 20: 91})
        self.assertEqual(row.total_ascent_time, "175:40")

    def test_lookup_air_o2_150_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(150, 25)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "4:00")
        self.assertEqual(row.stops_fsw, {30: 4, 20: 14})
        self.assertEqual(row.total_ascent_time, "22:40")

    def test_manual_example_air_o2_profile_rounds_to_150_40(self) -> None:
        profile = build_basic_air_o2_decompression_profile(145, 39)
        shift_plan = build_air_o2_oxygen_shift_plan(profile)

        self.assertEqual(profile.table_depth_fsw, 150)
        self.assertEqual(profile.table_bottom_time_min, 40)
        self.assertEqual(profile.time_to_first_stop, "3:20")
        self.assertEqual(profile.first_stop_depth_fsw, 50)
        self.assertEqual(profile.first_stop_time_min, 2)
        self.assertEqual(profile.stops_fsw, {50: 2, 40: 6, 30: 7, 20: 35})
        self.assertEqual(profile.total_ascent_time, "59:20")
        self.assertEqual(shift_plan.first_oxygen_stop_depth_fsw, 30)
        self.assertEqual(shift_plan.oxygen_stop_depths_fsw, (30, 20))
        self.assertFalse(shift_plan.travel_shift_vent_starts_on_arrival)
        self.assertEqual(shift_plan.travel_shift_vent_start_depth_fsw, 40)

    def test_lookup_air_o2_150_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(150, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:20")
        self.assertEqual(row.stops_fsw, {90: 3, 80: 20, 70: 22, 60: 23, 50: 50, 40: 37, 30: 168})
        self.assertEqual(row.total_ascent_time, "356:20")

    def test_lookup_air_o2_160_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(160, 80)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:00")
        self.assertEqual(row.stops_fsw, {70: 6, 60: 21, 50: 24, 40: 25, 30: 23, 20: 114})
        self.assertEqual(row.total_ascent_time, "237:00")

    def test_lookup_air_o2_170_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(170, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:40")
        self.assertEqual(row.stops_fsw, {60: 2, 50: 6, 40: 6, 30: 8, 20: 37})
        self.assertEqual(row.total_ascent_time, "68:40")

    def test_lookup_air_o2_170_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(170, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "2:40")
        self.assertEqual(row.stops_fsw, {100: 9, 90: 19, 80: 20, 70: 22, 60: 42, 50: 60, 40: 46, 30: 198})
        self.assertEqual(row.total_ascent_time, "454:40")

    def test_lookup_air_o2_180_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(180, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:40")
        self.assertEqual(row.stops_fsw, {70: 1, 60: 5, 50: 6, 40: 6, 30: 11, 20: 41})
        self.assertEqual(row.total_ascent_time, "79:40")

    def test_lookup_air_o2_180_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(180, 70)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:20")
        self.assertEqual(row.stops_fsw, {80: 4, 70: 12, 60: 21, 50: 24, 40: 25, 30: 24, 20: 119})
        self.assertEqual(row.total_ascent_time, "253:20")

    def test_lookup_air_o2_190_fsw_row(self) -> None:
        row = lookup_air_o2_decompression_row(190, 35)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "4:00")
        self.assertEqual(row.stops_fsw, {70: 4, 60: 5, 50: 6, 40: 8, 30: 13, 20: 45})
        self.assertEqual(row.total_ascent_time, "91:00")

    def test_lookup_air_o2_190_fsw_multi_stop_row(self) -> None:
        row = lookup_air_o2_decompression_row(190, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)
        self.assertEqual(row.time_to_first_stop, "3:00")
        self.assertEqual(row.stops_fsw, {100: 15, 90: 17, 80: 19, 70: 20, 60: 37, 50: 46, 40: 79, 30: 55, 20: 219})
        self.assertEqual(row.total_ascent_time, "551:00")

    def test_generic_lookup_can_select_air_o2_mode(self) -> None:
        row = lookup_decompression_row(DecompressionMode.AIR_O2, 90, 120)
        self.assertEqual(row.mode, DecompressionMode.AIR_O2)

    def test_lookup_recommended_row(self) -> None:
        row = lookup_air_decompression_row(50, 120)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {20: 21})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 0.5)
        self.assertEqual(row.repeat_group, "O")
        self.assertEqual(row.section, "csv_import")

    def test_lookup_required_row(self) -> None:
        row = lookup_air_decompression_row(45, 200)
        self.assertEqual(row.stops_fsw, {20: 89})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 1.0)
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "csv_import")

    def test_lookup_surd_o2_row(self) -> None:
        row = lookup_air_decompression_row(60, 300)
        self.assertEqual(row.stops_fsw, {20: 456})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 4.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_40_fsw_required_row(self) -> None:
        row = lookup_air_decompression_row(40, 300)
        self.assertEqual(row.time_to_first_stop, "0:40")
        self.assertEqual(row.stops_fsw, {20: 128})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 1.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_40_fsw_surd_o2_row(self) -> None:
        row = lookup_air_decompression_row(40, 540)
        self.assertEqual(row.time_to_first_stop, "0:40")
        self.assertEqual(row.stops_fsw, {20: 372})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 3.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_75_fsw_required_row(self) -> None:
        row = lookup_air_decompression_row(75, 160)
        self.assertEqual(row.time_to_first_stop, "1:20")
        self.assertEqual(row.stops_fsw, {30: 1})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 3.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_80_fsw_surd_o2_row(self) -> None:
        row = lookup_air_decompression_row(80, 180)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {30: 33})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 4.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_90_fsw_required_row(self) -> None:
        row = lookup_air_decompression_row(90, 80)
        self.assertEqual(row.time_to_first_stop, "2:00")
        self.assertEqual(row.stops_fsw, {30: 5, 20: 125})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 2.0)
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_90_fsw_surd_o2_required_row(self) -> None:
        row = lookup_air_decompression_row(90, 120)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {40: 2, 30: 28, 20: 256})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 3.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_new_90_fsw_surd_o2_row(self) -> None:
        row = lookup_air_decompression_row(90, 240)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {40: 42, 30: 68, 20: 592})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 7.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_100_fsw_row(self) -> None:
        row = lookup_air_decompression_row(100, 150)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {50: 3, 40: 26, 30: 46, 20: 461})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_110_fsw_row(self) -> None:
        row = lookup_air_decompression_row(110, 180)
        self.assertEqual(row.time_to_first_stop, "1:40")
        self.assertEqual(row.stops_fsw, {60: 3, 50: 23, 40: 47, 30: 68, 20: 593})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 7.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_120_fsw_row(self) -> None:
        row = lookup_air_decompression_row(120, 120)
        self.assertEqual(row.time_to_first_stop, "2:00")
        self.assertEqual(row.stops_fsw, {60: 3, 50: 23, 40: 25, 30: 47, 20: 480})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_130_fsw_row(self) -> None:
        row = lookup_air_decompression_row(130, 180)
        self.assertEqual(row.time_to_first_stop, "2:00")
        self.assertEqual(row.stops_fsw, {70: 13, 60: 21, 50: 45, 40: 57, 30: 94, 20: 658})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 9.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_140_fsw_row(self) -> None:
        row = lookup_air_decompression_row(140, 90)
        self.assertEqual(row.time_to_first_stop, "2:40")
        self.assertEqual(row.stops_fsw, {60: 12, 50: 23, 40: 26, 30: 38, 20: 443})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_150_fsw_row(self) -> None:
        row = lookup_air_decompression_row(150, 90)
        self.assertEqual(row.time_to_first_stop, "2:40")
        self.assertEqual(row.stops_fsw, {70: 3, 60: 22, 50: 23, 40: 26, 30: 47, 20: 496})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_160_fsw_row(self) -> None:
        row = lookup_air_decompression_row(160, 80)
        self.assertEqual(row.time_to_first_stop, "3:00")
        self.assertEqual(row.stops_fsw, {70: 6, 60: 21, 50: 24, 40: 25, 30: 44, 20: 482})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_170_fsw_row(self) -> None:
        row = lookup_air_decompression_row(170, 120)
        self.assertEqual(row.time_to_first_stop, "2:40")
        self.assertEqual(row.stops_fsw, {90: 9, 80: 19, 70: 20, 60: 22, 50: 42, 40: 60, 30: 94, 20: 659})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 9.0)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_180_fsw_row(self) -> None:
        row = lookup_air_decompression_row(180, 70)
        self.assertEqual(row.time_to_first_stop, "3:20")
        self.assertEqual(row.stops_fsw, {80: 4, 70: 12, 60: 21, 50: 24, 40: 25, 30: 48, 20: 499})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 5.5)
        self.assertEqual(row.section, "csv_import")

    def test_lookup_csv_backed_190_fsw_row(self) -> None:
        row = lookup_air_decompression_row(190, 120)
        self.assertEqual(row.time_to_first_stop, "3:00")
        self.assertEqual(row.stops_fsw, {100: 15, 90: 17, 80: 19, 70: 20, 60: 37, 50: 46, 40: 79, 30: 113, 20: 691})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.chamber_o2_periods, 10.5)
        self.assertEqual(row.section, "csv_import")

    def test_basic_profile_rounds_depth_and_time_up_conservatively(self) -> None:
        profile = build_basic_air_decompression_profile(31, 241)
        self.assertEqual(profile.table_depth_fsw, 35)
        self.assertEqual(profile.table_bottom_time_min, 270)
        self.assertEqual(profile.time_to_first_stop, "0:30")
        self.assertEqual(profile.first_stop_depth_fsw, 20)
        self.assertEqual(profile.stops_fsw, {20: 28})
        self.assertIsNone(profile.total_ascent_time)

    def test_basic_profile_uses_exact_supported_row_when_available(self) -> None:
        profile = build_basic_air_decompression_profile(60, 90)
        self.assertEqual(profile.table_depth_fsw, 60)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop, "1:20")
        self.assertEqual(profile.first_stop_depth_fsw, 20)
        self.assertEqual(profile.stops_fsw, {20: 23})
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_uses_new_rounded_depths(self) -> None:
        profile = build_basic_air_decompression_profile(76, 81)
        self.assertEqual(profile.table_depth_fsw, 80)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop, "2:00")
        self.assertEqual(profile.first_stop_depth_fsw, 20)
        self.assertEqual(profile.first_stop_time_min, 114)
        self.assertEqual(profile.stops_fsw, {20: 114})
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_use_csv_backed_depths(self) -> None:
        profile = build_basic_air_decompression_profile(99, 149)
        self.assertEqual(profile.table_depth_fsw, 100)
        self.assertEqual(profile.table_bottom_time_min, 150)
        self.assertEqual(profile.time_to_first_stop, "1:40")
        self.assertEqual(profile.first_stop_depth_fsw, 50)
        self.assertEqual(profile.first_stop_time_min, 3)
        self.assertEqual(profile.stops_fsw, {50: 3, 40: 26, 30: 46, 20: 461})
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_round_into_new_csv_depths(self) -> None:
        profile = build_basic_air_decompression_profile(121, 129)
        self.assertEqual(profile.table_depth_fsw, 130)
        self.assertEqual(profile.table_bottom_time_min, 180)
        self.assertEqual(profile.time_to_first_stop, "2:00")
        self.assertEqual(profile.first_stop_depth_fsw, 70)
        self.assertEqual(profile.first_stop_time_min, 13)
        self.assertEqual(profile.stops_fsw, {70: 13, 60: 21, 50: 45, 40: 57, 30: 94, 20: 658})
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_air_o2_profile_uses_seed_csv(self) -> None:
        profile = build_basic_air_o2_decompression_profile(89, 120)
        self.assertEqual(profile.mode, DecompressionMode.AIR_O2)
        self.assertEqual(profile.table_depth_fsw, 90)
        self.assertEqual(profile.table_bottom_time_min, 120)
        self.assertEqual(profile.first_stop_depth_fsw, 40)
        self.assertEqual(profile.first_stop_time_min, 2)
        self.assertEqual(profile.stops_fsw, {40: 2, 30: 14, 20: 70})

    def test_air_o2_shift_plan_tracks_oxygen_stops(self) -> None:
        profile = build_basic_air_o2_decompression_profile(89, 120)
        self.assertEqual(air_o2_oxygen_stop_depths(profile), (30, 20))
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        self.assertEqual(shift_plan.first_oxygen_stop_depth_fsw, 30)
        self.assertFalse(shift_plan.travel_shift_vent_starts_on_arrival)
        self.assertEqual(shift_plan.travel_shift_vent_start_depth_fsw, 40)

    def test_air_o2_shift_plan_starts_on_arrival_when_first_stop_is_oxygen_stop(self) -> None:
        profile = build_basic_air_o2_decompression_profile(60, 170)
        self.assertEqual(air_o2_oxygen_stop_depths(profile), (20,))
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        self.assertEqual(shift_plan.first_oxygen_stop_depth_fsw, 20)
        self.assertTrue(shift_plan.travel_shift_vent_starts_on_arrival)
        self.assertEqual(shift_plan.travel_shift_vent_start_depth_fsw, 20)

    def test_generic_profile_builder_can_use_air_o2_mode(self) -> None:
        profile = build_basic_decompression_profile(DecompressionMode.AIR_O2, 89, 120)
        self.assertEqual(profile.mode, DecompressionMode.AIR_O2)

    def test_planned_travel_time_to_first_stop_uses_ascent_rate(self) -> None:
        profile = build_basic_air_decompression_profile(113, 60)
        self.assertEqual(planned_travel_time_to_first_stop_seconds(113, profile), 166)

    def test_first_stop_arrival_starts_timer_at_planned_time_when_early(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(115, session, actual_tt1st_seconds=140)

        self.assertEqual(evaluation.outcome, "early_arrival")
        self.assertEqual(evaluation.planned_tt1st_seconds, 170)
        self.assertEqual(evaluation.stop_timer_starts_after_seconds, 170)
        self.assertFalse(evaluation.schedule_changed)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 30)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 19)

    def test_first_stop_arrival_ignores_delay_up_to_one_minute(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(115, session, actual_tt1st_seconds=220)

        self.assertEqual(evaluation.outcome, "ignore_delay")
        self.assertEqual(evaluation.delay_seconds, 50)
        self.assertEqual(evaluation.rounded_delay_minutes, 0)
        self.assertFalse(evaluation.schedule_changed)
        self.assertEqual(evaluation.stop_timer_starts_after_seconds, 220)

    def test_first_stop_arrival_can_use_air_o2_mode(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 11, 0, 0))

        evaluation = evaluate_first_stop_arrival(
            89,
            session,
            actual_tt1st_seconds=140,
            mode=DecompressionMode.AIR_O2,
        )

        self.assertEqual(evaluation.planned_profile.mode, DecompressionMode.AIR_O2)
        self.assertEqual(evaluation.active_profile.mode, DecompressionMode.AIR_O2)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 40)

    def test_first_stop_arrival_adds_delay_to_first_stop_when_delay_begins_shallower_than_50_fsw(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(113, session, actual_tt1st_seconds=380, delay_depth_fsw=40)

        self.assertEqual(evaluation.outcome, "add_to_first_stop")
        self.assertEqual(evaluation.planned_tt1st_seconds, 166)
        self.assertEqual(evaluation.rounded_delay_minutes, 4)
        self.assertTrue(evaluation.schedule_changed)
        self.assertFalse(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 30)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 23)
        self.assertEqual(evaluation.active_profile.stops_fsw, {30: 23, 20: 116})

    def test_first_stop_arrival_adds_delay_to_first_stop_for_shallow_delay_even_when_input_depth_is_deeper(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(121, session, actual_tt1st_seconds=241, delay_depth_fsw=40)

        self.assertEqual(evaluation.outcome, "add_to_first_stop")
        self.assertEqual(evaluation.rounded_delay_minutes, 2)
        self.assertTrue(evaluation.schedule_changed)
        self.assertFalse(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 130)
        self.assertEqual(evaluation.planned_tt1st_seconds, 162)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 55)
        self.assertEqual(evaluation.active_profile.stops_fsw, {40: 6, 30: 28, 20: 146})

    def test_first_stop_arrival_recomputes_when_delay_begins_deeper_than_50(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(121, session, actual_tt1st_seconds=241, delay_depth_fsw=60)

        self.assertEqual(evaluation.outcome, "recompute")
        self.assertEqual(evaluation.planned_tt1st_seconds, 162)
        self.assertEqual(evaluation.rounded_delay_minutes, 2)
        self.assertTrue(evaluation.schedule_changed)
        self.assertFalse(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 130)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 60)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 40)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 12)
        self.assertEqual(evaluation.active_profile.stops_fsw, {40: 12, 30: 28, 20: 170})

    def test_first_stop_arrival_moves_missed_deeper_stops_to_current_depth_for_deeper_than_50_delay(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(171, session, actual_tt1st_seconds=781, delay_depth_fsw=80)

        self.assertEqual(evaluation.outcome, "recompute")
        self.assertEqual(evaluation.planned_tt1st_seconds, 202)
        self.assertEqual(evaluation.rounded_delay_minutes, 10)
        self.assertTrue(evaluation.schedule_changed)
        self.assertTrue(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 180)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 70)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 70)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 16)
        self.assertEqual(evaluation.active_profile.stops_fsw, {70: 16, 60: 21, 50: 24, 40: 25, 30: 48, 20: 499})

    def test_between_stops_delay_ignores_less_than_one_minute(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))
        profile = build_basic_air_decompression_profile_for_session(171, session)

        evaluation = evaluate_between_stops_delay(
            171,
            session,
            profile,
            actual_elapsed_seconds=110,
            planned_elapsed_seconds=60,
            delay_depth_fsw=70,
        )

        self.assertEqual(evaluation.outcome, "ignore_delay")
        self.assertEqual(evaluation.rounded_delay_minutes, 0)
        self.assertFalse(evaluation.schedule_changed)
        self.assertEqual(evaluation.active_profile.stops_fsw, profile.stops_fsw)

    def test_between_stops_delay_ignores_shallow_delay_greater_than_one_minute(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))
        profile = build_basic_air_decompression_profile_for_session(113, session)

        evaluation = evaluate_between_stops_delay(
            113,
            session,
            profile,
            actual_elapsed_seconds=260,
            planned_elapsed_seconds=20,
            delay_depth_fsw=40,
        )

        self.assertEqual(evaluation.outcome, "ignore_delay")
        self.assertEqual(evaluation.rounded_delay_minutes, 0)
        self.assertFalse(evaluation.schedule_changed)
        self.assertEqual(evaluation.active_profile.stops_fsw, profile.stops_fsw)

    def test_between_stops_delay_recomputes_when_delay_is_deeper_than_50(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))
        profile = build_basic_air_decompression_profile_for_session(171, session)

        evaluation = evaluate_between_stops_delay(
            171,
            session,
            profile,
            actual_elapsed_seconds=250,
            planned_elapsed_seconds=60,
            delay_depth_fsw=70,
        )

        self.assertEqual(evaluation.outcome, "recompute")
        self.assertEqual(evaluation.rounded_delay_minutes, 4)
        self.assertTrue(evaluation.schedule_changed)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 180)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 60)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 70)
        self.assertEqual(evaluation.active_profile.stops_fsw, {70: 8, 60: 13, 50: 23, 40: 25, 30: 31, 20: 406})

    def test_basic_profile_can_round_into_140_fsw_rows(self) -> None:
        profile = build_basic_air_decompression_profile(131, 89)
        self.assertEqual(profile.table_depth_fsw, 140)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop, "2:40")
        self.assertEqual(profile.first_stop_depth_fsw, 60)
        self.assertEqual(profile.first_stop_time_min, 12)
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_round_into_150_fsw_rows(self) -> None:
        profile = build_basic_air_decompression_profile(141, 89)
        self.assertEqual(profile.table_depth_fsw, 150)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop, "2:40")
        self.assertEqual(profile.first_stop_depth_fsw, 70)
        self.assertEqual(profile.first_stop_time_min, 3)
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_round_into_160_fsw_rows(self) -> None:
        profile = build_basic_air_decompression_profile(151, 79)
        self.assertEqual(profile.table_depth_fsw, 160)
        self.assertEqual(profile.table_bottom_time_min, 80)
        self.assertEqual(profile.time_to_first_stop, "3:00")
        self.assertEqual(profile.first_stop_depth_fsw, 70)
        self.assertEqual(profile.first_stop_time_min, 6)
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_round_into_180_fsw_rows(self) -> None:
        profile = build_basic_air_decompression_profile(171, 69)
        self.assertEqual(profile.table_depth_fsw, 180)
        self.assertEqual(profile.table_bottom_time_min, 70)
        self.assertEqual(profile.time_to_first_stop, "3:20")
        self.assertEqual(profile.first_stop_depth_fsw, 80)
        self.assertEqual(profile.first_stop_time_min, 4)
        self.assertIsNone(profile.total_ascent_time)
        self.assertEqual(profile.section, "csv_import")

    def test_basic_profile_can_use_bottom_time_from_dive_session(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 1, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 1, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 1, 9, 22, 1))

        profile = build_basic_air_decompression_profile_for_session(31, session)

        self.assertEqual(profile.input_bottom_time_min, 23)
        self.assertEqual(profile.table_depth_fsw, 35)
        self.assertIsNone(profile.table_bottom_time_min)
        self.assertIsNone(profile.time_to_first_stop)
        self.assertEqual(profile.repeat_group, "B")
        self.assertEqual(profile.section, "no_decompression")

    def test_basic_profile_uses_no_decompression_table_below_first_deco_row(self) -> None:
        profile = build_basic_air_decompression_profile(31, 23)
        self.assertEqual(profile.table_depth_fsw, 35)
        self.assertIsNone(profile.table_bottom_time_min)
        self.assertIsNone(profile.time_to_first_stop)
        self.assertIsNone(profile.first_stop_depth_fsw)
        self.assertEqual(profile.repeat_group, "B")
        self.assertEqual(profile.section, "no_decompression")


if __name__ == "__main__":
    unittest.main()
