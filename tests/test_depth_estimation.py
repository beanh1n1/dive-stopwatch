from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from dive_stopwatch.v2.depth_estimation import descent_hold_depth_for_display, estimate_current_depth
from dive_stopwatch.v2.dive_controller import DiveController


class DepthEstimationTests(unittest.TestCase):
    def test_estimates_descent_depth_at_60_fsw_per_minute(self) -> None:
        controller = DiveController()
        start = datetime(2026, 4, 11, 12, 0, 0)
        controller.start(start)

        depth = estimate_current_depth(
            controller=controller,
            now=start + timedelta(seconds=90),
            max_depth_fsw=120,
            active_profile=None,
        )

        self.assertEqual(depth, 90)

    def test_reports_hold_depth_for_display(self) -> None:
        controller = DiveController()
        start = datetime(2026, 4, 11, 12, 0, 0)
        controller.start(start)
        controller.lap(start + timedelta(minutes=1))

        depth = descent_hold_depth_for_display(
            controller=controller,
            start_time=start + timedelta(minutes=1),
            max_depth_fsw=120,
        )

        self.assertEqual(depth, 60)

    def test_estimates_ascent_depth_before_first_stop(self) -> None:
        controller = DiveController()
        start = datetime(2026, 4, 11, 12, 0, 0)
        controller.start(start)
        controller.start(start + timedelta(minutes=2))
        controller.start(start + timedelta(minutes=22))
        profile = SimpleNamespace(stops_fsw={50: 2, 40: 6})

        depth = estimate_current_depth(
            controller=controller,
            now=start + timedelta(minutes=23),
            max_depth_fsw=120,
            active_profile=profile,
        )

        self.assertEqual(depth, 90)


if __name__ == "__main__":
    unittest.main()
