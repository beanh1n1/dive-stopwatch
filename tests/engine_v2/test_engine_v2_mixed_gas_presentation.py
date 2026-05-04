from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import EngineCoordinator, EngineMode
from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.engine_v2.contracts.timers import TimerState
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
from dive_stopwatch.engine_v2.projection.presentation_builder import build_presentation_model
from dive_stopwatch.engine_v2.runtime.session import EngineV2Session


def _mixed_gas_coordinator(*, now_provider):
    return EngineCoordinator(
        diving_mode=DivingMode.MIXED_GAS,
        deco_profile=DecoProfile.MIXED_GAS,
        now_provider=now_provider,
    )


def _mixed_gas_session(*, now_provider):
    return EngineV2Session(
        now_provider=now_provider,
        diving_mode=DivingMode.MIXED_GAS,
        deco_profile=DecoProfile.MIXED_GAS,
    )


class EngineV2MixedGasPresentationTests(unittest.TestCase):
    def test_mixed_gas_ready_presentation_surfaces_selected_bottom_mix(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.mode_name, "MIXED_GAS")
        self.assertEqual(presentation_model.status_value_text, "Ready")
        self.assertEqual(presentation_model.summary_text, "Next: Leave Surface")
        self.assertEqual(presentation_model.detail_text, "Max Depth ≤ 200 fsw | Supported Mix: 14-23.4% O2")
        assert presentation_model.primary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "LEAVE_SURFACE")

    def test_mixed_gas_session_records_bottom_mix_input(self) -> None:
        session = _mixed_gas_session(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))

        session.set_depth_text("150")
        session.set_bottom_mix_text("18.4")

        self.assertEqual(session.raw_audit_events()[1].payload["field"], "depth_fsw")
        self.assertEqual(session.raw_audit_events()[2].payload["field"], "bottom_mix_o2_percent")
        self.assertEqual(session.raw_audit_events()[2].payload["value"], 18.4)
        self.assertEqual(session.presentation_model().detail_text, "Max Depth ≤ 200 fsw | Supported Mix: 14-23.4% O2")

    def test_mixed_gas_ready_presentation_marks_unsupported_bottom_mix_in_red_summary_state(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="30.0", bottom_mix_o2_percent=30.0)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Warning")
        self.assertEqual(presentation_model.summary_text, "Next: Bottom mix not supported for depth")
        self.assertEqual(presentation_model.summary_kind, "error")

    def test_mixed_gas_ready_presentation_shows_low_o2_requirement_on_line_six_for_depths_to_two_hundred(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="13.9", bottom_mix_o2_percent=13.9)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.detail_text, "Bottom Mix ≥ 14% required")

    def test_mixed_gas_ready_presentation_shows_low_o2_requirement_on_line_six_for_depths_over_two_hundred(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="220", depth_fsw=220)
        coordinator.set_bottom_mix(raw_text="9.9", bottom_mix_o2_percent=9.9)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.detail_text, "Bottom Mix 10-40% required")

    def test_mixed_gas_ready_presentation_rejects_bottom_mix_above_forty_percent(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="40.1", bottom_mix_o2_percent=40.1)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Warning")
        self.assertEqual(presentation_model.summary_text, "Next: Bottom mix not supported for depth")
        self.assertEqual(presentation_model.detail_text, "Bottom Mix 10-40% required")

    def test_mixed_gas_ready_presentation_rejects_depth_above_three_eighty(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="381", depth_fsw=381)
        coordinator.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Warning")
        self.assertEqual(presentation_model.summary_text, "Next: Depth not supported")
        self.assertEqual(presentation_model.detail_text, "Max Depth ≤ 380 fsw")

    def test_mixed_gas_leave_surface_to_sub_sixteen_path_points_next_to_twenty_fsw(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Descent")
        self.assertEqual(presentation_model.summary_text, "Next: 20 fsw")
        self.assertEqual(presentation_model.detail_text, "")

    def test_mixed_gas_sub_sixteen_descent_shows_grace_countdown_immediately_after_leave_surface(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=10)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Descent")
        self.assertEqual(presentation_model.summary_text, "Next: 20 fsw")
        self.assertEqual(presentation_model.depth_timer_label, "4:50")
        self.assertEqual(presentation_model.detail_text, "")

    def test_mixed_gas_leave_surface_normal_path_does_not_point_next_to_twenty_fsw(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("150")
        session.set_bottom_mix_text("18.4")

        session.dispatch("LEAVE_SURFACE")

        presentation_model = session.presentation_model()
        self.assertNotEqual(presentation_model.summary_text, "Next: 20 fsw")

    def test_mixed_gas_active_hold_label_moves_to_depth_line(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("150")
        session.set_bottom_mix_text("18.4")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=30)
        session.dispatch("START_HOLD")
        current["now"] += timedelta(seconds=45)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.depth_timer_label, "H1   00:45")
        self.assertEqual(presentation_model.detail_text, "")

    def test_mixed_gas_r20_primary_and_secondary_actions_match_expected_order(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=20)
        session.dispatch("REACH_STOP")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "At Stop")
        self.assertEqual(presentation_model.summary_text, "Next: Confirm bottom-mix")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "On Bottom-mix")

    def test_mixed_gas_confirmed_bottom_mix_at_twenty_shows_descent_and_no_surface_next(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=20)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_BOTTOM_MIX")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "At Stop")
        self.assertEqual(presentation_model.summary_text, "Next: Leave Stop")
        self.assertEqual(presentation_model.detail_text, "")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "Shift to Air")

    def test_mixed_gas_shift_to_air_at_twenty_swaps_controls_to_abort_ascent_flow(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=20)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_BOTTOM_MIX")
        session.dispatch("CONVERT_TO_AIR")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "At Stop")
        self.assertEqual(presentation_model.summary_text, "Next: Leave Bottom")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Bottom")
        self.assertEqual(presentation_model.secondary_action.label, "On Bottom-mix")

    def test_mixed_gas_leave_twenty_shows_descent_and_next_placeholder(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=20)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_BOTTOM_MIX")
        current["now"] += timedelta(seconds=24)
        session.dispatch("LEAVE_STOP")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Descent")
        self.assertEqual(presentation_model.summary_text, "Next: --")
        self.assertEqual(presentation_model.detail_text, "")

    def test_mixed_gas_abort_leave_bottom_from_twenty_begins_surface_ascent_from_twenty(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(seconds=20)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_BOTTOM_MIX")
        session.dispatch("CONVERT_TO_AIR")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(seconds=20)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Traveling")
        self.assertEqual(presentation_model.depth_inline_text, "10 fsw")

    def test_mixed_gas_reach_bottom_uses_bottom_status_and_air_like_next_summary(self) -> None:
        current = {"now": datetime(2026, 4, 29, 19, 39, 55)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=2, seconds=8)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(seconds=8)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=3, seconds=11)
        session.dispatch("REACH_BOTTOM")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Bottom")
        self.assertEqual(presentation_model.summary_text, "Next: 80 fsw for 7 min")
        self.assertNotEqual(presentation_model.detail_text, "Next action: Leave Bottom")

    def test_mixed_gas_bottom_preview_uses_ten_minute_profile_when_bottom_time_is_under_ten_minutes(self) -> None:
        current = {"now": datetime(2026, 4, 29, 19, 39, 55)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=1, seconds=2)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(seconds=4)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=5)
        session.dispatch("REACH_BOTTOM")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Bottom")
        self.assertEqual(presentation_model.summary_text, "Next: 80 fsw for 7 min")

    def test_mixed_gas_live_depth_counts_down_after_leave_bottom(self) -> None:
        current = {"now": datetime(2026, 4, 29, 19, 39, 55)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=1, seconds=2)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(seconds=4)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=10)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(seconds=60)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Traveling")
        self.assertEqual(presentation_model.depth_inline_text, "190 fsw")

    def test_mixed_gas_bottom_preview_snaps_up_to_next_reviewed_row_for_thirteen_thirty_bottom_time(self) -> None:
        current = {"now": datetime(2026, 4, 29, 20, 9, 29)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=1, seconds=2)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(seconds=4)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=13, seconds=30)
        session.dispatch("REACH_BOTTOM")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Bottom")
        self.assertEqual(presentation_model.summary_text, "Next: 90 fsw for 7 min")

    def test_mixed_gas_deferred_fifty_fifty_confirm_is_primary_at_first_stop_below_ninety(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("180")
        session.set_bottom_mix_text("18.4")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=10)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(minutes=3)
        session.dispatch("REACH_STOP")

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.summary_text, "Next: Confirm 50/50")
        assert presentation_model.primary_action is not None
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "Confirm 50/50")

    def test_mixed_gas_leave_stop_from_fifty_fifty_wait_state_begins_ascent_to_next_stop(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("180")
        session.set_bottom_mix_text("18.4")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=10)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(minutes=3)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(seconds=30)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(seconds=60)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Traveling")
        self.assertEqual(presentation_model.summary_text, "Next: 50 fsw for 10 min")
        self.assertEqual(presentation_model.depth_inline_text, "50 fsw")

    def test_mixed_gas_leave_stop_after_prior_delay_does_not_freeze_depth_at_old_stop(self) -> None:
        current = {"now": datetime(2026, 4, 29, 11, 55, 50)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("210")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] = datetime(2026, 4, 29, 11, 56, 57)
        session.dispatch("REACH_STOP")
        current["now"] = datetime(2026, 4, 29, 11, 56, 58)
        session.dispatch("CONFIRM_BOTTOM_MIX")
        current["now"] = datetime(2026, 4, 29, 11, 57, 3)
        session.dispatch("LEAVE_STOP")
        current["now"] = datetime(2026, 4, 29, 12, 0, 9)
        session.dispatch("REACH_BOTTOM")
        current["now"] = datetime(2026, 4, 29, 12, 0, 11)
        session.dispatch("LEAVE_BOTTOM")
        current["now"] = datetime(2026, 4, 29, 12, 1, 14)
        session.dispatch("START_DELAY")
        current["now"] = datetime(2026, 4, 29, 12, 2, 18)
        session.dispatch("END_DELAY")
        current["now"] = datetime(2026, 4, 29, 12, 5, 33)
        session.dispatch("REACH_STOP")
        current["now"] = datetime(2026, 4, 29, 12, 12, 44)
        session.dispatch("LEAVE_STOP")
        current["now"] = datetime(2026, 4, 29, 12, 12, 45)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "Traveling")
        self.assertEqual(presentation_model.depth_inline_text, "79 fsw")

    def test_mixed_gas_interrupted_o2_shows_next_on_o2(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            breathing_gas=MixedGasBreathingGas.OXYGEN,
            shift_state=MixedGasShiftState.OFF_O2,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=30,
                table_depth_fsw=220,
                table_bottom_time_min=30,
                stops=(MixedGasStop(index=1, depth_fsw=20, gas="o2", duration_min=30),),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=datetime(2026, 4, 29, 11, 45, 0), carried_elapsed_sec=300, running=False)),
            interruption_timer=MixedGasTimer(kind=MixedGasTimerKind.SHIFT, timer=TimerState(started_at=datetime(2026, 4, 29, 12, 0, 0))),
            oxygen=MixedGasOxygenState(continuous_anchor_at=datetime(2026, 4, 29, 11, 30, 0)),
        )

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Off O2")
        self.assertEqual(presentation_model.summary_text, "Next: On O2")
        self.assertEqual(presentation_model.summary_kind, "o2")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "On O2")

    def test_mixed_gas_air_break_shows_five_minute_countdown_and_on_o2_summary_in_green(self) -> None:
        now = datetime(2026, 4, 29, 12, 0, 0)
        coordinator = _mixed_gas_coordinator(now_provider=lambda: now)
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=220,
            breathing_gas=MixedGasBreathingGas.OXYGEN,
            shift_state=MixedGasShiftState.AIR_BREAK,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=30,
                table_depth_fsw=220,
                table_bottom_time_min=30,
                stops=(MixedGasStop(index=1, depth_fsw=20, gas="o2", duration_min=30),),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now, carried_elapsed_sec=1200, running=False)),
            air_break_timer=MixedGasTimer(kind=MixedGasTimerKind.AIR_BREAK, timer=TimerState(started_at=now)),
            oxygen=MixedGasOxygenState(continuous_anchor_at=now),
        )

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Air Break")
        self.assertEqual(presentation_model.depth_timer_label, "05:00 left")
        self.assertEqual(presentation_model.summary_text, "Next: On O2")
        self.assertEqual(presentation_model.summary_kind, "o2")

    def test_mixed_gas_arrival_at_thirty_fsw_tsv_shows_at_stop_with_running_timer(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("150")
        session.set_bottom_mix_text("18.4")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=10)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(minutes=3)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_50_50")
        current["now"] += timedelta(minutes=3)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=2)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(minutes=1)
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=2)
        session.dispatch("REACH_STOP")
        current["now"] += timedelta(minutes=2)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.status_value_text, "At Stop")
        self.assertEqual(presentation_model.summary_text, "Next: On O2")
        self.assertEqual(presentation_model.primary_value, "02:00.0")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "On O2")

    def test_mixed_gas_first_stop_travel_shows_air_style_overtime_counter(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        session = _mixed_gas_session(now_provider=lambda: current["now"])
        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")

        session.dispatch("LEAVE_SURFACE")
        current["now"] += timedelta(minutes=1)
        session.dispatch("REACH_STOP")
        session.dispatch("CONFIRM_BOTTOM_MIX")
        session.dispatch("LEAVE_STOP")
        current["now"] += timedelta(minutes=10)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("LEAVE_BOTTOM")
        current["now"] += timedelta(minutes=5)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.depth_timer_label, "+00:20")


if __name__ == "__main__":
    unittest.main()
