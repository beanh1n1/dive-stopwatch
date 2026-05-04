from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.redesign.surd_runtime import (
    OperatorAction,
    RedesignSURDEngine,
    RedesignSURDPhase,
)


class RedesignSURDRuntimeTests(unittest.TestCase):
    def test_normal_path_handoffs_at_l40_and_enters_chamber_o2(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        engine = RedesignSURDEngine(now_provider=lambda: current["now"])
        engine.set_depth_text("150")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40

        at_l40 = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.AT_WATER_STOP)
        self.assertEqual(at_l40.depth_text, "40 fsw")
        self.assertEqual(at_l40.summary_text, "Next: 40 fsw -> Surface")

        engine.dispatch(OperatorAction.LEAVE_STOP)
        start_surd = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.SURFACE_ASCENT)
        self.assertEqual(start_surd.status_text, "40 -> Surface")
        self.assertEqual(start_surd.depth_timer_text, "05:00 left")
        self.assertTrue(any("SurD start from 40 fsw" in line for line in engine.recall_lines()))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.LEAVE_SURFACE_INTERVAL)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.REACH_CHAMBER_50)

        waiting = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.CHAMBER_WAITING_ON_O2)
        self.assertEqual(waiting.summary_text, "Next: 50 fsw for 15 min")
        self.assertEqual(waiting.secondary_button_label, "On O2")

        engine.dispatch(OperatorAction.TOGGLE_CHAMBER_O2)
        on_o2 = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.CHAMBER_ON_O2)
        self.assertEqual(on_o2.status_text, "50 fsw O2")
        self.assertEqual(on_o2.summary_text, "Next: 40 fsw for 15 min")
        self.assertEqual(on_o2.depth_timer_text, "15:00 left")

    def test_surface_interval_penalty_extends_first_50_segment(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        engine = RedesignSURDEngine(now_provider=lambda: current["now"])
        engine.set_depth_text("150")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)
        engine.dispatch(OperatorAction.LEAVE_STOP)

        current["now"] += timedelta(minutes=5, seconds=10)
        penalty = engine.snapshot()
        self.assertEqual(penalty.summary_text, "Next: Chamber 50 with penalty")
        self.assertEqual(penalty.depth_timer_text, "+00:10")
        self.assertEqual(penalty.depth_timer_kind, "warning")

        engine.dispatch(OperatorAction.REACH_SURFACE)
        engine.dispatch(OperatorAction.LEAVE_SURFACE_INTERVAL)
        engine.dispatch(OperatorAction.REACH_CHAMBER_50)

        waiting = engine.snapshot()
        self.assertEqual(engine.state.surface_penalty_half_periods, 1)
        self.assertEqual(waiting.summary_text, "Next: 50 fsw for 30 min")
        self.assertTrue(any("Surface interval penalty (+15 O2 @ 50)" in line for line in engine.recall_lines()))

    def test_chamber_air_break_is_distinct_phase(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        engine = RedesignSURDEngine(now_provider=lambda: current["now"])
        engine.set_depth_text("150")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.LEAVE_SURFACE_INTERVAL)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(OperatorAction.REACH_CHAMBER_50)
        engine.dispatch(OperatorAction.TOGGLE_CHAMBER_O2)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(OperatorAction.ADVANCE_CHAMBER)  # to 40
        current["now"] += timedelta(minutes=15)
        engine.dispatch(OperatorAction.ADVANCE_CHAMBER)  # to air break

        air_break = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.CHAMBER_AIR_BREAK)
        self.assertEqual(air_break.status_text, "40 fsw Air Break")
        self.assertEqual(air_break.summary_text, "Chamber air break")
        self.assertEqual(air_break.depth_timer_text, "05:00 left")

        current["now"] += timedelta(minutes=5)
        engine.dispatch(OperatorAction.ADVANCE_CHAMBER)

        resumed = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignSURDPhase.CHAMBER_ON_O2)
        self.assertEqual(resumed.status_text, "40 fsw O2")
        self.assertEqual(resumed.summary_text, "O2 period 2")
        self.assertTrue(any("Air break start" in line for line in engine.recall_lines()))


if __name__ == "__main__":
    unittest.main()
