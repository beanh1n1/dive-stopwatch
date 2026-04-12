from datetime import datetime
import unittest

from dive_stopwatch.v2.dive_session import DiveSession


class DiveSessionTests(unittest.TestCase):
    def test_summary_for_no_decompression_dive(self) -> None:
        session = DiveSession()

        session.leave_surface(datetime(2026, 3, 30, 9, 0, 0))
        session.reach_bottom(datetime(2026, 3, 30, 9, 3, 1))
        session.leave_bottom(datetime(2026, 3, 30, 9, 25, 1))
        session.reach_surface(datetime(2026, 3, 30, 9, 33, 5))

        self.assertEqual(
            session.summary(),
            {
                "LS": "09:00:00",
                "RB": "09:03:01",
                "LB": "09:25:01",
                "RS": "09:33:05",
                "DT": 4,
                "BT": 26,
                "AT": "08:04",
                "TDT": 9,
                "TTD": 34,
            },
        )

    def test_metrics_require_complete_session(self) -> None:
        session = DiveSession()
        session.leave_surface(datetime(2026, 3, 30, 9, 0, 0))
        session.reach_bottom(datetime(2026, 3, 30, 9, 2, 0))

        with self.assertRaises(RuntimeError):
            session.metrics()

    def test_events_must_be_recorded_in_order(self) -> None:
        session = DiveSession()

        with self.assertRaises(RuntimeError):
            session.reach_bottom(datetime(2026, 3, 30, 9, 2, 0))

        session.leave_surface(datetime(2026, 3, 30, 9, 0, 0))

        with self.assertRaises(RuntimeError):
            session.leave_surface(datetime(2026, 3, 30, 9, 1, 0))

        with self.assertRaises(RuntimeError):
            session.reach_bottom(datetime(2026, 3, 30, 8, 59, 59))
