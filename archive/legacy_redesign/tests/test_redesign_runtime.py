from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.air_o2_profiles import DecoMode
from dive_stopwatch.core.redesign import OperatorAction, RedesignRuntime


class RedesignRuntimeTests(unittest.TestCase):
    def test_surd_mode_uses_air_runtime_until_explicit_l40_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.SURD, now_provider=lambda: current["now"])
        runtime.set_depth_text("150")

        runtime.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        runtime.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        runtime.dispatch(OperatorAction.REACH_STOP)

        before_handoff = runtime.snapshot()
        self.assertFalse(runtime.state_view.surface_active)
        self.assertEqual(runtime.state_view.phase_name, "AT_AIR_STOP")
        self.assertEqual(before_handoff.mode_text, "SURD")
        self.assertEqual(before_handoff.summary_text, "Next: 40 fsw -> Surface")

        runtime.dispatch(OperatorAction.LEAVE_STOP)

        after_handoff = runtime.snapshot()
        self.assertTrue(runtime.state_view.surface_active)
        self.assertEqual(runtime.state_view.phase_name, "SURFACE_ASCENT")
        self.assertEqual(after_handoff.status_text, "40 -> Surface")
        self.assertTrue(any("SurD start from 40 fsw" in line for line in runtime.recall_lines()))

    def test_surd_runtime_keeps_single_snapshot_contract_across_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.SURD, now_provider=lambda: current["now"])
        runtime.set_depth_text("150")

        runtime.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        runtime.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=1)
        runtime.dispatch(OperatorAction.REACH_SURFACE)

        snap = runtime.snapshot()
        self.assertEqual(snap.mode_text, "SURD")
        self.assertTrue(hasattr(snap, "status_text"))
        self.assertTrue(hasattr(snap, "depth_text"))
        self.assertTrue(hasattr(snap, "summary_text"))
        self.assertEqual(snap.status_text, "Undress")

    def test_air_modes_flow_through_same_runtime_entry(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        runtime.set_depth_text("145")

        runtime.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=37)
        runtime.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.CONFIRM_ON_O2)

        snap = runtime.snapshot()
        self.assertEqual(runtime.state_view.phase_name, "AT_O2_STOP_ON_O2")
        self.assertEqual(snap.mode_text, "AIR/O2")
        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.secondary_button_label, "Off O2")

    def test_invalid_action_is_no_op_before_surd_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.SURD, now_provider=lambda: current["now"])
        runtime.set_depth_text("150")
        before = runtime.snapshot()

        runtime.dispatch(OperatorAction.ADVANCE_CHAMBER)

        after = runtime.snapshot()
        self.assertEqual(runtime.state_view.phase_name, "READY")
        self.assertEqual(after, before)
        self.assertEqual(runtime.recall_lines(), ())

    def test_invalid_action_is_no_op_after_surd_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 23, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.SURD, now_provider=lambda: current["now"])
        runtime.set_depth_text("150")

        runtime.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=42)
        runtime.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)

        before = runtime.snapshot()
        recall_before = runtime.recall_lines()

        runtime.dispatch(OperatorAction.REACH_BOTTOM)

        after = runtime.snapshot()
        self.assertTrue(runtime.state_view.surface_active)
        self.assertEqual(runtime.state_view.phase_name, "SURFACE_ASCENT")
        self.assertEqual(after, before)
        self.assertEqual(runtime.recall_lines(), recall_before)

    def test_convert_to_air_is_available_through_shared_runtime_dispatch(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        runtime = RedesignRuntime(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        runtime.set_depth_text("145")

        runtime.dispatch(OperatorAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        runtime.dispatch(OperatorAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=6)
        runtime.dispatch(OperatorAction.REACH_STOP)
        runtime.dispatch(OperatorAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=3)
        runtime.dispatch(OperatorAction.TOGGLE_OFF_O2)

        off_o2 = runtime.snapshot()
        self.assertEqual(off_o2.primary_button_label, "Convert to Air")

        runtime.dispatch(OperatorAction.CONVERT_TO_AIR)

        converted = runtime.snapshot()
        self.assertEqual(runtime.state_view.phase_name, "AT_AIR_STOP")
        self.assertEqual(converted.status_value_text, "At Stop")
        self.assertEqual(converted.depth_text, "30 fsw")
        self.assertEqual(converted.depth_timer_text, "18:00 left")


if __name__ == "__main__":
    unittest.main()
