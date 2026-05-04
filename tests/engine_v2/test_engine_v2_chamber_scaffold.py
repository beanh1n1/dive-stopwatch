from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import ChamberEngine, EngineAction, EngineMode, SurdToChamberHandoff, SurdEntryKind


class EngineV2ChamberScaffoldTests(unittest.TestCase):
    def test_chamber_ready_uses_leave_surface_and_o2_toggle(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        view = engine.view()
        self.assertEqual(view.mode, EngineMode.CHAMBER)
        self.assertEqual(view.phase_name, "READY")
        self.assertIn("LEAVE_SURFACE", view.available_actions)
        self.assertIn("TOGGLE_OFF_O2", view.available_actions)

    def test_chamber_descends_to_60_then_waits_for_explicit_on_o2(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        view = engine.view()
        self.assertEqual(view.phase_name, "DESCENT_TO_60")
        self.assertEqual(view.obligation.name, "REACH_BOTTOM")

        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        view = engine.view()
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.committed_depth_fsw, 60)
        self.assertEqual(view.gas_state_name, "WAITING_ON_O2")
        self.assertEqual(view.available_actions, ("CONFIRM_ON_O2", "RESET"))
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.elapsed_sec, 0.0)

        current["now"] += timedelta(seconds=34)
        view = engine.view()
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.elapsed_sec, 34.0)

    def test_second_60fsw_decision_point_locks_tt5_on_next_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)

        view = engine.view()
        self.assertEqual(view.phase_name, "ON_O2")
        self.assertIn("LEAVE_STOP", view.available_actions)

        engine.dispatch(EngineAction.LEAVE_STOP)
        view = engine.view()
        self.assertEqual(view.phase_name, "TRAVEL_TO_30")
        self.assertEqual(engine.selected_table_name(), "TT5")
        self.assertEqual(view.display_depth_fsw, 60)

        current["now"] += timedelta(seconds=1)
        view = engine.view()
        self.assertEqual(view.display_depth_fsw, 60)

        current["now"] += timedelta(seconds=59)
        view = engine.view()
        self.assertEqual(view.display_depth_fsw, 59)

    def test_first_60fsw_period_previews_air_break_not_next_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)

        self.assertEqual(engine.view().pending_action_text, "5 min air break")

    def test_third_60fsw_tt6_period_previews_air_break_not_next_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)

        self.assertEqual(engine.selected_table_name(), "TT6")
        self.assertEqual(engine.view().pending_action_text, "5 min air break")

    def test_second_60fsw_decision_point_locks_tt6_on_additional_period_path(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        view = engine.view()
        self.assertEqual(view.phase_name, "AIR_BREAK")
        self.assertEqual(engine.selected_table_name(), "TT6")
        self.assertEqual(view.gas_state_name, "AIR_BREAK")

    def test_tt6_allows_leave_stop_after_post_third_break_and_on_o2(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        view = engine.view()
        self.assertEqual(engine.selected_table_name(), "TT6")
        self.assertEqual(view.phase_name, "ON_O2")
        self.assertIn("LEAVE_STOP", view.available_actions)

        engine.dispatch(EngineAction.LEAVE_STOP)
        view = engine.view()
        self.assertEqual(view.phase_name, "TRAVEL_TO_30")

    def test_reach_30_holds_on_o2_until_explicit_arrival_break(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.REACH_STOP)

        view = engine.view()
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.gas_state_name, "ON_O2")
        self.assertEqual(view.pending_action_text, "Air Break for 5 min")
        self.assertEqual(view.available_actions, ("TOGGLE_OFF_O2", "RESET"))
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.elapsed_sec, 0.0)

        current["now"] += timedelta(seconds=42)
        view = engine.view()
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.elapsed_sec, 42.0)

    def test_tt5_first_30_period_requires_mid_break_then_final_on_o2_before_ascent(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)

        view = engine.view()
        self.assertEqual(view.phase_name, "ON_O2")
        self.assertEqual(view.pending_action_text, "5 min air break")
        self.assertIn("TOGGLE_OFF_O2", view.available_actions)

        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        view = engine.view()
        self.assertEqual(view.phase_name, "ON_O2")
        self.assertEqual(view.pending_action_text, "Surface")
        self.assertIn("LEAVE_STOP", view.available_actions)
        self.assertNotIn("TOGGLE_OFF_O2", view.available_actions)

    def test_tt6_reach_30_requires_arrival_break_then_first_60_period(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.REACH_STOP)

        view = engine.view()
        self.assertEqual(engine.selected_table_name(), "TT6")
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.gas_state_name, "ON_O2")
        self.assertEqual(view.pending_action_text, "Air Break for 15 min")
        self.assertEqual(view.available_actions, ("TOGGLE_OFF_O2", "RESET"))

        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=60)

        view = engine.view()
        self.assertEqual(view.phase_name, "ON_O2")
        self.assertEqual(view.pending_action_text, "15 min air break")
        self.assertIn("TOGGLE_OFF_O2", view.available_actions)

    def test_reach_surface_enters_clean_time_then_completes(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.REACH_SURFACE)

        view = engine.view()
        self.assertEqual(view.phase_name, "COMPLETE_CLEAN_TIME")
        self.assertEqual(view.gas_state_name, "CLEAN_TIME")
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.role.name, "CLEAN_TIME")
        self.assertEqual(view.active_timer.remaining_sec, 600.0)

        current["now"] += timedelta(minutes=10)
        view = engine.view()
        self.assertEqual(view.phase_name, "READY")

    def test_start_treatment_stores_handoff_context_and_begins_descent_to_60(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        engine = ChamberEngine(now_provider=lambda: now)
        handoff = SurdToChamberHandoff(
            trigger="SURFACE_INTERVAL_EXCEEDED",
            surface_interval_elapsed_sec=8 * 60 + 1,
            entry_depth_fsw=0,
            source_entry_kind=SurdEntryKind.L40_NORMAL,
            input_depth_fsw=120,
            input_bottom_time_min=90,
            handed_off_at=now,
        )

        engine.start_treatment(handoff)

        self.assertEqual(engine.state.phase.name, "DESCENT_TO_60")
        self.assertEqual(engine.state.current_depth_fsw, 0)
        self.assertEqual(engine.state.descent_timer.started_at, now)
        self.assertEqual(engine.state.treatment_handoff, handoff)


if __name__ == "__main__":
    unittest.main()
