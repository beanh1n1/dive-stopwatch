from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.core import EngineV2
from dive_stopwatch.v2.models import IntentV2


class V2P2ParityTests(unittest.TestCase):
    def _build_air_o2_engine(self, start: datetime) -> tuple[EngineV2, dict[str, datetime]]:
        current = {"now": start}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        return engine, current

    def _advance_to_first_o2_stop(self, engine: EngineV2, current: dict[str, datetime]) -> None:
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(IntentV2.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R3 (first O2 stop)

    def test_mode_and_deco_audit_phrasing(self) -> None:
        engine, _ = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))

        self.assertGreaterEqual(len(engine.state.log_lines), 2)
        self.assertEqual(engine.state.log_lines[0], "Mode -> DIVE")
        self.assertEqual(engine.state.log_lines[1], "Deco -> AIR/O2")

    def test_delay_rule_audit_phrasing(self) -> None:
        engine, current = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB (travel)

        engine.dispatch(IntentV2.SECONDARY)  # start delay
        current["now"] += timedelta(seconds=30)
        engine.dispatch(IntentV2.SECONDARY)  # end delay

        self.assertIn("Delay 1 start", engine.state.log_lines)
        self.assertIn("Delay 1 end", engine.state.log_lines)

    def test_o2_and_air_break_audit_phrasing(self) -> None:
        engine, current = self._build_air_o2_engine(datetime(2026, 4, 12, 10, 0, 0))
        self._advance_to_first_o2_stop(engine, current)

        engine.dispatch(IntentV2.SECONDARY)  # On O2 at first O2 stop
        self.assertTrue(engine.state.log_lines[-1].startswith("On O2 "))

        current["now"] += timedelta(minutes=30)
        engine.dispatch(IntentV2.SECONDARY)  # start air break
        self.assertTrue(engine.state.log_lines[-1].startswith("Air break start "))

        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.SECONDARY)  # warn incomplete break
        self.assertTrue(engine.state.log_lines[-1].startswith("Complete break first ("))

        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.SECONDARY)  # finish break
        self.assertTrue(engine.state.log_lines[-1].startswith("Back on O2 "))


if __name__ == "__main__":
    unittest.main()
