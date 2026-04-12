from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.core import EngineV2
from dive_stopwatch.v2.models import IntentV2


class V2SmokeTests(unittest.TestCase):
    def test_stopwatch_mode_runs_and_labels(self) -> None:
        engine = EngineV2()
        snap = engine.snapshot()
        self.assertEqual(snap.mode_text, "STOPWATCH")
        self.assertEqual(snap.status.value, "READY")

        engine.dispatch(IntentV2.PRIMARY)
        running = engine.snapshot()
        self.assertEqual(running.status.value, "RUNNING")

    def test_dive_mode_transitions_to_bottom(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        snap = engine.snapshot()
        self.assertEqual(snap.status.value, "BOTTOM")

    def test_dynamic_button_labels_follow_original_flow(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")

        engine.dispatch(IntentV2.MODE)  # DIVE READY
        ready = engine.snapshot()
        self.assertEqual((ready.start_label, ready.secondary_label), ("Leave Surface", ""))
        self.assertEqual((ready.start_enabled, ready.secondary_enabled), (True, False))

        engine.dispatch(IntentV2.PRIMARY)  # DESCENT
        descent = engine.snapshot()
        self.assertEqual((descent.start_label, descent.secondary_label), ("Reach Bottom", "Hold"))
        self.assertEqual((descent.start_enabled, descent.secondary_enabled), (True, True))

        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # BOTTOM
        bottom = engine.snapshot()
        self.assertEqual((bottom.start_label, bottom.secondary_label), ("Leave Bottom", "Delay"))
        self.assertEqual((bottom.start_enabled, bottom.secondary_enabled), (True, True))

    def test_dynamic_button_labels_show_on_o2_at_first_oxygen_stop(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 54, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2

        # Build to first oxygen stop (30 fsw), awaiting confirmation.
        engine.dispatch(IntentV2.PRIMARY)  # LS 09:00:00
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB 09:03:00
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB 09:42:00
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1 09:45:20
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.SECONDARY)  # L1 09:47:20
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R2 09:47:40
        current["now"] += timedelta(minutes=6)
        engine.dispatch(IntentV2.SECONDARY)  # L2 09:53:40
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R3 09:54:00

        at_first_o2_stop = engine.snapshot()
        self.assertEqual((at_first_o2_stop.start_label, at_first_o2_stop.secondary_label), ("Leave Stop", "On O2"))
        self.assertEqual((at_first_o2_stop.start_enabled, at_first_o2_stop.secondary_enabled), (True, True))

    def test_test_time_fast_forward_helper_advances_engine_clock(self) -> None:
        engine = EngineV2(now_provider=lambda: datetime(2026, 4, 11, 12, 0, 0))
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS

        start = engine.snapshot()
        self.assertEqual(start.primary, "00:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: LIVE")

        engine.advance_test_time(300)
        advanced = engine.snapshot()
        self.assertEqual(advanced.primary, "05:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: +05:00")

        engine.reset_test_time()
        reset = engine.snapshot()
        self.assertEqual(reset.primary, "00:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: LIVE")

    def test_depth_estimator_runs_during_descent(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS

        current["now"] += timedelta(seconds=90)
        snap = engine.snapshot()
        self.assertEqual(snap.depth, "90 fsw")

    def test_depth_estimator_runs_during_ascent_travel(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=22)
        engine.dispatch(IntentV2.PRIMARY)  # LB

        current["now"] += timedelta(minutes=1)
        snap = engine.snapshot()
        self.assertEqual(snap.status.value, "TRAVELING")
        self.assertEqual(snap.depth, "90 fsw")

    def test_primary_leave_stop_progresses_from_at_stop(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 45, 20)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1 (at stop)
        at_stop = engine.snapshot()
        self.assertEqual(at_stop.status.value, "AT STOP")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # Leave stop (L1)
        traveling = engine.snapshot()
        self.assertEqual(traveling.status.value, "TRAVELING")
        self.assertIn("L1", " ".join(engine.state.log_lines[-3:]))

    def test_reset_in_dive_mode_works_mid_dive_for_testing(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS

        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        self.assertEqual(engine.snapshot().status.value, "BOTTOM")

        engine.dispatch(IntentV2.RESET)  # force-reset while active
        snap = engine.snapshot()
        self.assertEqual(snap.status.value, "READY")
        self.assertEqual((snap.start_label, snap.secondary_label), ("Leave Surface", ""))

    def test_bottom_remaining_counter_counts_down(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # RB

        before = engine.snapshot().remaining
        self.assertIn("Bottom:", before)
        self.assertIn("left", before)

        current["now"] += timedelta(minutes=1)
        after = engine.snapshot().remaining
        self.assertIn("Bottom:", after)
        self.assertNotEqual(before, after)

    def test_stop_remaining_counter_counts_down(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 45, 20)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1

        before = engine.snapshot().remaining
        self.assertIn("Stop:", before)
        self.assertIn("left", before)

        current["now"] += timedelta(seconds=30)
        after = engine.snapshot().remaining
        self.assertIn("Stop:", after)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
