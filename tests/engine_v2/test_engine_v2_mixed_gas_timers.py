from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import EngineAction, MixedGasEngine


class EngineV2MixedGasTimerTests(unittest.TestCase):
    def test_grace_window_remaining_counts_down_after_bottom_mix_confirmation(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=30)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] += timedelta(minutes=2)

        view = engine.view()
        self.assertEqual(view.current_stop_depth_fsw, 20)
        self.assertEqual(int(view.current_stop_remaining_sec), 150)

    def test_subsequent_stop_timer_includes_travel_time_from_prior_leave_stop(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="150", depth_fsw=150)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)

        view = engine.view()
        self.assertEqual(int(view.active_timer.elapsed_sec), 120)

    def test_mixed_gas_descent_hold_freezes_depth_until_released(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="150", depth_fsw=150)
        engine.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=30)
        before_hold = engine.view()
        engine.dispatch(EngineAction.START_HOLD)
        current["now"] += timedelta(seconds=45)
        during_hold = engine.view()

        self.assertEqual(during_hold.display_depth_fsw, before_hold.display_depth_fsw)
        self.assertEqual(during_hold.active_hold_label, "H1   00:45")

        engine.dispatch(EngineAction.END_HOLD)
        current["now"] += timedelta(seconds=15)
        after_hold = engine.view()
        self.assertGreater((after_hold.display_depth_fsw or 0), (during_hold.display_depth_fsw or 0))

    def test_mixed_gas_travel_timer_after_delay_includes_elapsed_since_leave_bottom(self) -> None:
        current = {"now": datetime(2026, 4, 29, 11, 38, 45)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 4, 29, 11, 39, 54)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] = datetime(2026, 4, 29, 11, 39, 55)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        current["now"] = datetime(2026, 4, 29, 11, 39, 57)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] = datetime(2026, 4, 29, 11, 43, 59)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 4, 29, 11, 44, 5)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] = datetime(2026, 4, 29, 11, 45, 10)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] = datetime(2026, 4, 29, 11, 45, 18)
        engine.dispatch(EngineAction.END_DELAY)
        current["now"] = datetime(2026, 4, 29, 11, 46, 27)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] = datetime(2026, 4, 29, 11, 51, 30)
        engine.dispatch(EngineAction.END_DELAY)

        view = engine.view()
        self.assertEqual(int(view.active_timer.elapsed_sec), 445)

    def test_first_stop_travel_overtime_mirrors_air_style_counter(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.set_depth(raw_text="220", depth_fsw=220)
        engine.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=5)

        view = engine.view()
        self.assertEqual(view.phase_name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(int(view.travel_overtime_sec or -1), 20)


if __name__ == "__main__":
    unittest.main()
