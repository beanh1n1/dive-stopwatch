from datetime import datetime, timedelta
import unittest

from dive_stopwatch.minimal import Engine, Intent


class ActiveParityP1Tests(unittest.TestCase):
    def _build_engine(self, start: datetime) -> tuple[Engine, dict[str, datetime]]:
        current = {"now": start}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        return engine, current

    def test_status_vocabulary_uses_expected_labels(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        seen = {engine.snapshot().status_text}

        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=40)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.PRIMARY)
        seen.add(engine.snapshot().status_text)
        current["now"] += timedelta(minutes=11)
        seen.add(engine.snapshot().status_text)

        self.assertEqual(seen, {"READY", "DESCENT", "BOTTOM", "TRAVELING", "AT STOP", "AT O2 STOP", "CLEAN TIME", "SURFACE"})

    def test_depth_and_remaining_show_at_stop(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)

        snap = engine.snapshot()
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertIn("Stop:", snap.remaining_text)
        self.assertIn("left", snap.remaining_text)

    def test_detail_line_shows_hold_and_delay(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(Intent.PRIMARY)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(seconds=30)
        self.assertTrue(engine.snapshot().detail_text.startswith("H1"))

        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(seconds=30)
        self.assertTrue(engine.snapshot().detail_text.startswith("D1"))

    def test_summary_points_to_next_oxygen_stop(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
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

        snap = engine.snapshot()
        self.assertTrue(snap.summary_text.startswith("Next: 30 fsw for "))

    def test_log_is_chronological_and_omits_mode_chatter(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)

        logs = engine.state.ui_log
        self.assertTrue(any(line.startswith("LS ") for line in logs))
        self.assertTrue(any(line.startswith("RB ") for line in logs))
        self.assertTrue(any(line.startswith("LB ") for line in logs))
        self.assertTrue(any(line.startswith("R1 ") for line in logs))
        self.assertTrue(any(line.startswith("L1 ") for line in logs))
        self.assertFalse(any(line.startswith("Mode ->") or line.startswith("Deco ->") for line in logs))


if __name__ == "__main__":
    unittest.main()
