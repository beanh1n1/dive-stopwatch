from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.air_o2_profiles import DecoMode, DelayOutcome
from dive_stopwatch.core.redesign.air_runtime import OperatorAction, RedesignDiveEngine, RedesignDivePhase


class RedesignAirRuntimeTests(unittest.TestCase):
    def test_convert_to_air_replaces_remaining_o2_schedule_at_current_stop(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth_text("145")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(OperatorAction.REACH_STOP)  # 30
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.TOGGLE_OFF_O2)

        off_o2 = engine.snapshot()
        self.assertEqual(off_o2.primary_button_label, "Convert to Air")
        self.assertEqual(off_o2.secondary_button_label, "On O2")
        self.assertEqual(off_o2.depth_timer_text, "09:00 left")

        engine.convert_to_air()

        converted = engine.snapshot()
        self.assertEqual(engine.state.plan.profile.mode, DecoMode.AIR)
        self.assertEqual(engine.state.plan.current_stop_index, 3)
        self.assertEqual(converted.status_value_text, "At Stop")
        self.assertEqual(converted.depth_text, "30 fsw")
        self.assertEqual(converted.primary_text, "00:00.0")
        self.assertEqual(converted.depth_timer_text, "18:00 left")
        self.assertEqual(converted.summary_text, "Next: 20 fsw for 142 min")
        self.assertEqual(converted.primary_button_label, "Leave Stop")
        self.assertEqual(converted.secondary_button_label, "")
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in engine.state.plan.profile.stops],
            [(50, 3, "air"), (40, 8, "air"), (30, 18, "air"), (20, 142, "air")],
        )
        self.assertTrue(engine.recall_lines()[-2].startswith("Convert to Air "))
        self.assertIn("Converted remaining O2 at 30 fsw", engine.recall_lines()[-1])

    def test_off_o2_pause_does_not_reduce_remaining_o2_obligation(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth_text("145")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(OperatorAction.REACH_STOP)
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.TOGGLE_OFF_O2)

        start = engine.snapshot()
        self.assertEqual(start.depth_timer_text, "09:00 left")

        current["now"] += timedelta(minutes=2)
        after = engine.snapshot()
        self.assertEqual(after.primary_text, "02:00.0")
        self.assertEqual(after.depth_timer_text, "09:00 left")

    def test_o2_travel_delay_reduces_twenty_stop_and_records_credit(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth_text("145")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=37)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(OperatorAction.REACH_STOP)  # 30
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=10)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.depth_text, "25 fsw")
        self.assertEqual(after_delay.summary_text, "Next: 20 fsw for 33 min")
        self.assertIsNotNone(engine.state.last_delay_result)
        self.assertEqual(engine.state.last_delay_result.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(engine.state.last_delay_result.credited_o2_min, 2)
        self.assertEqual(engine.state.last_delay_result.air_interruption_min, 0)
        self.assertTrue(engine.recall_lines()[-1].startswith("O2 delay credited (+2m)"))

        current["now"] += timedelta(seconds=10)
        engine.dispatch(OperatorAction.REACH_STOP)
        at_twenty = engine.snapshot()
        self.assertEqual(at_twenty.depth_text, "20 fsw")
        self.assertTrue(at_twenty.summary_text.startswith("Next: "))
        self.assertEqual(at_twenty.secondary_button_label, "Off O2")

    def test_o2_travel_delay_with_air_interrupt_resets_o2_segment(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth_text("190")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=32)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=4)
        engine.dispatch(OperatorAction.REACH_STOP)  # 70
        current["now"] += timedelta(minutes=4)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)  # 60
        current["now"] += timedelta(minutes=5)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=6)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40
        current["now"] += timedelta(minutes=8)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)  # 30
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=13)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.summary_text, "Next: 20 fsw for 28 min")
        self.assertIsNotNone(engine.state.last_delay_result)
        self.assertEqual(engine.state.last_delay_result.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(engine.state.last_delay_result.credited_o2_min, 17)
        self.assertEqual(engine.state.last_delay_result.air_interruption_min, 3)
        self.assertEqual(engine.recall_lines()[-1], "O2 delay interruption (3m air) ignored for O2 credit")
        self.assertIsNotNone(engine.state.o2_anchor)
        self.assertEqual(engine.state.o2_anchor.started_at, current["now"])

        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)
        at_twenty = engine.snapshot()
        self.assertEqual(at_twenty.depth_text, "20 fsw")
        self.assertEqual(at_twenty.summary_text, "Next: Surface")

    def test_o2_surface_departure_delay_resets_o2_segment_and_preserves_surface_travel(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        self._reach_final_twenty_departure_point(engine, current)

        current["now"] += timedelta(seconds=10)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)
        current["now"] += timedelta(minutes=1)

        while_delayed = engine.snapshot()
        self.assertEqual(while_delayed.status_text, "TRAVELING")
        self.assertEqual(while_delayed.status_value_text, "Traveling")
        self.assertEqual(while_delayed.primary_value_kind, "default")

        current["now"] += timedelta(minutes=4)
        engine.dispatch(OperatorAction.TOGGLE_DELAY)

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.status_value_text, "On O2/ Traveling")
        self.assertEqual(after_delay.summary_text, "Next: Surface")
        self.assertIsNotNone(engine.state.last_delay_result)
        self.assertEqual(engine.state.last_delay_result.outcome, DelayOutcome.O2_SURFACE_DELAY)
        self.assertEqual(engine.state.last_delay_result.delay_min, 5)
        self.assertEqual(engine.state.last_delay_result.credited_o2_min, 0)
        self.assertEqual(engine.state.last_delay_result.air_interruption_min, 5)
        self.assertEqual(engine.recall_lines()[-1], "20 fsw O2 departure delay interruption (5m air) ignored")
        self.assertEqual(engine.recall_lines()[-2], "20 fsw departure delay ignored (+5m); 5m on air before surface")
        self.assertIsNotNone(engine.state.o2_anchor)
        self.assertEqual(engine.state.o2_anchor.started_at, current["now"])

    def test_air_break_uses_explicit_phase_and_blocks_early_return(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = RedesignDiveEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth_text("120")

        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=87)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=7)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40
        current["now"] += timedelta(minutes=26)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 30
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=14)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 20
        current["now"] += timedelta(minutes=14)

        due = engine.snapshot()
        self.assertEqual(due.summary_text, "Next: Air break in 00:00")
        self.assertEqual(due.secondary_button_label, "Off O2")

        engine.dispatch(OperatorAction.TOGGLE_OFF_O2)

        break_start = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignDivePhase.AT_O2_STOP_AIR_BREAK)
        self.assertEqual(break_start.status_value_text, "Off O2")
        self.assertEqual(break_start.summary_text, "Next: On O2")
        self.assertEqual(break_start.primary_text, "00:00.0")
        self.assertEqual(break_start.depth_timer_text, "64:00 left")
        self.assertEqual(break_start.remaining_text, "")
        self.assertEqual(break_start.primary_button_label, "Convert to Air")
        self.assertEqual(break_start.secondary_button_label, "On O2")
        self.assertEqual(engine.recall_lines()[-1], f"Off O2 {current['now'].strftime('%H:%M:%S')}")

        current["now"] += timedelta(minutes=2)
        remaining_before = break_start.depth_timer_text
        engine.dispatch(OperatorAction.TOGGLE_OFF_O2)
        blocked = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignDivePhase.AT_O2_STOP_AIR_BREAK)
        self.assertEqual(blocked.summary_text, "Next: On O2")
        self.assertEqual(blocked.depth_timer_text, "64:00 left")
        self.assertEqual(engine.recall_lines()[-1], "Complete break first (03:00)")
        self.assertEqual(blocked.depth_timer_text, remaining_before)

        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.TOGGLE_OFF_O2)

        resumed = engine.snapshot()
        self.assertEqual(engine.state.phase, RedesignDivePhase.AT_O2_STOP_ON_O2)
        self.assertEqual(resumed.status_value_text, "On O2")
        self.assertEqual(resumed.secondary_button_label, "Off O2")
        self.assertEqual(resumed.depth_timer_text, "64:00 left")
        self.assertEqual(engine.recall_lines()[-1], f"Back on O2 {current['now'].strftime('%H:%M:%S')}")
        self.assertIsNotNone(engine.state.o2_anchor)
        self.assertEqual(engine.state.o2_anchor.started_at, current["now"])

    def _reach_final_twenty_departure_point(self, engine: RedesignDiveEngine, current: dict[str, datetime]) -> None:
        engine.set_depth_text("145")
        engine.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=37)
        engine.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(OperatorAction.REACH_STOP)  # 50
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(OperatorAction.REACH_STOP)  # 40
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(OperatorAction.REACH_STOP)  # 30
        engine.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(OperatorAction.REACH_STOP)  # 20
        current["now"] += timedelta(minutes=35)
        engine.dispatch(OperatorAction.LEAVE_STOP)


if __name__ == "__main__":
    unittest.main()
