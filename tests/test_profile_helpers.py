import unittest

from dive_stopwatch.v2.profile_helpers import (
    current_stop_remaining_text,
    next_action_after_air_break,
    next_stop_instruction,
    profile_line_text,
    stop_depth_for_number,
    surface_table_summary,
)
from dive_stopwatch.v2.tables import (
    DecompressionMode,
    build_basic_air_o2_decompression_profile,
    build_basic_decompression_profile,
    lookup_repetitive_group_schedule,
)


class ProfileHelperTests(unittest.TestCase):
    def test_next_stop_instruction_uses_next_stop_depth_and_time(self) -> None:
        profile = build_basic_air_o2_decompression_profile(145, 39)

        text = next_stop_instruction(profile, latest_arrival_stop_number=1)

        self.assertEqual(text, "Next: 40 fsw for 6m")

    def test_next_action_after_air_break_holds_diver_at_twenty(self) -> None:
        profile = build_basic_air_o2_decompression_profile(145, 39)

        text = next_action_after_air_break(
            profile,
            latest_arrival_stop_number=4,
            current_stop_remaining="12:00",
        )

        self.assertEqual(text, "Next: 20 fsw for 12:00")

    def test_profile_line_text_formats_no_decompression_profile(self) -> None:
        profile = build_basic_decompression_profile(DecompressionMode.AIR, 60, 5)
        repet_group, schedule_time = lookup_repetitive_group_schedule(60, 5)

        text = profile_line_text(profile, bottom_time_minutes=5)

        self.assertEqual(text, f"60/{schedule_time}   {repet_group}")

    def test_surface_table_summary_uses_profile_line_text(self) -> None:
        profile = build_basic_air_o2_decompression_profile(145, 39)

        text = surface_table_summary(profile, bottom_time_minutes=39)

        self.assertEqual(text, "150/40   --")

    def test_current_stop_remaining_text_clamps_at_zero(self) -> None:
        self.assertEqual(current_stop_remaining_text(-12.0), "00:00")

    def test_stop_depth_for_number_returns_surface_after_last_stop(self) -> None:
        self.assertEqual(stop_depth_for_number([50, 40, 30, 20], 5), 0)


if __name__ == "__main__":
    unittest.main()
