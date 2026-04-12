from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.core import EngineV2
from dive_stopwatch.v2.models import IntentV2


class V2P1ParityTests(unittest.TestCase):
    def _build_engine(self, start: datetime) -> tuple[EngineV2, dict[str, datetime]]:
        current = {"now": start}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        return engine, current

    def test_status_vocabulary_uses_expected_labels(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        seen: set[str] = {engine.snapshot().status.value}

        engine.dispatch(IntentV2.PRIMARY)  # LS -> DESCENT
        seen.add(engine.snapshot().status.value)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB -> BOTTOM
        seen.add(engine.snapshot().status.value)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB -> TRAVELING
        seen.add(engine.snapshot().status.value)
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1 -> AT STOP
        seen.add(engine.snapshot().status.value)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(IntentV2.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R3 (AT O2 STOP pending confirmation)
        seen.add(engine.snapshot().status.value)
        engine.dispatch(IntentV2.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=7)
        engine.dispatch(IntentV2.PRIMARY)  # L3
        current["now"] += timedelta(minutes=1)
        engine.dispatch(IntentV2.PRIMARY)  # R4 at 20
        current["now"] += timedelta(minutes=35)
        engine.dispatch(IntentV2.PRIMARY)  # L4 -> traveling to surface
        current["now"] += timedelta(minutes=1)
        engine.dispatch(IntentV2.PRIMARY)  # RS -> SURFACE
        seen.add(engine.snapshot().status.value)

        self.assertEqual(
            seen,
            {"READY", "DESCENT", "BOTTOM", "TRAVELING", "AT STOP", "AT O2 STOP", "SURFACE"},
        )

    def test_timer_kind_parity_in_key_states(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        self.assertEqual(engine.snapshot().timer_kind, "READY_ZERO")

        engine.dispatch(IntentV2.PRIMARY)  # LS
        self.assertEqual(engine.snapshot().timer_kind, "DESCENT_TOTAL")
        engine.dispatch(IntentV2.SECONDARY)  # hold start
        self.assertEqual(engine.snapshot().timer_kind, "DESCENT_HOLD")
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.SECONDARY)  # hold end
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        self.assertEqual(engine.snapshot().timer_kind, "BOTTOM_ELAPSED")
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        self.assertEqual(engine.snapshot().timer_kind, "ASCENT_TRAVEL")
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1
        self.assertEqual(engine.snapshot().timer_kind, "STOP_TIMER")

    def test_line3_depth_and_modifier_show_at_stop(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1

        snap = engine.snapshot()
        self.assertEqual(snap.depth, "50 fsw")
        self.assertIn("Stop:", snap.remaining)
        self.assertIn("left", snap.remaining)

    def test_line5_event_text_parity_for_hold_and_delay(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(IntentV2.PRIMARY)  # LS
        engine.dispatch(IntentV2.SECONDARY)  # hold start
        current["now"] += timedelta(seconds=30)
        hold_snap = engine.snapshot()
        self.assertTrue(hold_snap.detail.startswith("H1"))

        engine.dispatch(IntentV2.SECONDARY)  # hold end
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        engine.dispatch(IntentV2.SECONDARY)  # delay start during travel
        current["now"] += timedelta(seconds=30)
        delay_snap = engine.snapshot()
        self.assertTrue(delay_snap.detail.startswith("D1"))

    def test_oxygen_target_styling_metadata_parity(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
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
        engine.dispatch(IntentV2.PRIMARY)  # R2 (next is 30 fsw)

        snap = engine.snapshot()
        self.assertTrue(snap.summary.startswith("Next: 30 fsw for "))
        self.assertTrue(snap.summary_targets_oxygen_stop)

    def test_chronological_event_logging(self) -> None:
        engine, current = self._build_engine(datetime(2026, 3, 30, 9, 0, 0))
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # L1

        logs = engine.state.log_lines
        self.assertGreaterEqual(len(logs), 5)
        self.assertTrue(logs[0].startswith("Mode -> DIVE"))
        self.assertTrue(any(line.startswith("LS ") for line in logs))
        self.assertTrue(any(line.startswith("RB ") for line in logs))
        self.assertTrue(any(line.startswith("LB ") for line in logs))
        self.assertTrue(any(line.startswith("R1 ") for line in logs))
        self.assertTrue(any(line.startswith("L1 ") for line in logs))


if __name__ == "__main__":
    unittest.main()
