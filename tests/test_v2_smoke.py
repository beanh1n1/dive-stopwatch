from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core import Engine, Intent


class ActiveSmokeTests(unittest.TestCase):
    def test_stopwatch_mode_runs_and_labels(self) -> None:
        engine = Engine(now_provider=lambda: datetime(2026, 4, 11, 12, 0, 0))
        snap = engine.snapshot()
        self.assertEqual(snap.mode_text, "STOPWATCH")
        self.assertEqual(snap.status_text, "READY")

        engine.dispatch(Intent.PRIMARY)
        self.assertEqual(engine.snapshot().status_text, "RUNNING")

    def test_dive_mode_transitions_to_bottom(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # RB

        self.assertEqual(engine.snapshot().status_text, "BOTTOM")

    def test_dynamic_button_labels_follow_active_flow(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)

        ready = engine.snapshot()
        self.assertEqual((ready.primary_button_label, ready.secondary_button_label), ("Leave Surface", ""))
        self.assertEqual((ready.primary_button_enabled, ready.secondary_button_enabled), (True, False))

        engine.dispatch(Intent.PRIMARY)  # LS
        descent = engine.snapshot()
        self.assertEqual((descent.primary_button_label, descent.secondary_button_label), ("Reach Bottom", "Hold"))
        self.assertEqual((descent.primary_button_enabled, descent.secondary_button_enabled), (True, True))

        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        bottom = engine.snapshot()
        self.assertEqual((bottom.primary_button_label, bottom.secondary_button_label), ("Leave Bottom", ""))
        self.assertEqual((bottom.primary_button_enabled, bottom.secondary_button_enabled), (True, False))

    def test_first_oxygen_stop_prompts_for_on_o2(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R3

        snap = engine.snapshot()
        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual((snap.primary_button_label, snap.secondary_button_label), ("Leave Stop", "On O2"))
        self.assertEqual((snap.primary_button_enabled, snap.secondary_button_enabled), (True, True))

    def test_test_time_fast_forward_helper_advances_engine_clock(self) -> None:
        engine = Engine(now_provider=lambda: datetime(2026, 4, 11, 12, 0, 0))
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)

        start = engine.snapshot()
        self.assertEqual(start.primary_text, "00:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: LIVE")

        engine.advance_test_time(300)
        advanced = engine.snapshot()
        self.assertEqual(advanced.primary_text, "05:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: +05:00")

        engine.reset_test_time()
        self.assertEqual(engine.snapshot().primary_text, "00:00.0")
        self.assertEqual(engine.test_time_label(), "Test Time: LIVE")

    def test_depth_estimator_runs_during_descent_and_travel(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS

        current["now"] += timedelta(seconds=90)
        self.assertEqual(engine.snapshot().depth_text, "90 fsw")

        current["now"] += timedelta(seconds=30)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=10)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=1)
        snap = engine.snapshot()
        self.assertEqual(snap.status_text, "TRAVELING")
        self.assertEqual(snap.depth_text, "90 fsw")


if __name__ == "__main__":
    unittest.main()
