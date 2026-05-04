from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import EngineAction, MixedGasEngine
from dive_stopwatch.engine_v2.modes.mixed_gas.state import (
    MixedGasBreathingGas,
    MixedGasOxygenState,
    MixedGasPhase,
    MixedGasPlan,
    MixedGasShiftState,
    MixedGasStop,
    MixedGasTimer,
    MixedGasTimerKind,
)
from dive_stopwatch.engine_v2.contracts.timers import TimerState


class EngineV2MixedGasSemanticsTests(unittest.TestCase):
    def test_bottom_phase_exposes_leave_bottom_before_runtime_plan_lookup(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="180", depth_fsw=180)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        view = engine.view()
        self.assertEqual(view.phase_name, "BOTTOM")
        self.assertIn("LEAVE_BOTTOM", view.available_actions)

    def test_leave_bottom_uses_reviewed_table_lookup_for_runtime_plan(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="180", depth_fsw=180)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        self.assertIsNotNone(engine.state.plan)
        assert engine.state.plan is not None
        self.assertEqual(engine.state.plan.table_depth_fsw, 180)
        self.assertEqual(engine.state.plan.table_bottom_time_min, 10)
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in engine.state.plan.stops],
            [
                (70, 7, "50_50"),
                (50, 10, "50_50"),
                (40, 10, "50_50"),
                (30, 9, "o2"),
                (20, 14, "o2"),
            ],
        )
        self.assertEqual(engine.view().phase_name, "TRAVEL_TO_FIRST_STOP")

    def test_first_stop_delay_greater_than_one_minute_adds_to_bottom_time_and_recomputes(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] += timedelta(minutes=4)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=3, seconds=25)
        engine.dispatch(EngineAction.END_DELAY)

        assert engine.state.plan is not None
        self.assertEqual(engine.state.plan.table_bottom_time_min, 20)
        self.assertEqual(engine.view().next_stop_depth_fsw, 90)

    def test_delay_leaving_thirty_subtracts_from_twenty_stop_time(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="150", depth_fsw=150)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        assert engine.state.plan is not None
        original_twenty = next(stop.duration_min for stop in engine.state.plan.stops if stop.depth_fsw == 20)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=9)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=2, seconds=10)
        engine.dispatch(EngineAction.END_DELAY)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)

        current_twenty = next(stop for stop in engine.state.plan.stops if stop.depth_fsw == 20)
        self.assertEqual(current_twenty.duration_min, original_twenty - 3)

    def test_sub_sixteen_launch_pauses_at_twenty_until_bottom_mix_confirmation(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=5)

        descending = engine.view()
        self.assertEqual(descending.phase_name, "DESCENT_TO_20_ON_AIR")
        self.assertLessEqual(descending.display_depth_fsw or 0, 20)

        engine.dispatch(EngineAction.REACH_STOP)
        waiting = engine.view()
        self.assertEqual(waiting.phase_name, "AT_20_PREBOTTOM_SHIFT")
        self.assertEqual(waiting.current_stop_depth_fsw, 20)
        self.assertEqual(waiting.obligation.name, "CONFIRM_BOTTOM_MIX")

    def test_normal_descent_bottom_timer_anchors_at_leave_surface_for_sixteen_or_more_percent(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="150", depth_fsw=150)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        view = engine.view()
        self.assertEqual(view.phase_name, "BOTTOM")
        self.assertEqual(int(view.active_timer.elapsed_sec), 120)

    def test_sub_sixteen_percent_path_anchors_bottom_time_at_leave_twenty_within_grace_window(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] += timedelta(minutes=4)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        view = engine.view()
        self.assertEqual(view.phase_name, "BOTTOM")
        self.assertEqual(int(view.active_timer.elapsed_sec), 120)

    def test_leave_stop_from_twenty_implicitly_commits_bottom_mix(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.LEAVE_STOP)

        view = engine.view()
        self.assertEqual(view.phase_name, "DESCENT_TO_BOTTOM")
        self.assertEqual(view.gas_state_name, "BOTTOM_MIX")

    def test_shift_to_air_at_twenty_enters_abort_ready_air_state(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        engine.dispatch(EngineAction.CONVERT_TO_AIR)

        view = engine.view()
        self.assertEqual(view.phase_name, "AT_20_PREBOTTOM_SHIFT")
        self.assertEqual(view.gas_state_name, "AIR")
        self.assertEqual(view.obligation.name, "LEAVE_BOTTOM")
        self.assertIn("LEAVE_BOTTOM", view.available_actions)
        self.assertIn("CONFIRM_BOTTOM_MIX", view.available_actions)

    def test_leave_bottom_from_abort_ready_twenty_starts_no_penalty_surface_ascent(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        engine.dispatch(EngineAction.CONVERT_TO_AIR)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        self.assertEqual(engine.view().phase_name, "TRAVEL_TO_SURFACE")

    def test_abort_ascent_reach_surface_enters_clean_time(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        engine.dispatch(EngineAction.CONVERT_TO_AIR)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(seconds=40)
        engine.dispatch(EngineAction.REACH_SURFACE)

        view = engine.view()
        self.assertEqual(view.phase_name, "COMPLETE")
        self.assertEqual(view.gas_state_name, "CLEAN_TIME")
        self.assertIsNotNone(view.active_timer)
        assert view.active_timer is not None
        self.assertEqual(view.active_timer.role.name, "CLEAN_TIME")
        self.assertEqual(int(view.active_timer.remaining_sec or -1), 600)

        current["now"] += timedelta(minutes=10, seconds=1)
        ready_view = engine.view()
        self.assertEqual(ready_view.phase_name, "READY")

    def test_sub_sixteen_percent_path_anchors_bottom_time_at_grace_limit_when_departure_is_late(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] += timedelta(minutes=6)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        view = engine.view()
        self.assertEqual(view.phase_name, "BOTTOM")
        self.assertEqual(int(view.active_timer.elapsed_sec), 200)

    def test_late_leave_twenty_logs_grace_based_bottom_time_anchor(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] += timedelta(minutes=6)
        events = engine.dispatch(EngineAction.LEAVE_STOP)

        self.assertEqual(events[0].payload["bottom_time_anchor"], "grace_5_min")

    def test_ninety_stop_waits_for_explicit_fifty_fifty_confirmation_while_stop_timer_runs_from_arrival(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="16.0", bottom_mix_o2_percent=16.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=1)

        view = engine.view()
        self.assertEqual(view.phase_name, "AT_STOP")
        self.assertEqual(view.obligation.name, "CONFIRM_50_50")
        self.assertEqual(view.gas_state_name, "WAITING_ON_50_50")
        self.assertEqual(int(view.active_timer.elapsed_sec), 60)

        engine.dispatch(EngineAction.CONFIRM_50_50)
        self.assertEqual(engine.view().gas_state_name, "HELIOX_50_50")

    def test_thirty_stop_clock_begins_on_confirm_on_o2_not_arrival(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="150", depth_fsw=150)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=2)

        waiting = engine.view()
        self.assertEqual(waiting.obligation.name, "CONFIRM_ON_O2")
        self.assertIsNotNone(waiting.active_timer)
        assert waiting.active_timer is not None
        self.assertEqual(waiting.active_timer.role.name, "STOP")
        self.assertEqual(int(waiting.active_timer.elapsed_sec), 120)

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=1)
        on_o2 = engine.view()
        self.assertEqual(int(on_o2.active_timer.elapsed_sec), 60)

    def test_crossing_ninety_without_a_ninety_stop_defers_confirmation_to_next_stop(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="180", depth_fsw=180)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        self.assertEqual(engine.state.shift_state, MixedGasShiftState.AWAITING_50_50_CONFIRM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)

        view = engine.view()
        self.assertEqual(view.current_stop_depth_fsw, 70)
        self.assertEqual(view.obligation.name, "CONFIRM_50_50")

    def test_confirmed_fifty_fifty_persists_until_later_gas_change(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="180", depth_fsw=180)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        current["now"] += timedelta(seconds=30)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=1)

        traveling = engine.view()
        self.assertEqual(traveling.phase_name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(traveling.gas_state_name, "HELIOX_50_50")

    def test_toggle_off_o2_transitions_to_interrupted_and_back_on_o2_stop(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.state = replace(
            engine.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=220,
            breathing_gas=MixedGasBreathingGas.OXYGEN,
            shift_state=MixedGasShiftState.NONE,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=30,
                table_depth_fsw=220,
                table_bottom_time_min=30,
                stops=(
                    MixedGasStop(index=1, depth_fsw=30, gas="o2", duration_min=40),
                    MixedGasStop(index=2, depth_fsw=20, gas="o2", duration_min=30),
                ),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=current["now"] - timedelta(minutes=10))),
            oxygen=MixedGasOxygenState(continuous_anchor_at=current["now"] - timedelta(minutes=10)),
        )

        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        interrupted = engine.view()
        self.assertEqual(interrupted.gas_state_name, "INTERRUPTED_O2")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        resumed = engine.view()
        self.assertEqual(resumed.gas_state_name, "ON_O2")

    def test_air_break_due_warning_and_resume_after_five_minute_break(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.state = replace(
            engine.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=220,
            breathing_gas=MixedGasBreathingGas.OXYGEN,
            shift_state=MixedGasShiftState.NONE,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=30,
                table_depth_fsw=220,
                table_bottom_time_min=30,
                stops=(
                    MixedGasStop(index=1, depth_fsw=30, gas="o2", duration_min=40),
                    MixedGasStop(index=2, depth_fsw=20, gas="o2", duration_min=30),
                ),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=current["now"] - timedelta(minutes=30))),
            oxygen=MixedGasOxygenState(continuous_anchor_at=current["now"] - timedelta(minutes=30)),
        )

        due = engine.view()
        self.assertIn("AIR_BREAK_DUE", [warning.name for warning in due.warnings])

        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        break_view = engine.view()
        self.assertEqual(break_view.gas_state_name, "AIR_BREAK")
        self.assertEqual(break_view.active_timer.role.name, "AIR_BREAK")

        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        resumed = engine.view()
        self.assertEqual(resumed.gas_state_name, "ON_O2")


if __name__ == "__main__":
    unittest.main()
