from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import unittest

from dive_stopwatch.engine_v2 import EngineCoordinator, EngineMode, MixedGasEngine, ObligationKind
from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.engine_v2.contracts.surd_handoff import SurdEntryKind
from dive_stopwatch.engine_v2.contracts.timers import TimerState
from dive_stopwatch.engine_v2.modes.mixed_gas.state import (
    MixedGasBreathingGas,
    MixedGasPhase,
    MixedGasPlan,
    MixedGasStop,
    MixedGasTimer,
    MixedGasTimerKind,
)


def _mixed_gas_coordinator(*, now_provider):
    return EngineCoordinator(
        diving_mode=DivingMode.MIXED_GAS,
        deco_profile=DecoProfile.MIXED_GAS,
        now_provider=now_provider,
    )


class EngineV2MixedGasArchitectureTests(unittest.TestCase):
    def test_mixed_gas_ready_requires_depth_before_launch_action_appears(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))

        view = coordinator.view()
        self.assertEqual(view.mode, EngineMode.MIXED_GAS)
        self.assertEqual(view.phase_name, "READY")
        self.assertEqual(view.pending_action_text, "Input Max Depth")
        self.assertEqual(view.available_actions, ("RESET",))

    def test_mixed_gas_ready_projects_bottom_mix_input_and_obligation(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        view = coordinator.view()
        self.assertEqual(view.gas_mix_label, "Bottom Mix: 18.4% O2")
        self.assertEqual(view.pending_action_text, "Leave Surface")
        self.assertEqual(view.obligation, ObligationKind.LEAVE_SURFACE)
        self.assertEqual(view.available_actions, ("LEAVE_SURFACE", "RESET"))
        self.assertEqual(view.profile_preview_label, "Max Depth ≤ 200 fsw | Supported Mix: 14-23.4% O2")

    def test_mixed_gas_ready_flags_sub_16_percent_descent_path_without_start_action(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="220", depth_fsw=220)
        coordinator.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        view = coordinator.view()
        self.assertEqual(view.gas_mix_label, "Bottom Mix: 14% O2 | Air to 20 fsw required")
        self.assertEqual(view.pending_action_text, "Leave Surface")
        self.assertEqual(view.available_actions, ("LEAVE_SURFACE", "RESET"))
        self.assertEqual(view.profile_preview_label, "Air to 20 fsw required | Max Depth ≤ 270 fsw | Supported Mix: 10-17% O2")

    def test_mixed_gas_ready_snaps_depth_to_next_supported_table_depth_for_validation(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="199", depth_fsw=199)
        coordinator.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        view = coordinator.view()
        self.assertEqual(view.pending_action_text, "Leave Surface")
        self.assertEqual(view.available_actions, ("LEAVE_SURFACE", "RESET"))
        self.assertEqual(view.profile_preview_label, "Air to 20 fsw required | Max Depth ≤ 270 fsw | Supported Mix: 14-18.4% O2")

    def test_mixed_gas_ready_blocks_unsupported_bottom_mix_for_depth(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_depth(raw_text="150", depth_fsw=150)
        coordinator.set_bottom_mix(raw_text="30.0", bottom_mix_o2_percent=30.0)

        view = coordinator.view()
        self.assertEqual(view.pending_action_text, "Bottom mix not supported for depth")
        self.assertEqual(view.available_actions, ("RESET",))
        self.assertEqual(view.profile_preview_label, "Supported Mix: 14-23.4% O2")

    def test_mixed_gas_ready_shows_max_depth_for_entered_mix_before_depth_input(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_bottom_mix(raw_text="18.4", bottom_mix_o2_percent=18.4)

        view = coordinator.view()
        self.assertEqual(view.pending_action_text, "Input Max Depth")
        self.assertEqual(view.profile_preview_label, "Max Depth ≤ 200 fsw")

    def test_mixed_gas_ready_shows_hypoxic_floor_without_depth(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        view = coordinator.view()
        self.assertEqual(view.pending_action_text, "Input Max Depth")
        self.assertEqual(view.profile_preview_label, "Air to 20 fsw required | Max Depth ≤ 270 fsw")

    def test_mixed_gas_ready_rejects_bottom_mix_below_ten_percent_with_line_six_message(self) -> None:
        coordinator = _mixed_gas_coordinator(now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0))
        coordinator.set_bottom_mix(raw_text="9.9", bottom_mix_o2_percent=9.9)

        view = coordinator.view()
        self.assertEqual(view.pending_action_text, "Input Max Depth")
        self.assertEqual(view.profile_preview_label, "Bottom Mix 10-40% required")
        self.assertEqual(view.warnings[0].name, "UNSUPPORTED_BOTTOM_MIX")

    def test_mixed_gas_at_forty_stop_does_not_expose_manual_switch_to_surd(self) -> None:
        now = datetime(2026, 4, 29, 12, 0, 0)
        coordinator = _mixed_gas_coordinator(now_provider=lambda: now)
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=20,
                table_depth_fsw=220,
                table_bottom_time_min=20,
                stops=(MixedGasStop(index=1, depth_fsw=40, gas="50_50", duration_min=7),),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        )

        self.assertNotIn("SWITCH_TO_SURD", coordinator.view().available_actions)

    def test_preselected_mixed_gas_surd_at_forty_stop_does_not_expose_switch_to_surd(self) -> None:
        now = datetime(2026, 5, 2, 18, 2, 38)
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.MIXED_GAS,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: now,
        )
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=210,
            bottom_mix_o2_percent=14.0,
            breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
            plan=MixedGasPlan(
                input_depth_fsw=210,
                input_bottom_time_min=10,
                table_depth_fsw=210,
                table_bottom_time_min=10,
                stops=(
                    MixedGasStop(index=1, depth_fsw=80, gas="50_50", duration_min=7),
                    MixedGasStop(index=2, depth_fsw=50, gas="50_50", duration_min=9),
                    MixedGasStop(index=3, depth_fsw=40, gas="50_50", duration_min=9),
                    MixedGasStop(index=4, depth_fsw=30, gas="o2", duration_min=12),
                ),
            ),
            current_stop_index=3,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        )

        self.assertNotIn("SWITCH_TO_SURD", coordinator.view().available_actions)

    def test_mixed_gas_surd_builder_creates_normal_handoff_from_forty(self) -> None:
        now = datetime(2026, 4, 29, 12, 0, 0)
        engine = MixedGasEngine(now_provider=lambda: now)
        engine.state = replace(
            engine.state,
            phase=MixedGasPhase.AT_STOP,
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=20,
                table_depth_fsw=220,
                table_bottom_time_min=20,
                stops=(MixedGasStop(index=1, depth_fsw=40, gas="50_50", duration_min=7),),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        )

        self.assertTrue(engine.can_start_normal_surd_handoff())
        handoff = engine.build_normal_surd_handoff()
        self.assertEqual(handoff.entry_kind, SurdEntryKind.L40_NORMAL)
        self.assertEqual(handoff.left_water_stop_depth_fsw, 40)
        self.assertEqual(handoff.remaining_in_water_obligation_sec, 0.0)


if __name__ == "__main__":
    unittest.main()
