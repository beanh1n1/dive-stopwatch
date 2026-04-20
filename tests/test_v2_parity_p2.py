from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core import Engine, Intent


class ActiveParityP2Tests(unittest.TestCase):
    def _build_air_o2_engine(self, start: datetime) -> tuple[Engine, dict[str, datetime]]:
        current = {"now": start}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        return engine, current

    def _advance_to_first_o2_stop(self, engine: Engine, current: dict[str, datetime]) -> None:
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

    def test_log_is_event_only_from_mode_setup_onward(self) -> None:
        engine, _ = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        self.assertEqual(engine.state.ui_log, ())

    def test_delay_rule_audit_phrasing(self) -> None:
        engine, current = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)

        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(seconds=30)
        engine.dispatch(Intent.SECONDARY)

        self.assertTrue(any(line.startswith("Delay 1 start ") for line in engine.state.ui_log))
        self.assertTrue(any(line.startswith("Delay 1 end ") for line in engine.state.ui_log))

    def test_o2_and_off_o2_audit_phrasing(self) -> None:
        engine, current = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        self._advance_to_first_o2_stop(engine, current)

        engine.dispatch(Intent.SECONDARY)
        self.assertTrue(engine.state.ui_log[-1].startswith("On O2 "))

        current["now"] += timedelta(minutes=30)
        engine.dispatch(Intent.SECONDARY)
        self.assertTrue(engine.state.ui_log[-1].startswith("Off O2 "))

        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.SECONDARY)
        self.assertTrue(engine.state.ui_log[-1].startswith("Back on O2 "))

    def test_active_off_o2_layout_uses_split_meaningful_lines(self) -> None:
        engine, current = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        self._advance_to_first_o2_stop(engine, current)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(minutes=2)

        snap = engine.snapshot()
        self.assertEqual(snap.primary_text, "02:00.0")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: On O2")
        self.assertEqual(snap.detail_text, "")


if __name__ == "__main__":
    unittest.main()
