from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.profiles import DecoMode, DelayOutcome, apply_between_stop_delay, apply_first_stop_delay, apply_oxygen_surface_delay, apply_oxygen_travel_delay, build_profile, convert_remaining_o2_to_air, first_stop_depth, next_stop_after, stop_by_index


class CoreProfilesTests(unittest.TestCase):
    def test_air_profile_uses_expected_rounded_schedule(self) -> None:
        profile = build_profile(DecoMode.AIR, 131, 89)

        self.assertFalse(profile.is_no_decompression)
        self.assertEqual(profile.table_depth_fsw, 140)
        self.assertEqual(profile.table_bottom_time_min, 90)
        self.assertEqual(profile.time_to_first_stop_sec, 160)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in profile.stops], [(60, 12), (50, 23), (40, 26), (30, 38), (20, 443)])

    def test_air_o2_profile_assigns_o2_only_at_thirty_and_twenty(self) -> None:
        new = build_profile(DecoMode.AIR_O2, 145, 39)

        gases = {stop.depth_fsw: stop.gas for stop in new.stops}
        self.assertEqual(gases[40], "air")
        self.assertEqual(gases[30], "o2")
        self.assertEqual(gases[20], "o2")

    def test_no_decompression_profile_has_no_stops(self) -> None:
        profile = build_profile(DecoMode.AIR, 60, 5)

        self.assertTrue(profile.is_no_decompression)
        self.assertEqual(profile.table_depth_fsw, 60)
        self.assertEqual(profile.stops, ())
        self.assertEqual(profile.repeat_group, "A")

    def test_build_profile_uses_elapsed_minutes(self) -> None:
        leave_surface = datetime(2026, 4, 12, 9, 0, 0)
        leave_bottom = leave_surface + timedelta(minutes=39)

        profile = build_profile(DecoMode.AIR_O2, 145, max((leave_bottom - leave_surface).seconds // 60, 0))

        self.assertEqual(profile.table_depth_fsw, 150)
        self.assertEqual(profile.table_bottom_time_min, 40)

    def test_stop_helpers_use_one_based_indices(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 39)

        self.assertEqual(first_stop_depth(profile), 50)
        self.assertEqual(stop_by_index(profile, 2).depth_fsw, 40)
        self.assertEqual(next_stop_after(profile, 2).depth_fsw, 30)
        self.assertIsNone(next_stop_after(profile, 4))

    def test_first_stop_delay_adds_minutes_to_first_stop_for_shallow_delay(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 55)

        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=380,
            delay_depth_fsw=40,
        )

        self.assertEqual(result.outcome, DelayOutcome.ADD_TO_FIRST_STOP)
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(30, 23), (20, 116)])

    def test_first_stop_delay_exactly_60s_is_ignored_at_depth_gt_50(self) -> None:
        profile = build_profile(DecoMode.AIR, 121, 55)
        planned_time_to_first_stop_sec = profile.time_to_first_stop_sec
        self.assertIsNotNone(planned_time_to_first_stop_sec)

        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=planned_time_to_first_stop_sec + 60,
            delay_depth_fsw=60,
        )

        self.assertEqual(result.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertEqual(result.delay_min, 0)
        self.assertFalse(result.schedule_changed)

    def test_first_stop_delay_recomputes_for_deeper_delay(self) -> None:
        profile = build_profile(DecoMode.AIR, 121, 55)

        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=241,
            delay_depth_fsw=60,
        )

        self.assertEqual(result.outcome, DelayOutcome.RECOMPUTE)
        self.assertEqual(result.delay_min, 2)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 130)
        self.assertEqual(result.profile.table_bottom_time_min, 60)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(40, 12), (30, 28), (20, 170)])

    def test_first_stop_delay_at_exactly_50_fsw_takes_shallow_branch(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 55)

        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=380,
            delay_depth_fsw=50,
        )

        self.assertEqual(result.outcome, DelayOutcome.ADD_TO_FIRST_STOP)
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(30, 23), (20, 116)])

    def test_between_stop_delay_ignores_shallow_delay(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 55)

        result = apply_between_stop_delay(
            profile=profile,
            actual_elapsed_sec=260,
            planned_elapsed_sec=20,
            delay_depth_fsw=40,
        )

        self.assertEqual(result.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertEqual(result.delay_min, 4)
        self.assertFalse(result.schedule_changed)

    def test_between_stop_delay_exactly_60s_is_ignored_at_depth_gt_50(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 55)

        result = apply_between_stop_delay(
            profile=profile,
            actual_elapsed_sec=80,
            planned_elapsed_sec=20,
            delay_depth_fsw=60,
        )

        self.assertEqual(result.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertEqual(result.delay_min, 0)
        self.assertFalse(result.schedule_changed)

    def test_between_stop_delay_at_exactly_50_fsw_is_ignored_not_recomputed(self) -> None:
        profile = build_profile(DecoMode.AIR, 113, 55)

        result = apply_between_stop_delay(
            profile=profile,
            actual_elapsed_sec=260,
            planned_elapsed_sec=20,
            delay_depth_fsw=50,
        )

        self.assertEqual(result.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertEqual(result.delay_min, 4)
        self.assertFalse(result.schedule_changed)

    def test_between_stop_delay_recomputes_for_deep_delay(self) -> None:
        profile = build_profile(DecoMode.AIR, 171, 55)

        result = apply_between_stop_delay(
            profile=profile,
            actual_elapsed_sec=250,
            planned_elapsed_sec=60,
            delay_depth_fsw=70,
        )

        self.assertEqual(result.outcome, DelayOutcome.RECOMPUTE)
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 180)
        self.assertEqual(result.profile.table_bottom_time_min, 60)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(70, 8), (60, 13), (50, 23), (40, 25), (30, 31), (20, 406)])

    def test_oxygen_travel_delay_subtracts_credit_from_subsequent_twenty_stop(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 40)

        result = apply_oxygen_travel_delay(
            profile=profile,
            from_stop_index=3,
            delay_elapsed_sec=120,
            o2_time_before_delay_sec=7 * 60,
        )

        self.assertEqual(result.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(result.delay_min, 2)
        self.assertEqual(result.credited_o2_min, 2)
        self.assertEqual(result.air_interruption_min, 0)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(50, 2), (40, 6), (30, 7), (20, 33)])

    def test_oxygen_travel_delay_caps_credit_at_thirty_minutes_and_tracks_air_interruption(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 190, 35)

        result = apply_oxygen_travel_delay(
            profile=profile,
            from_stop_index=5,
            delay_elapsed_sec=20 * 60,
            o2_time_before_delay_sec=13 * 60,
        )

        self.assertEqual(result.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(result.delay_min, 20)
        self.assertEqual(result.credited_o2_min, 17)
        self.assertEqual(result.air_interruption_min, 3)
        self.assertTrue(result.schedule_changed)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(70, 4), (60, 5), (50, 6), (40, 8), (30, 13), (20, 28)])

    def test_oxygen_surface_delay_is_ignored_when_it_stays_within_continuous_limit(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 40)

        result = apply_oxygen_surface_delay(
            profile=profile,
            from_stop_index=4,
            delay_elapsed_sec=10 * 60,
            o2_time_before_delay_sec=12 * 60,
        )

        self.assertEqual(result.outcome, DelayOutcome.O2_SURFACE_DELAY)
        self.assertEqual(result.delay_min, 10)
        self.assertEqual(result.credited_o2_min, 10)
        self.assertEqual(result.air_interruption_min, 0)
        self.assertFalse(result.schedule_changed)
        self.assertEqual(result.profile, profile)

    def test_oxygen_surface_delay_tracks_air_interruption_after_thirty_minutes(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 40)

        result = apply_oxygen_surface_delay(
            profile=profile,
            from_stop_index=4,
            delay_elapsed_sec=25 * 60,
            o2_time_before_delay_sec=12 * 60,
        )

        self.assertEqual(result.outcome, DelayOutcome.O2_SURFACE_DELAY)
        self.assertEqual(result.delay_min, 25)
        self.assertEqual(result.credited_o2_min, 18)
        self.assertEqual(result.air_interruption_min, 7)
        self.assertFalse(result.schedule_changed)
        self.assertEqual(result.profile, profile)

    def test_convert_remaining_o2_at_thirty_to_air_uses_thirty_ratio_and_full_twenty_air_stop(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 40)

        result = convert_remaining_o2_to_air(
            profile=profile,
            current_stop_index=3,
            remaining_o2_stop_sec=4 * 60,
        )

        self.assertEqual(result.source_stop_depth_fsw, 30)
        self.assertEqual(result.remaining_o2_min, 4)
        self.assertEqual(result.air_to_o2_ratio, 2.0)
        self.assertEqual(result.converted_air_min, 8)
        self.assertEqual(result.profile.mode, DecoMode.AIR)
        self.assertEqual([(stop.depth_fsw, stop.duration_min, stop.gas) for stop in result.profile.stops], [(50, 2, "air"), (40, 6, "air"), (30, 8, "air"), (20, 106, "air")])

    def test_convert_remaining_o2_at_twenty_to_air_uses_twenty_ratio(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 190, 35)

        result = convert_remaining_o2_to_air(
            profile=profile,
            current_stop_index=6,
            remaining_o2_stop_sec=9 * 60,
        )

        self.assertEqual(result.source_stop_depth_fsw, 20)
        self.assertEqual(result.remaining_o2_min, 9)
        self.assertAlmostEqual(result.air_to_o2_ratio, 165 / 45)
        self.assertEqual(result.converted_air_min, 33)
        self.assertEqual(result.profile.mode, DecoMode.AIR)
        self.assertEqual([(stop.depth_fsw, stop.duration_min, stop.gas) for stop in result.profile.stops], [(70, 4, "air"), (60, 5, "air"), (50, 6, "air"), (40, 8, "air"), (30, 26, "air"), (20, 33, "air")])

    def test_convert_remaining_o2_to_air_rejects_non_o2_stop(self) -> None:
        profile = build_profile(DecoMode.AIR_O2, 145, 40)

        with self.assertRaisesRegex(ValueError, "oxygen stop"):
            convert_remaining_o2_to_air(
                profile=profile,
                current_stop_index=2,
                remaining_o2_stop_sec=5 * 60,
            )


if __name__ == "__main__":
    unittest.main()
