from datetime import datetime, timedelta
import unittest

from dive_stopwatch.minimal.profiles import DecoMode, apply_between_stop_delay, apply_first_stop_delay, build_profile, first_stop_depth, next_stop_after, stop_by_index


class MinimalTablesTests(unittest.TestCase):
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

        self.assertEqual(result.outcome, "add_to_first_stop")
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

        self.assertEqual(result.outcome, "ignore_delay")
        self.assertEqual(result.delay_min, 0)
        self.assertFalse(result.schedule_changed)

    def test_first_stop_delay_recomputes_for_deeper_delay(self) -> None:
        profile = build_profile(DecoMode.AIR, 121, 55)

        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=241,
            delay_depth_fsw=60,
        )

        self.assertEqual(result.outcome, "recompute")
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

        self.assertEqual(result.outcome, "add_to_first_stop")
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

        self.assertEqual(result.outcome, "ignore_delay")
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

        self.assertEqual(result.outcome, "ignore_delay")
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

        self.assertEqual(result.outcome, "ignore_delay")
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

        self.assertEqual(result.outcome, "recompute")
        self.assertEqual(result.delay_min, 4)
        self.assertTrue(result.schedule_changed)
        self.assertEqual(result.profile.table_depth_fsw, 180)
        self.assertEqual(result.profile.table_bottom_time_min, 60)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in result.profile.stops], [(70, 8), (60, 13), (50, 23), (40, 25), (30, 31), (20, 406)])


if __name__ == "__main__":
    unittest.main()
