from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core import Engine, Intent


class ActiveParityP0Tests(unittest.TestCase):
    def test_phase_sequence_ready_to_surface_for_no_decompression_dive(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("60")
        engine.dispatch(Intent.MODE)

        self.assertEqual(engine.snapshot().status_text, "READY")
        engine.dispatch(Intent.PRIMARY)
        self.assertEqual(engine.snapshot().status_text, "DESCENT")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        self.assertEqual(engine.snapshot().status_text, "BOTTOM")

        current["now"] += timedelta(minutes=10)
        engine.dispatch(Intent.PRIMARY)
        self.assertEqual(engine.snapshot().status_text, "TRAVELING")

        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.PRIMARY)
        self.assertEqual(engine.snapshot().status_text, "CLEAN TIME")

    def test_descent_hold_start_and_end_are_visible(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)

        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(seconds=20)
        snap = engine.snapshot()
        self.assertEqual(snap.secondary_button_label, "Stop Hold")
        self.assertTrue(snap.detail_text.startswith("H1"))

        engine.dispatch(Intent.SECONDARY)
        self.assertEqual(engine.snapshot().secondary_button_label, "Hold")
        self.assertTrue(any(line.startswith("H1 start ") for line in engine.state.ui_log))
        self.assertTrue(any(line.startswith("H1 end ") for line in engine.state.ui_log))

    def test_ascent_stop_arrival_departure_sequence_is_logged(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)

        self.assertTrue(any(line.startswith("R1 ") for line in engine.state.ui_log))
        self.assertTrue(any(line.startswith("L1 ") for line in engine.state.ui_log))

    def test_ascent_delay_start_end_sequence_is_logged(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)

        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.SECONDARY)

        self.assertTrue(any(line.startswith("Delay 1 start ") for line in engine.state.ui_log))
        self.assertTrue(any(line.startswith("Delay 1 end ") for line in engine.state.ui_log))

    def test_first_o2_confirmation_sets_segment_state(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)

        engine.dispatch(Intent.SECONDARY)
        self.assertEqual(engine.state.dive.oxygen.first_confirmed_at, current["now"])
        self.assertEqual(engine.state.dive.oxygen.segment_started_at, current["now"])
        self.assertIsNone(engine.state.dive.oxygen.active_air_break)

    def test_off_o2_primary_timer_tracks_elapsed_deviation(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(Intent.SECONDARY)

        self.assertEqual(engine.snapshot().primary_text, "00:00.0")
        current["now"] += timedelta(minutes=2)
        self.assertEqual(engine.snapshot().primary_text, "02:00.0")

    def test_bottom_summary_reports_required_stop_and_time(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)

        summary = engine.snapshot().summary_text
        self.assertTrue(summary.startswith("Next: 50 fsw for "))
        self.assertTrue(summary.endswith(" min"))

    def test_terminal_o2_stop_can_prioritize_air_break_when_due(self) -> None:
        current = {"now": datetime(2026, 4, 13, 10, 22, 2)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        current["now"] = datetime(2026, 4, 13, 10, 22, 2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 10, 24, 5)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 11, 44, 9)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 11, 47, 20)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 11, 54, 25)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 11, 55, 29)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 12, 21, 37)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 12, 22, 40)
        engine.dispatch(Intent.PRIMARY)
        engine.dispatch(Intent.SECONDARY)
        current["now"] = datetime(2026, 4, 13, 12, 36, 59)
        engine.dispatch(Intent.PRIMARY)
        current["now"] = datetime(2026, 4, 13, 12, 38, 2)
        engine.dispatch(Intent.PRIMARY)

        self.assertEqual(engine.snapshot().summary_text, "Next: Air break in 14:38")


if __name__ == "__main__":
    unittest.main()
