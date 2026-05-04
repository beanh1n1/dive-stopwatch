from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import AirEngine, EngineAction
from dive_stopwatch.engine_v2.contracts.events import AuditEventKind
from dive_stopwatch.engine_v2.domain.air_o2_profiles import DecoMode, DelayOutcome


class EngineV2AirSemanticsTests(unittest.TestCase):
    def _wait_until_leaveable(self, engine: AirEngine, current: dict[str, datetime]) -> None:
        remaining = engine.view().current_stop_remaining_sec
        if remaining is not None and remaining > 0:
            current["now"] += timedelta(seconds=remaining)

    def test_first_o2_stop_waits_for_confirmation(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)

        view = engine.view()
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.gas_state_name, "WAITING_ON_O2")
        self.assertEqual(view.obligation.name, "CONFIRM_ON_O2")
        self.assertEqual(view.current_stop_depth_fsw, 30)
        self.assertIn("CONFIRM_ON_O2", view.available_actions)

    def test_o2_confirmation_and_carry_to_next_o2_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)

        view = engine.view()
        current_stop = engine.state.plan.profile.stops[engine.state.plan.current_stop_index - 1]
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.gas_state_name, "ON_O2")
        self.assertEqual(view.current_stop_depth_fsw, 20)
        self.assertEqual(view.current_stop_remaining_sec, (current_stop.duration_min * 60) - (2 * 60))

    def test_convert_to_air_replaces_remaining_current_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        engine.dispatch(EngineAction.CONVERT_TO_AIR)

        view = engine.view()
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.gas_state_name, "AIR")
        self.assertEqual(engine.state.plan.profile.mode, DecoMode.AIR)
        self.assertEqual(view.current_stop_depth_fsw, 30)

    def test_o2_delay_credit_updates_subsequent_twenty_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=10)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.END_DELAY)

        self.assertEqual(engine.state.delay.status.name, "RESOLVED")
        self.assertEqual(engine.state.delay.outcome, DelayOutcome.O2_DELAY_CREDIT)
        next_stop = engine.view().next_stop_duration_min
        self.assertEqual(next_stop, 33)

    def test_valid_delay_and_interruption_transitions_do_not_emit_invalid_action(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=3)
        interruption_events = engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual([event.kind for event in interruption_events], [AuditEventKind.GAS_INTERRUPTED])

        resume_events = engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual([event.kind for event in resume_events], [AuditEventKind.REACHED_STOP])

        current["now"] += timedelta(minutes=4)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=10)
        start_events = engine.dispatch(EngineAction.START_DELAY)
        self.assertEqual([event.kind for event in start_events], [AuditEventKind.DELAY_STARTED])

        current["now"] += timedelta(minutes=2)
        end_events = engine.dispatch(EngineAction.END_DELAY)
        self.assertEqual([event.kind for event in end_events], [AuditEventKind.DELAY_RESOLVED])

    def test_active_delay_freezes_travel_depth_during_fast_forward(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=10)
        before_delay = engine.view()

        engine.dispatch(EngineAction.START_DELAY)
        frozen_depth = engine.view().display_depth_fsw
        current["now"] += timedelta(minutes=2)
        during_delay = engine.view()

        self.assertEqual(before_delay.display_depth_fsw, frozen_depth)
        self.assertEqual(during_delay.display_depth_fsw, frozen_depth)
        self.assertEqual(int(during_delay.active_timer.elapsed_sec), 120)

    def test_depth_resumes_from_frozen_point_after_delay_ends(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="129", depth_fsw=129)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=40)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(seconds=123)

        before_delay = engine.view()
        engine.dispatch(EngineAction.START_DELAY)
        frozen_depth = engine.view().display_depth_fsw
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.END_DELAY)
        after_delay = engine.view()

        self.assertEqual(frozen_depth, before_delay.display_depth_fsw)
        self.assertEqual(after_delay.display_depth_fsw, frozen_depth)

        current["now"] += timedelta(seconds=10)
        resumed = engine.view()
        self.assertLess(resumed.display_depth_fsw, frozen_depth)

    def test_delay_primary_timer_switches_to_delay_elapsed_then_back_to_time_since_lb(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(seconds=10)
        pre_delay = engine.view()

        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=2)
        delay_view = engine.view()
        self.assertEqual(int(delay_view.active_timer.elapsed_sec), 120)

        engine.dispatch(EngineAction.END_DELAY)
        post_delay = engine.view()
        self.assertEqual(int(post_delay.active_timer.elapsed_sec), int(pre_delay.active_timer.elapsed_sec + 120))
        self.assertNotEqual(int(post_delay.active_timer.elapsed_sec), int(pre_delay.active_timer.elapsed_sec))

    def test_first_stop_overtime_persists_until_r1_and_active_delay_timer_resets_per_delay(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="100", depth_fsw=100)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=86)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        current["now"] += timedelta(seconds=65)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=71)
        first_delay_view = engine.view()
        self.assertEqual(int(first_delay_view.active_timer.elapsed_sec), 71)
        self.assertEqual(int(first_delay_view.travel_overtime_sec), 16)

        engine.dispatch(EngineAction.END_DELAY)
        after_first_delay = engine.view()
        self.assertEqual(int(after_first_delay.active_timer.elapsed_sec), 136)
        self.assertEqual(int(after_first_delay.travel_overtime_sec), 16)

        current["now"] += timedelta(seconds=5)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=20)
        second_delay_view = engine.view()
        self.assertEqual(int(second_delay_view.active_timer.elapsed_sec), 20)
        self.assertEqual(int(second_delay_view.travel_overtime_sec), 41)

    def test_resolved_delay_does_not_leave_stop_delay_action_on_later_travel_leg(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        self._reach_thirty_waiting_on_o2(engine, current)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(seconds=30)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.END_DELAY)

        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=36)
        engine.dispatch(EngineAction.LEAVE_STOP)

        view = engine.view()
        self.assertEqual(view.phase_name, "TRAVEL_TO_SURFACE")
        self.assertIn("REACH_SURFACE", view.available_actions)
        self.assertIn("START_DELAY", view.available_actions)
        self.assertNotIn("END_DELAY", view.available_actions)

    def test_reach_surface_enters_clean_time_countdown(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="78", depth_fsw=78)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_SURFACE)

        view = engine.view()
        self.assertEqual(view.phase_name, "COMPLETE")
        self.assertEqual(view.gas_state_name, "CLEAN_TIME")
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.role.name, "CLEAN_TIME")
        self.assertEqual(int(view.active_timer.remaining_sec), 600)

        current["now"] += timedelta(minutes=10, seconds=1)
        ready_view = engine.view()
        self.assertEqual(ready_view.phase_name, "READY")

    def test_air_break_due_surfaces_as_warning_and_state(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="120", depth_fsw=120)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=87)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 40
        current["now"] += timedelta(minutes=26)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 30
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=14)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 20
        current["now"] += timedelta(minutes=14)

        due_view = engine.view()
        self.assertIn("AIR_BREAK_DUE", [warning.name for warning in due_view.warnings])

        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        break_view = engine.view()
        self.assertEqual(break_view.gas_state_name, "AIR_BREAK")
        self.assertEqual(break_view.active_timer.role.name, "AIR_BREAK")

    def test_air_break_due_warning_appears_at_exact_30_min_boundary(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="120", depth_fsw=120)

        self._reach_twenty_on_o2_for_120_90_profile(engine, current)

        current["now"] += timedelta(minutes=13, seconds=59)
        before_boundary = engine.view()
        self.assertNotIn("AIR_BREAK_DUE", [warning.name for warning in before_boundary.warnings])

        current["now"] += timedelta(seconds=1)
        at_boundary = engine.view()
        self.assertIn("AIR_BREAK_DUE", [warning.name for warning in at_boundary.warnings])

    def test_air_break_due_warning_clears_at_exact_35_min_remaining_boundary(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="120", depth_fsw=120)

        self._reach_twenty_on_o2_for_120_90_profile(engine, current)
        arrival_view = engine.view()
        seconds_until_cutoff = int(arrival_view.current_stop_remaining_sec - (35 * 60))
        current["now"] += timedelta(seconds=seconds_until_cutoff)
        cutoff_view = engine.view()
        self.assertEqual(int(cutoff_view.current_stop_remaining_sec), 35 * 60)
        self.assertNotIn("AIR_BREAK_DUE", [warning.name for warning in cutoff_view.warnings])

    def test_air_o2_leave_bottom_uses_legacy_in_water_time_for_table_selection(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR_O2, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="145", depth_fsw=145)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        assert engine.state.plan is not None
        self.assertEqual(engine.state.plan.profile.table_depth_fsw, 150)
        self.assertEqual(engine.state.plan.profile.table_bottom_time_min, 45)
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in engine.state.plan.profile.stops],
            [
                (50, 3, "air"),
                (40, 8, "air"),
                (30, 12, "o2"),
                (20, 40, "o2"),
            ],
        )

    def test_descent_hold_freezes_depth_progress_until_released(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = AirEngine(mode=DecoMode.AIR, now_provider=lambda: current["now"])
        engine.set_depth(raw_text="78", depth_fsw=78)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=30)
        before_hold = engine.view()
        self.assertEqual(before_hold.display_depth_fsw, 30)

        engine.dispatch(EngineAction.START_HOLD)
        current["now"] += timedelta(seconds=45)
        during_hold = engine.view()
        self.assertEqual(during_hold.display_depth_fsw, 30)
        self.assertEqual(during_hold.active_hold_label, "H1   00:45")

        engine.dispatch(EngineAction.END_HOLD)
        current["now"] += timedelta(seconds=15)
        after_hold = engine.view()
        self.assertEqual(after_hold.display_depth_fsw, 45)

    def _reach_thirty_waiting_on_o2(self, engine: AirEngine, current: dict[str, datetime]) -> None:
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=37)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # 50
        self._wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 40
        self._wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 30

    def _reach_twenty_on_o2_for_120_90_profile(self, engine: AirEngine, current: dict[str, datetime]) -> None:
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=87)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 40
        current["now"] += timedelta(minutes=26)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 30
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=14)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # 20


if __name__ == "__main__":
    unittest.main()
