from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import EngineAction
from dive_stopwatch.engine_v2.contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from dive_stopwatch.engine_v2.modes.surd.engine import SurdEngine
from dive_stopwatch.engine_v2.modes.surd.plan import SurdPenaltyKind, build_surd_chamber_plan


class EngineV2SurdSemanticsTests(unittest.TestCase):
    def test_normal_l40_handoff_progresses_through_surface_interval_into_chamber(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.view().phase_name, "SURFACE_UNDRESS")

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        self.assertEqual(engine.view().phase_name, "SURFACE_TO_CHAMBER_50")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_AT_50_WAITING_O2")
        self.assertEqual(view.obligation.name, "CONFIRM_ON_O2")
        self.assertEqual(view.current_stop_depth_fsw, 50)

    def test_adapter_30_20_entry_starts_at_surface_to_chamber(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        engine = SurdEngine(now_provider=lambda: now)
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.ADAPTER_30_20, now=now, left_water_stop_depth_fsw=30))

        view = engine.view()
        self.assertEqual(view.phase_name, "SURFACE_TO_CHAMBER_50")
        self.assertEqual(view.obligation.name, "REACH_CHAMBER_50")

    def test_chamber_waiting_on_o2_on_o2_move_break_and_completion(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_ON_O2")
        self.assertEqual(view.current_stop_depth_fsw, 50)

        current["now"] += timedelta(minutes=15)
        self.assertIn("MOVE_CHAMBER", engine.view().available_actions)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_STOP")
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)

        current["now"] += timedelta(minutes=15)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)
        engine.dispatch(EngineAction.START_AIR_BREAK)
        self.assertEqual(engine.view().phase_name, "CHAMBER_AIR_BREAK")

        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        self.assertEqual(engine.view().phase_name, "CHAMBER_ON_O2")
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)

    def test_off_o2_pauses_chamber_segment(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        current["now"] += timedelta(minutes=4)
        before = engine.view().current_stop_remaining_sec
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] += timedelta(minutes=3)
        during = engine.view().current_stop_remaining_sec
        self.assertEqual(before, during)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual(engine.view().phase_name, "CHAMBER_ON_O2")

    def test_surface_interval_penalty_adds_extra_15_minutes_at_50(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=4)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_AT_50_WAITING_O2")
        self.assertIn("SURFACE_INTERVAL_PENALTY", [warning.name for warning in view.warnings])
        self.assertEqual(view.current_stop_depth_fsw, 50)
        self.assertEqual(view.current_stop_remaining_sec, None)

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=30)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)

    def test_penalized_fifty_air_break_ends_ready_to_move_not_auto_ascending_or_second_fifty_period(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 52, 36)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="AIR",
                input_depth_fsw=120,
                input_bottom_time_min=100,
                source_table_depth_fsw=120,
                source_table_bottom_time_min=100,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=4, seconds=3)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=64)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        current["now"] += timedelta(minutes=30)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)
        engine.dispatch(EngineAction.START_AIR_BREAK)

        current["now"] += timedelta(minutes=5)
        events = engine.dispatch(EngineAction.END_AIR_BREAK)

        self.assertEqual(engine.view().phase_name, "CHAMBER_READY_TO_MOVE")
        self.assertIsNone(engine.state.chamber_travel_timer)
        self.assertEqual(engine.state.current_segment_index, 0)
        self.assertEqual([event.kind.name for event in events], ["REACHED_STOP"])
        self.assertEqual(events[0].payload["confirmation"], "resume_after_break")

        move_events = engine.dispatch(EngineAction.MOVE_CHAMBER)
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_STOP")
        self.assertEqual(engine.state.chamber_travel_from_depth_fsw, 50)
        self.assertEqual(engine.state.current_segment_index, 1)
        self.assertEqual([event.kind.name for event in move_events], ["LEFT_STOP"])
        self.assertEqual(move_events[0].payload["depth_fsw"], 50)
        self.assertEqual(move_events[0].payload["next_depth_fsw"], 40)

        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)

    def test_penalized_fifty_air_break_allows_explicit_move_to_forty_during_break(self) -> None:
        current = {"now": datetime(2026, 5, 3, 19, 30, 24)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=200,
                input_bottom_time_min=10,
                source_table_depth_fsw=200,
                source_table_bottom_time_min=10,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(seconds=64)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=4, seconds=5)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=65)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] += timedelta(seconds=1)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=30, seconds=4)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        break_view = engine.view()
        self.assertEqual(break_view.phase_name, "CHAMBER_AIR_BREAK")
        self.assertIn("MOVE_CHAMBER", break_view.available_actions)
        self.assertNotIn("END_AIR_BREAK", break_view.available_actions)

        current["now"] += timedelta(seconds=5)
        move_events = engine.dispatch(EngineAction.MOVE_CHAMBER)
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_STOP")
        self.assertEqual(engine.view().gas_state_name, "AIR_BREAK")
        self.assertEqual([event.kind.name for event in move_events], ["LEFT_STOP"])
        self.assertEqual(move_events[0].payload["depth_fsw"], 50)
        self.assertEqual(move_events[0].payload["next_depth_fsw"], 40)

        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        arrived_view = engine.view()
        self.assertEqual(arrived_view.phase_name, "CHAMBER_AIR_BREAK")
        self.assertEqual(arrived_view.current_stop_depth_fsw, 40)
        self.assertNotIn("END_AIR_BREAK", arrived_view.available_actions)

        current["now"] += timedelta(minutes=4, seconds=35)
        ready_to_end_view = engine.view()
        self.assertIn("END_AIR_BREAK", ready_to_end_view.available_actions)

    def test_surface_interval_penalty_single_period_path_previews_air_break_before_forty(self) -> None:
        current = {"now": datetime(2026, 5, 3, 1, 9, 58)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=210,
                input_bottom_time_min=4,
                source_table_depth_fsw=210,
                source_table_bottom_time_min=10,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=datetime(2026, 5, 3, 1, 9, 58),
            )
        )

        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=4, seconds=8)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_ON_O2")
        self.assertEqual(view.current_stop_depth_fsw, 50)
        self.assertEqual(view.pending_action_text, "Air Break for 5 min")
        self.assertNotIn("MOVE_CHAMBER", view.available_actions)

    def test_surface_interval_penalty_multi_period_path_requires_air_break_before_move_to_forty(self) -> None:
        current = {"now": datetime(2026, 5, 2, 18, 11, 47)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=210,
                input_bottom_time_min=20,
                source_table_depth_fsw=210,
                source_table_bottom_time_min=20,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 2, 18, 17, 0)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=30)

        view = engine.view()
        self.assertEqual(view.pending_action_text, "Air Break for 5 min")
        self.assertEqual(view.current_stop_depth_fsw, 50)
        self.assertIn("START_AIR_BREAK", view.available_actions)
        self.assertNotIn("MOVE_CHAMBER", view.available_actions)

    def test_completed_final_forty_stop_keeps_surface_available_even_when_off_o2(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 0, 25)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=200,
                input_bottom_time_min=10,
                source_table_depth_fsw=200,
                source_table_bottom_time_min=10,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] = datetime(2026, 5, 3, 20, 1, 27)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 5, 32)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 6, 37)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] = datetime(2026, 5, 3, 20, 6, 44)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] = datetime(2026, 5, 3, 20, 36, 58)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] = datetime(2026, 5, 3, 20, 42, 3)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        current["now"] = datetime(2026, 5, 3, 20, 42, 8)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] = datetime(2026, 5, 3, 20, 43, 15)
        engine.dispatch(EngineAction.REACH_STOP)

        current["now"] = datetime(2026, 5, 3, 20, 57, 24)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_OFF_O2")
        self.assertEqual(view.current_stop_depth_fsw, 40)
        self.assertIn("COMPLETE_TO_SURFACE", view.available_actions)
        self.assertNotIn("MOVE_CHAMBER", view.available_actions)

        current["now"] = datetime(2026, 5, 3, 20, 57, 25)
        events = engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_SURFACE")
        self.assertEqual([event.kind.name for event in events], ["LEFT_STOP"])

        current["now"] = datetime(2026, 5, 3, 20, 58, 45)
        self.assertEqual(engine.view().display_depth_fsw, 0)

        current["now"] = datetime(2026, 5, 3, 20, 58, 46)
        events = engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.view().phase_name, "COMPLETE_CLEAN_TIME")
        self.assertEqual([event.kind.name for event in events], ["REACHED_SURFACE"])

    def test_reach_chamber_50_uses_table_schedule_values_when_handoff_input_time_is_lower(self) -> None:
        current = {"now": datetime(2026, 5, 2, 18, 11, 47)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=210,
                input_bottom_time_min=4,
                source_table_depth_fsw=210,
                source_table_bottom_time_min=10,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=40)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        view = engine.view()
        self.assertEqual(view.phase_name, "CHAMBER_AT_50_WAITING_O2")
        self.assertEqual(view.current_stop_depth_fsw, 50)
        self.assertEqual(view.obligation.name, "CONFIRM_ON_O2")

    def test_mixed_gas_single_surface_period_yields_fifty_then_forty_segments(self) -> None:
        current = {"now": datetime(2026, 5, 2, 18, 11, 47)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="MIXED_GAS",
                input_depth_fsw=210,
                input_bottom_time_min=4,
                source_table_depth_fsw=210,
                source_table_bottom_time_min=10,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=40)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        self.assertEqual(engine.view().current_stop_depth_fsw, 50)
        self.assertEqual(engine.view().next_stop_depth_fsw, 40)
        self.assertEqual(engine.view().next_stop_duration_min, 15)

    def test_surface_interval_exceeded_blocks_normal_chamber_progression(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=6, seconds=1)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        view = engine.view()
        self.assertEqual(view.phase_name, "SURFACE_INTERVAL_EXCEEDED")
        self.assertIn("SURFACE_INTERVAL_EXCEEDED", [warning.name for warning in view.warnings])
        self.assertEqual(view.available_actions, ("RESET",))

    def test_surface_interval_exceeded_can_build_chamber_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=6, seconds=1)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        self.assertTrue(engine.can_handoff_to_chamber())
        handoff = engine.build_chamber_handoff()
        self.assertEqual(handoff.trigger, "SURFACE_INTERVAL_EXCEEDED")
        self.assertEqual(handoff.source_entry_kind, SurdEntryKind.L40_NORMAL)
        self.assertEqual(handoff.input_depth_fsw, 120)
        self.assertEqual(handoff.input_bottom_time_min, 90)
        self.assertEqual(handoff.surface_interval_elapsed_sec, 8 * 60 + 1)
        self.assertEqual(handoff.entry_depth_fsw, 50)
        self.assertEqual(handoff.handed_off_at, current["now"])

    def test_exceeded_surface_interval_chamber_treatment_begins_with_75_fpm_descent_to_60(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        surd = SurdEngine(now_provider=lambda: current["now"])
        surd.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        surd.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        surd.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=6, seconds=1)
        surd.dispatch(EngineAction.REACH_CHAMBER_50)

        handoff = surd.build_chamber_handoff()

        from dive_stopwatch.engine_v2.modes.chamber.engine import ChamberEngine

        chamber = ChamberEngine(now_provider=lambda: current["now"])
        chamber.start_treatment(handoff)
        self.assertEqual(chamber.view().phase_name, "DESCENT_TO_60")

        current["now"] += timedelta(seconds=24)
        self.assertEqual(chamber.view().display_depth_fsw, 60)

    def test_view_is_pure_during_clean_time_and_tick_advances_completion(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.START_AIR_BREAK)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.START_AIR_BREAK)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        current["now"] += timedelta(minutes=15)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.START_AIR_BREAK)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)

        self.assertEqual(engine.state.phase.name, "CHAMBER_TRAVEL_TO_SURFACE")
        current["now"] += timedelta(seconds=81)
        engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.state.phase.name, "COMPLETE_CLEAN_TIME")
        view_before = engine.view()
        self.assertEqual(view_before.phase_name, "COMPLETE_CLEAN_TIME")
        self.assertEqual(engine.state.phase.name, "COMPLETE_CLEAN_TIME")

        current["now"] += timedelta(minutes=10, seconds=1)
        view_still_pure = engine.view()
        self.assertEqual(view_still_pure.phase_name, "READY")
        self.assertEqual(engine.state.phase.name, "READY")

        engine.tick()
        self.assertEqual(engine.state.phase.name, "READY")

    def test_build_surd_chamber_plan_has_expected_segment_shape_for_known_profile(self) -> None:
        plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.NONE,
        )

        self.assertEqual(len(plan.segments), 5)
        self.assertEqual(
            [(segment.period_number, segment.depth_fsw, segment.duration_sec // 60) for segment in plan.segments],
            [
                (1, 50, 15),
                (1, 40, 15),
                (2, 40, 30),
                (3, 40, 30),
                (4, 40, 15),
            ],
        )

    def test_surface_interval_penalty_extends_only_first_50_segment_by_15_minutes(self) -> None:
        base_plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.NONE,
        )
        penalty_plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.PLUS_15_AT_50,
        )

        self.assertEqual(len(base_plan.segments), len(penalty_plan.segments))
        self.assertEqual(penalty_plan.segments[0].depth_fsw, 50)
        self.assertEqual(penalty_plan.segments[0].duration_sec, base_plan.segments[0].duration_sec + (15 * 60))

    def test_normal_under_five_min_si_chamber_timing_matches_50_then_40_sequence(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(self._handoff(entry_kind=SurdEntryKind.L40_NORMAL, now=current["now"], left_water_stop_depth_fsw=40))

        current["now"] += timedelta(seconds=40)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(seconds=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=40)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        waiting = engine.view()
        self.assertEqual(waiting.phase_name, "CHAMBER_AT_50_WAITING_O2")
        self.assertIsNotNone(waiting.active_timer)
        assert waiting.active_timer is not None
        self.assertEqual(int(waiting.active_timer.elapsed_sec), 81)

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_STOP")
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)

        at_forty = engine.view()
        self.assertEqual(at_forty.current_stop_depth_fsw, 40)
        self.assertIsNotNone(at_forty.current_stop_remaining_sec)
        assert at_forty.current_stop_remaining_sec is not None
        self.assertEqual(int(at_forty.current_stop_remaining_sec), 14 * 60 + 40)

    def test_build_surd_chamber_plan_rejects_exceeded_penalty(self) -> None:
        with self.assertRaises(AssertionError):
            build_surd_chamber_plan(
                input_depth_fsw=120,
                input_bottom_time_min=90,
                penalty_kind=SurdPenaltyKind.EXCEEDED,
            )

    def _handoff(self, *, entry_kind: SurdEntryKind, now: datetime, left_water_stop_depth_fsw: int) -> InWaterToSurdHandoff:
        return InWaterToSurdHandoff(
            entry_kind=entry_kind,
            source_mode="SURD" if entry_kind is SurdEntryKind.L40_NORMAL else "AIR/O2",
            input_depth_fsw=120,
            input_bottom_time_min=90,
            source_table_depth_fsw=120,
            source_table_bottom_time_min=90,
            left_water_stop_depth_fsw=left_water_stop_depth_fsw,
            remaining_in_water_obligation_sec=0.0 if entry_kind is SurdEntryKind.L40_NORMAL else 10 * 60.0,
            handed_off_at=now,
        )


if __name__ == "__main__":
    unittest.main()
