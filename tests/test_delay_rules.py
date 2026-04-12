import unittest

from dive_stopwatch.v2.delay_rules import (
    evaluate_between_stops_delay_rule,
    evaluate_first_stop_delay_rule,
)


class DelayRuleTests(unittest.TestCase):
    def test_first_stop_exactly_one_minute_is_ignored(self) -> None:
        decision = evaluate_first_stop_delay_rule(
            actual_tt1st_seconds=180.0,
            planned_tt1st_seconds=120,
            delay_depth_fsw=80,
        )

        self.assertEqual(decision.outcome, "ignore_delay")
        self.assertEqual(decision.rounded_delay_minutes, 0)

    def test_first_stop_shallow_delay_adds_to_first_stop(self) -> None:
        decision = evaluate_first_stop_delay_rule(
            actual_tt1st_seconds=181.0,
            planned_tt1st_seconds=120,
            delay_depth_fsw=50,
        )

        self.assertEqual(decision.outcome, "add_to_first_stop")
        self.assertEqual(decision.rounded_delay_minutes, 2)

    def test_first_stop_deep_delay_recomputes(self) -> None:
        decision = evaluate_first_stop_delay_rule(
            actual_tt1st_seconds=181.0,
            planned_tt1st_seconds=120,
            delay_depth_fsw=51,
        )

        self.assertEqual(decision.outcome, "recompute")
        self.assertEqual(decision.rounded_delay_minutes, 2)

    def test_between_stops_exactly_one_minute_is_ignored(self) -> None:
        decision = evaluate_between_stops_delay_rule(
            actual_elapsed_seconds=180.0,
            planned_elapsed_seconds=120,
            delay_depth_fsw=80,
        )

        self.assertEqual(decision.outcome, "ignore_delay")
        self.assertEqual(decision.rounded_delay_minutes, 0)

    def test_between_stops_at_fifty_fsw_is_shallow_ignore(self) -> None:
        decision = evaluate_between_stops_delay_rule(
            actual_elapsed_seconds=181.0,
            planned_elapsed_seconds=120,
            delay_depth_fsw=50,
        )

        self.assertEqual(decision.outcome, "ignore_delay")
        self.assertEqual(decision.rounded_delay_minutes, 0)

    def test_between_stops_deeper_than_fifty_recomputes(self) -> None:
        decision = evaluate_between_stops_delay_rule(
            actual_elapsed_seconds=181.0,
            planned_elapsed_seconds=120,
            delay_depth_fsw=51,
        )

        self.assertEqual(decision.outcome, "recompute")
        self.assertEqual(decision.rounded_delay_minutes, 2)


if __name__ == "__main__":
    unittest.main()
