from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import EngineAction, EngineCoordinator, EngineMode, ObligationKind
from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.engine_v2.contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from dive_stopwatch.engine_v2.contracts.timers import TimerState
from dive_stopwatch.engine_v2.modes.mixed_gas.state import MixedGasPhase, MixedGasPlan, MixedGasStop, MixedGasTimer, MixedGasTimerKind


def _coordinator_from_mode(mode: EngineMode, *, now_provider):
    mapping = {
        EngineMode.AIR: (DivingMode.AIR, DecoProfile.AIR),
        EngineMode.AIR_O2: (DivingMode.AIR, DecoProfile.O2),
        EngineMode.MIXED_GAS: (DivingMode.MIXED_GAS, DecoProfile.MIXED_GAS),
        EngineMode.SURD: (DivingMode.AIR, DecoProfile.SURD),
        EngineMode.CHAMBER: (DivingMode.CHAMBER, DecoProfile.AIR),
    }
    diving_mode, deco_profile = mapping[mode]
    return EngineCoordinator(diving_mode=diving_mode, deco_profile=deco_profile, now_provider=now_provider)


class EngineV2ArchitectureTests(unittest.TestCase):
    def test_air_coordinator_no_decompression_flow(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="60", depth_fsw=60)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        self.assertEqual(coordinator.view().phase_name, "DESCENT")
        self.assertEqual(coordinator.view().obligation, ObligationKind.REACH_BOTTOM)

        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        self.assertEqual(coordinator.view().phase_name, "BOTTOM")

        current["now"] += timedelta(minutes=10)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        view = coordinator.view()
        self.assertEqual(view.phase_name, "TRAVEL_TO_SURFACE")
        self.assertEqual(view.obligation, ObligationKind.REACH_SURFACE)
        self.assertIsNone(view.next_stop_depth_fsw)

    def test_air_coordinator_decompression_first_stop_flow(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="78", depth_fsw=78)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=47)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        travel_view = coordinator.view()
        self.assertEqual(travel_view.phase_name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(travel_view.next_stop_depth_fsw, 20)
        self.assertEqual(travel_view.next_stop_duration_min, 17)

        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        stop_view = coordinator.view()
        self.assertEqual(stop_view.phase_name, "AT_STOP")
        self.assertEqual(stop_view.current_stop_depth_fsw, 20)
        self.assertEqual(stop_view.current_stop_remaining_sec, 17 * 60)
        self.assertEqual(stop_view.obligation, ObligationKind.NONE)

    def test_invalid_action_records_structured_audit_event(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="60", depth_fsw=60)

        events = coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        self.assertEqual(coordinator.view().phase_name, "READY")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind.name, "INVALID_ACTION")
        self.assertEqual(events[0].payload["action"], "LEAVE_BOTTOM")

    def test_surd_coordinator_starts_with_separate_mode_shell(self) -> None:
        coordinator = _coordinator_from_mode(EngineMode.SURD, now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0))

        view = coordinator.view()
        self.assertEqual(view.mode, EngineMode.AIR)
        self.assertEqual(coordinator.state().active, "air")

    def test_switch_to_surd_is_rejected_when_manual_path_is_removed(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="145", depth_fsw=145)

        events = coordinator.dispatch(EngineAction.SWITCH_TO_SURD)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind.name, "INVALID_ACTION")
        self.assertEqual(coordinator.state().active, "air")

    def test_surd_mode_leave_stop_at_40_starts_normal_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.SURD, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="120", depth_fsw=120)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=87)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=7)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)  # 40

        events = coordinator.dispatch(EngineAction.LEAVE_STOP)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind.name, "HANDOFF_CREATED")
        self.assertEqual(events[0].payload["entry_kind"], "L40_NORMAL")
        self.assertEqual(coordinator.state().active, "surd")
        self.assertEqual(coordinator.view().mode, EngineMode.SURD)
        self.assertEqual(coordinator.view().phase_name, "SURFACE_ASCENT_FROM_WATER_STOP")

    def test_new_api_surd_surface_interval_exceeded_auto_handoffs_to_chamber(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        coordinator = EngineCoordinator(diving_mode=DivingMode.AIR, deco_profile=DecoProfile.SURD, now_provider=lambda: current["now"])
        coordinator._surd.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="AIR_O2",
                input_depth_fsw=120,
                input_bottom_time_min=90,
                source_table_depth_fsw=120,
                source_table_bottom_time_min=90,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )
        coordinator._active = "surd"

        current["now"] += timedelta(minutes=1)
        coordinator.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=6, seconds=1)
        coordinator.view()

        self.assertEqual(coordinator.state().active, "chamber")
        self.assertEqual(coordinator.state().deco_profile, DecoProfile.TREATMENT)
        self.assertEqual(coordinator.view().mode, EngineMode.CHAMBER)
        self.assertEqual(coordinator.view().phase_name, "DESCENT_TO_60")
        self.assertEqual(coordinator._chamber.state.treatment_handoff.input_depth_fsw, 120)
        self.assertEqual(coordinator._chamber.state.treatment_handoff.entry_depth_fsw, 50)
        current["now"] += timedelta(seconds=24)
        self.assertEqual(coordinator.view().display_depth_fsw, 60)

    def test_air_surd_shallow_surface_path_uses_reach_surface_and_enters_surface_undress(self) -> None:
        current = {"now": datetime(2026, 5, 2, 15, 34, 43)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=5, seconds=8)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        travel_view = coordinator.view()
        self.assertEqual(travel_view.phase_name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(travel_view.obligation, ObligationKind.REACH_SURFACE)
        self.assertIn("REACH_SURFACE", travel_view.available_actions)
        self.assertIsNone(travel_view.next_stop_depth_fsw)

        current["now"] += timedelta(minutes=1)
        events = coordinator.dispatch(EngineAction.REACH_SURFACE)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].kind.name, "REACHED_SURFACE")
        self.assertEqual(events[1].kind.name, "HANDOFF_CREATED")
        self.assertEqual(events[1].payload["entry_kind"], "SURFACE_DIRECT")
        self.assertEqual(coordinator.view().mode, EngineMode.SURD)
        self.assertEqual(coordinator.view().phase_name, "SURFACE_UNDRESS")


if __name__ == "__main__":
    unittest.main()
