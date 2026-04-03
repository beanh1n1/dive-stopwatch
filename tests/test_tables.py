from datetime import datetime
import unittest

from dive_stopwatch.tables.air_decompression import (
    available_air_decompression_depths,
    build_basic_air_decompression_profile,
    build_basic_air_decompression_profile_for_session,
    evaluate_first_stop_arrival,
    lookup_air_decompression_row,
    planned_travel_time_to_first_stop_seconds,
)
from dive_stopwatch.dive_session import DiveSession
from dive_stopwatch.tables.no_decompression import (
    lookup_no_decompression_limit,
    lookup_repetitive_group,
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


class AirDecompressionTableTests(unittest.TestCase):
    def test_supported_depths_are_exposed(self) -> None:
        self.assertEqual(
            available_air_decompression_depths(),
            [30, 35, 40, 45, 50, 55, 60, 75, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190],
        )

    def test_lookup_standard_air_row(self) -> None:
        row = lookup_air_decompression_row(30, 371)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {})
        self.assertIsNone(row.total_ascent_time)
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "csv_import")

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

    def test_first_stop_arrival_requires_delay_zone_when_first_stop_is_shallower_than_50_fsw(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(113, session, actual_tt1st_seconds=380)

        self.assertEqual(evaluation.outcome, "delay_zone_required")
        self.assertEqual(evaluation.planned_tt1st_seconds, 166)
        self.assertEqual(evaluation.rounded_delay_minutes, 4)
        self.assertFalse(evaluation.schedule_changed)
        self.assertFalse(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 120)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 55)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 30)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 19)
        self.assertEqual(evaluation.active_profile.stops_fsw, {30: 19, 20: 116})

    def test_first_stop_arrival_adds_delay_to_first_stop_when_zone_is_shallower_than_50(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(113, session, actual_tt1st_seconds=380, delay_zone="shallower_than_50")

        self.assertEqual(evaluation.outcome, "add_to_first_stop")
        self.assertEqual(evaluation.planned_tt1st_seconds, 166)
        self.assertEqual(evaluation.rounded_delay_minutes, 4)
        self.assertTrue(evaluation.schedule_changed)
        self.assertEqual(evaluation.active_profile.first_stop_depth_fsw, 30)
        self.assertEqual(evaluation.active_profile.first_stop_time_min, 23)
        self.assertEqual(evaluation.active_profile.stops_fsw, {30: 23, 20: 116})

    def test_first_stop_arrival_requires_delay_zone_for_shallow_first_stop_even_when_input_depth_is_deeper(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(121, session, actual_tt1st_seconds=241)

        self.assertEqual(evaluation.outcome, "delay_zone_required")
        self.assertEqual(evaluation.rounded_delay_minutes, 2)
        self.assertFalse(evaluation.schedule_changed)
        self.assertFalse(evaluation.missed_deeper_stop)
        self.assertEqual(evaluation.active_profile.table_depth_fsw, 130)
        self.assertEqual(evaluation.planned_tt1st_seconds, 162)
        self.assertEqual(evaluation.active_profile.table_bottom_time_min, 55)
        self.assertEqual(evaluation.active_profile.stops_fsw, {40: 4, 30: 28, 20: 146})

    def test_first_stop_arrival_recomputes_when_delay_zone_is_deeper_than_50(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 4, 2, 9, 0, 0))
        session.reach_bottom(datetime(2026, 4, 2, 9, 3, 0))
        session.leave_bottom(datetime(2026, 4, 2, 9, 55, 0))

        evaluation = evaluate_first_stop_arrival(121, session, actual_tt1st_seconds=241, delay_zone="deeper_than_50")

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

        evaluation = evaluate_first_stop_arrival(171, session, actual_tt1st_seconds=781, delay_zone="deeper_than_50")

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
