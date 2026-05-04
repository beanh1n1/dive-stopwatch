from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import ChamberEngine, EngineAction, EngineCoordinator, EngineMode, SurdEngine
from dive_stopwatch.engine_v2.contracts.events import AuditEvent, AuditEventKind
from dive_stopwatch.engine_v2.contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.engine_v2.contracts.timers import TimerState
from dive_stopwatch.engine_v2.modes.surd.plan import SurdPenaltyKind, build_surd_chamber_plan
from dive_stopwatch.engine_v2.modes.mixed_gas.state import (
    MixedGasBreathingGas,
    MixedGasPhase,
    MixedGasPlan,
    MixedGasStop,
    MixedGasTimer,
    MixedGasTimerKind,
)
from dive_stopwatch.engine_v2.projection.presentation_builder import build_presentation_model
from dive_stopwatch.engine_v2.projection.dive_log import build_dive_log


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


class EngineV2PresentationBuilderTests(unittest.TestCase):
    def test_air_presentation_model_prioritizes_primary_and_secondary_actions(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="78", depth_fsw=78)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=47)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=17)

        presentation_model = build_presentation_model(coordinator.view())
        assert presentation_model.primary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "LEAVE_STOP")
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertIsNone(presentation_model.secondary_action)
        self.assertEqual(tuple(action.action_name for action in presentation_model.utility_actions), ("RESET",))

    def test_air_ready_preview_matches_legacy_no_decompression_summary(self) -> None:
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0))
        coordinator.set_depth(raw_text="145", depth_fsw=145)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_text, "Next: --")
        self.assertEqual(presentation_model.detail_text, "No-D Limit: 150 / 8 E")

    def test_air_ready_depth_above_three_hundred_blocks_launch(self) -> None:
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0))
        coordinator.set_depth(raw_text="301", depth_fsw=301)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.status_value_text, "Warning")
        self.assertEqual(presentation_model.summary_text, "Next: Depth not supported")
        self.assertEqual(presentation_model.detail_text, "Max Depth ≤ 300 fsw")
        self.assertIsNone(presentation_model.primary_action)

    def test_air_no_d_bottom_shows_remaining_and_surface_summary(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="60", depth_fsw=60)
        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.depth_timer_label, "61:00 remaining")
        self.assertEqual(presentation_model.summary_text, "Next: Surface")

    def test_air_o2_bottom_hides_remaining_timer_before_deco_obligation(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="145", depth_fsw=145)
        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertIsNone(presentation_model.depth_timer_label)
        self.assertEqual(presentation_model.summary_text, "Next: Surface")

    def test_preselected_air_surd_uses_air_schedule_before_handoff(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="120", depth_fsw=120)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)

        bottom = build_presentation_model(coordinator.view())
        self.assertEqual(coordinator.view().mode, EngineMode.AIR)
        self.assertEqual(bottom.summary_kind, "default")
        self.assertEqual(bottom.summary_text, "Next: Surface")

        current["now"] += timedelta(minutes=87)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=7)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)

        forty_stop = build_presentation_model(coordinator.view())
        self.assertEqual(forty_stop.summary_kind, "surd_travel")
        self.assertEqual(forty_stop.summary_text, "Next: Surface | 3.5 periods at 50")

    def test_preselected_air_surd_bottom_still_shows_required_forty_stop(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=10)

        bottom = build_presentation_model(coordinator.view())
        self.assertEqual(bottom.summary_kind, "default")
        self.assertEqual(bottom.summary_text, "Next: 40 fsw for 1 min")

    def test_preselected_air_surd_leave_bottom_to_shallow_stop_collapses_to_surface(self) -> None:
        current = {"now": datetime(2026, 5, 2, 15, 24, 38)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 2, 15, 27, 42)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 5, 2, 15, 32, 48)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        traveling = build_presentation_model(coordinator.view())
        self.assertEqual(traveling.summary_kind, "surd_travel")
        self.assertEqual(traveling.summary_text, "Next: Surface | .5 periods at 50")
        assert traveling.primary_action is not None
        self.assertEqual(traveling.primary_action.action_name, "REACH_SURFACE")
        self.assertEqual(traveling.primary_action.label, "Reach Surface")

    def test_air_reached_stop_log_uses_depth_not_ordinal(self) -> None:
        rows = build_dive_log(
            (
                AuditEvent(
                    kind=AuditEventKind.REACHED_STOP,
                    at=datetime(2026, 5, 3, 12, 0, 0),
                    payload={"stop_index": 1, "depth_fsw": 40, "gas": "air"},
                ),
            ),
            mode=EngineMode.AIR,
        )

        self.assertEqual([row.summary for row in rows], ["Arrive 40 fsw"])

    def test_air_o2_leave_thirty_resumes_visible_ascent_immediately(self) -> None:
        current = {"now": datetime(2026, 5, 3, 17, 57, 30)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 3, 18, 1, 37)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 5, 3, 18, 3, 27)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] = datetime(2026, 5, 3, 18, 9, 32)
        coordinator.dispatch(EngineAction.REACH_STOP)
        coordinator.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] = datetime(2026, 5, 3, 18, 10, 32)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] = datetime(2026, 5, 3, 18, 10, 33)

        traveling = coordinator.view()
        self.assertEqual(traveling.phase_name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(traveling.display_depth_fsw, 29)

    def test_air_o2_cannot_leave_fifty_stop_before_one_minute_completes(self) -> None:
        current = {"now": datetime(2026, 5, 3, 19, 35, 5)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="189", depth_fsw=189)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 3, 19, 40, 9)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 5, 3, 19, 45, 13)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] = datetime(2026, 5, 3, 19, 49, 51)
        coordinator.dispatch(EngineAction.REACH_STOP)

        stop_view = coordinator.view()
        self.assertEqual(stop_view.current_stop_depth_fsw, 50)
        self.assertNotIn("LEAVE_STOP", stop_view.available_actions)

        current["now"] = datetime(2026, 5, 3, 19, 50, 19)
        events = coordinator.dispatch(EngineAction.LEAVE_STOP)

        self.assertEqual(events[0].kind.name, "INVALID_ACTION")
        self.assertEqual(coordinator.view().current_stop_depth_fsw, 50)

    def test_air_surd_surface_direct_logs_reached_surface_before_handoff(self) -> None:
        current = {"now": datetime(2026, 5, 2, 15, 24, 38)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 2, 15, 27, 42)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 5, 2, 15, 32, 48)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=1)
        events = coordinator.dispatch(EngineAction.REACH_SURFACE)

        rows = build_dive_log(events, mode=EngineMode.SURD)
        self.assertEqual([row.summary for row in rows], ["RS", "SURD Handoff Ready"])

    def test_preselected_air_surd_surface_leg_switches_to_forty_fpm_above_surface(self) -> None:
        current = {"now": datetime(2026, 5, 2, 15, 31, 35)}
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: current["now"],
        )
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 2, 15, 34, 43)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] = datetime(2026, 5, 2, 15, 39, 49)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        current["now"] += timedelta(minutes=5)
        self.assertEqual(coordinator.view().display_depth_fsw, 40)

        current["now"] += timedelta(minutes=1)
        self.assertEqual(coordinator.view().display_depth_fsw, 0)

    def test_preselected_mixed_gas_surd_forty_stop_uses_surface_in_blue(self) -> None:
        now = datetime(2026, 4, 29, 12, 0, 0)
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.MIXED_GAS,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: now,
        )
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=190,
            bottom_mix_o2_percent=14.0,
            breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
            plan=MixedGasPlan(
                input_depth_fsw=190,
                input_bottom_time_min=10,
                table_depth_fsw=190,
                table_bottom_time_min=10,
                stops=(
                    MixedGasStop(index=1, depth_fsw=40, gas="50_50", duration_min=7),
                    MixedGasStop(index=2, depth_fsw=30, gas="o2", duration_min=2),
                ),
            ),
            current_stop_index=1,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        )

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_kind, "surd_travel")
        self.assertEqual(presentation_model.summary_text, "Next: Surface | 1 period at 50")

    def test_preselected_mixed_gas_surd_fifty_stop_keeps_next_in_water_stop(self) -> None:
        now = datetime(2026, 5, 2, 18, 12, 17)
        coordinator = EngineCoordinator(
            diving_mode=DivingMode.MIXED_GAS,
            deco_profile=DecoProfile.SURD,
            now_provider=lambda: now,
        )
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.AT_STOP,
            depth_fsw=190,
            bottom_mix_o2_percent=14.0,
            breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
            plan=MixedGasPlan(
                input_depth_fsw=190,
                input_bottom_time_min=10,
                table_depth_fsw=190,
                table_bottom_time_min=10,
                stops=(
                    MixedGasStop(index=1, depth_fsw=90, gas="50_50", duration_min=7),
                    MixedGasStop(index=2, depth_fsw=60, gas="50_50", duration_min=9),
                    MixedGasStop(index=3, depth_fsw=50, gas="50_50", duration_min=9),
                    MixedGasStop(index=4, depth_fsw=30, gas="o2", duration_min=2),
                ),
            ),
            current_stop_index=3,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=now)),
        )

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_kind, "o2")
        self.assertEqual(presentation_model.summary_text, "Next: 30 fsw for 2 min")

    def test_surd_chamber_at_fifty_waiting_on_o2_shows_surface_interval_elapsed(self) -> None:
        now = datetime(2026, 5, 2, 18, 12, 17)
        engine = SurdEngine(now_provider=lambda: now)
        handoff = InWaterToSurdHandoff(
            entry_kind=SurdEntryKind.L40_NORMAL,
            source_mode="MIXED_GAS",
            input_depth_fsw=220,
            input_bottom_time_min=30,
            source_table_depth_fsw=220,
            source_table_bottom_time_min=30,
            left_water_stop_depth_fsw=40,
            remaining_in_water_obligation_sec=60,
            handed_off_at=now,
        )
        engine.start_handoff(handoff)
        engine.state = replace(
            engine.state,
            phase=engine.state.phase.CHAMBER_AT_50_WAITING_O2,
            to_chamber_timer=None,
        )

        presentation_model = build_presentation_model(engine.view())
        self.assertEqual(presentation_model.primary_value, "00:00.0")
        self.assertEqual(presentation_model.summary_text, "Next: On O2")

    def test_mixed_gas_surd_chamber_on_o2_at_fifty_with_penalty_previews_air_break(self) -> None:
        current = {"now": datetime(2026, 5, 2, 18, 12, 17)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        handoff = InWaterToSurdHandoff(
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
        engine.start_handoff(handoff)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(seconds=63)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 2, 18, 18, 0)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=30)

        presentation_model = build_presentation_model(engine.view())
        self.assertEqual(presentation_model.summary_text, "Next: Air Break for 5 min")

    def test_surd_ready_to_move_after_air_break_keeps_primary_value_time_based(self) -> None:
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
        engine.dispatch(EngineAction.START_AIR_BREAK)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)

        presentation_model = build_presentation_model(engine.view())
        self.assertEqual(engine.view().phase_name, "CHAMBER_READY_TO_MOVE")
        self.assertEqual(presentation_model.primary_value, "00:00.0")

    def test_surd_chamber_on_o2_does_not_render_line_six_footer(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 58, 20)}
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
        current["now"] += timedelta(minutes=2, seconds=4)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=91)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] += timedelta(seconds=1)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(seconds=21)

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(engine.view().phase_name, "CHAMBER_ON_O2")
        self.assertEqual(presentation_model.detail_text, "")
        self.assertEqual(presentation_model.summary_text, "Next: 40 fsw for 15 min")
        self.assertEqual(presentation_model.summary_kind, "o2")

    def test_surd_chamber_at_forty_on_o2_previews_air_break(self) -> None:
        now = datetime(2026, 5, 2, 18, 12, 17)
        engine = SurdEngine(now_provider=lambda: now)
        handoff = InWaterToSurdHandoff(
            entry_kind=SurdEntryKind.L40_NORMAL,
            source_mode="MIXED_GAS",
            input_depth_fsw=210,
            input_bottom_time_min=10,
            source_table_depth_fsw=210,
            source_table_bottom_time_min=10,
            left_water_stop_depth_fsw=40,
            remaining_in_water_obligation_sec=60,
            handed_off_at=now,
        )
        engine.start_handoff(handoff)
        engine.state = replace(
            engine.state,
            phase=engine.state.phase.CHAMBER_ON_O2,
            chamber_plan=build_surd_chamber_plan(input_depth_fsw=220, input_bottom_time_min=30, penalty_kind=SurdPenaltyKind.NONE),
            current_segment_index=1,
            o2_timer=TimerState(started_at=now, carried_elapsed_sec=15 * 60),
            continuous_o2_anchor_at=now - timedelta(minutes=30),
        )

        presentation_model = build_presentation_model(engine.view())
        self.assertEqual(presentation_model.summary_text, "Next: Air Break for 5 min")
        self.assertEqual(presentation_model.summary_kind, "air_break")

    def test_surd_mixed_gas_two_hundred_ten_at_forty_on_o2_previews_air_break_in_red(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 18, 45)}
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
        current["now"] += timedelta(minutes=2, seconds=4)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(seconds=91)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] += timedelta(seconds=1)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=5, seconds=27)

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(engine.view().phase_name, "CHAMBER_ON_O2")
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)
        self.assertEqual(presentation_model.summary_text, "Next: Air Break for 5 min")
        self.assertEqual(presentation_model.summary_kind, "air_break")

    def test_surd_completed_final_forty_stop_keeps_leave_stop_primary_and_on_o2_secondary(self) -> None:
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

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(presentation_model.summary_text, "Next: Surface")
        self.assertEqual(presentation_model.detail_text, "")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "COMPLETE_TO_SURFACE")
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.action_name, "TOGGLE_OFF_O2")
        self.assertEqual(presentation_model.secondary_action.label, "On O2")

    def test_surd_final_surface_ascent_uses_reach_surface_primary(self) -> None:
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
        current["now"] = datetime(2026, 5, 3, 20, 57, 25)
        engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_SURFACE")
        self.assertEqual(presentation_model.summary_text, "Next: Reach Surface")
        self.assertEqual(presentation_model.detail_text, "")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "REACH_SURFACE")
        self.assertEqual(presentation_model.primary_action.label, "Reach Surface")
        self.assertEqual(presentation_model.secondary_action.label, "")

    def test_surd_final_surface_ascent_after_off_o2_is_not_o2_tinted(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 30, 47)}
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

        current["now"] = datetime(2026, 5, 3, 20, 32, 51)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 33, 53)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 34, 55)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] = datetime(2026, 5, 3, 20, 34, 56)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] = datetime(2026, 5, 3, 20, 50, 10)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] = datetime(2026, 5, 3, 20, 51, 13)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] = datetime(2026, 5, 3, 21, 5, 20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] = datetime(2026, 5, 3, 21, 5, 25)
        engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(engine.view().phase_name, "CHAMBER_TRAVEL_TO_SURFACE")
        self.assertEqual(engine.view().gas_state_name, "OFF_O2")
        self.assertEqual(presentation_model.gas_label, "Off O2")
        self.assertEqual(presentation_model.summary_kind, "default")

    def test_surd_clean_time_does_not_render_line_six_footer(self) -> None:
        current = {"now": datetime(2026, 5, 3, 20, 30, 47)}
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

        current["now"] = datetime(2026, 5, 3, 20, 32, 51)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 33, 53)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] = datetime(2026, 5, 3, 20, 34, 55)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        current["now"] = datetime(2026, 5, 3, 20, 34, 56)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] = datetime(2026, 5, 3, 20, 50, 10)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        current["now"] = datetime(2026, 5, 3, 20, 51, 13)
        engine.dispatch(EngineAction.REACH_STOP)
        current["now"] = datetime(2026, 5, 3, 21, 5, 20)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        current["now"] = datetime(2026, 5, 3, 21, 5, 25)
        engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)
        current["now"] = datetime(2026, 5, 3, 21, 6, 46)
        engine.dispatch(EngineAction.REACH_SURFACE)

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        self.assertEqual(engine.view().phase_name, "COMPLETE_CLEAN_TIME")
        self.assertEqual(presentation_model.detail_text, "")

    def test_surd_penalty_arrival_at_fifty_is_explicit_in_log(self) -> None:
        now = datetime(2026, 5, 2, 18, 17, 0)
        rows = build_dive_log(
            (
                AuditEvent(
                    kind=AuditEventKind.REACHED_STOP,
                    at=now,
                    payload={"chamber_depth_fsw": 50, "penalty_kind": "PLUS_15_AT_50"},
                ),
            ),
            mode=EngineMode.SURD,
        )
        self.assertEqual(rows[0].summary, "Arrive 50 fsw | SI Penalty +15 min O2")

    def test_air_descent_presentation_restores_hold_and_next_placeholder(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="78", depth_fsw=78)
        coordinator.dispatch(EngineAction.LEAVE_SURFACE)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_text, "Next: --")
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.secondary_action.label, "Hold")

    def test_chamber_ready_presentation_uses_leave_surface_and_o2_toggle(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])

        presentation_model = build_presentation_model(
            engine.view(),
            audit_events=engine.audit_events(),
            selected_table_name=None,
            tender_view=None,
        )
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.summary_text, "Next: Leave Surface")
        self.assertEqual(presentation_model.primary_action.action_name, "LEAVE_SURFACE")
        self.assertEqual(presentation_model.secondary_action.action_name, "")
        self.assertEqual(presentation_model.secondary_action.label, "Off/On O2")

    def test_chamber_descent_presentation_uses_reach_bottom_and_muted_o2_toggle(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])
        engine.dispatch(EngineAction.LEAVE_SURFACE)

        presentation_model = build_presentation_model(engine.view(), audit_events=engine.audit_events(), tender_view=None)
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "REACH_BOTTOM")
        self.assertEqual(presentation_model.secondary_action.action_name, "")
        self.assertEqual(presentation_model.secondary_action.label, "Off/On O2")

    def test_chamber_stop_waiting_on_o2_uses_leave_stop_and_on_o2_controls(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        presentation_model = build_presentation_model(engine.view(), audit_events=engine.audit_events(), tender_view=None)
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.primary_action.action_name, "")
        self.assertEqual(presentation_model.secondary_action.action_name, "CONFIRM_ON_O2")
        self.assertEqual(presentation_model.secondary_action.label, "On O2")

    def test_chamber_stop_on_o2_uses_leave_stop_and_off_o2_controls(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = ChamberEngine(now_provider=lambda: current["now"])
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        presentation_model = build_presentation_model(engine.view(), audit_events=engine.audit_events(), tender_view=None)
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.primary_action.action_name, "")
        self.assertEqual(presentation_model.secondary_action.action_name, "TOGGLE_OFF_O2")
        self.assertEqual(presentation_model.secondary_action.label, "Off O2")
        self.assertEqual(presentation_model.summary_text, "Next: 5 min air break")

    def test_chamber_presentation_model_surfaces_selected_table_after_tt5_lock(self) -> None:
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

        presentation_model = build_presentation_model(
            engine.view(),
            audit_events=engine.audit_events(),
            selected_table_name=engine.selected_table_name(),
            tender_view=None,
        )
        self.assertEqual(presentation_model.selected_table_label, "TT5")
        self.assertEqual(presentation_model.summary_text, "Next: Reach Stop")
        self.assertIsNone(presentation_model.tender_card)

    def test_chamber_presentation_model_surfaces_selected_table_after_tt6_lock(self) -> None:
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

        presentation_model = build_presentation_model(
            engine.view(),
            audit_events=engine.audit_events(),
            selected_table_name=engine.selected_table_name(),
            tender_view=None,
        )
        self.assertEqual(presentation_model.selected_table_label, "TT6")
        self.assertEqual(presentation_model.summary_text, "Next: On O2")

    def test_chamber_r30_break_pending_detail_is_explicit(self) -> None:
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

        presentation_model = build_presentation_model(
            engine.view(),
            audit_events=engine.audit_events(),
            selected_table_name=engine.selected_table_name(),
            tender_view=None,
        )
        self.assertEqual(presentation_model.selected_table_label, "TT5")
        self.assertEqual(presentation_model.summary_text, "Next: Air Break for 5 min")
        self.assertEqual(presentation_model.detail_text, "TT5 | Break Pending")

    def test_chamber_tt5_final_ascent_prep_detail_is_explicit(self) -> None:
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

        presentation_model = build_presentation_model(
            engine.view(),
            audit_events=engine.audit_events(),
            selected_table_name=engine.selected_table_name(),
            tender_view=None,
        )
        self.assertEqual(presentation_model.summary_text, "Next: Surface")
        self.assertEqual(presentation_model.detail_text, "TT5 | Final On O2")

    def test_air_o2_presentation_labels_o2_state_actions_contextually(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="145", depth_fsw=145)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=6)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)

        waiting = build_presentation_model(coordinator.view())
        self.assertEqual(waiting.status_value_text, "TSV")
        self.assertEqual(waiting.summary_kind, "o2")
        assert waiting.secondary_action is not None
        self.assertEqual(waiting.secondary_action.label, "On O2")

        coordinator.dispatch(EngineAction.CONFIRM_ON_O2)
        on_o2 = build_presentation_model(coordinator.view())
        self.assertEqual(on_o2.status_value_text, "On O2")
        assert on_o2.secondary_action is not None
        self.assertEqual(on_o2.secondary_action.label, "Off O2")

        coordinator.dispatch(EngineAction.TOGGLE_OFF_O2)
        off_o2 = build_presentation_model(coordinator.view())
        self.assertEqual(off_o2.status_value_text, "Off O2")
        self.assertEqual(off_o2.summary_text, "Next: On O2")
        assert off_o2.primary_action is not None
        self.assertEqual(off_o2.primary_action.label, "Convert To Air")
        assert off_o2.secondary_action is not None
        self.assertEqual(off_o2.secondary_action.label, "On O2")

    def test_air_o2_traveling_on_o2_and_air_break_due_match_legacy_rows(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="120", depth_fsw=120)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=87)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=7)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=26)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)
        coordinator.dispatch(EngineAction.CONFIRM_ON_O2)

        current["now"] += timedelta(minutes=14)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        traveling = build_presentation_model(coordinator.view())
        self.assertEqual(traveling.status_value_text, "On O2/ Traveling")
        self.assertEqual(traveling.depth_timer_label, "80:00 left")
        self.assertEqual(traveling.summary_kind, "o2")

        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)
        break_due = build_presentation_model(coordinator.view())
        self.assertEqual(break_due.summary_text, "Next: Air break in 14:00")
        self.assertEqual(break_due.summary_kind, "air_break")

    def test_surd_chamber_waiting_on_o2_uses_secondary_button(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="AIR",
                input_depth_fsw=120,
                input_bottom_time_min=90,
                source_table_depth_fsw=120,
                source_table_bottom_time_min=90,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

        presentation_model = build_presentation_model(engine.view())
        self.assertIsNone(presentation_model.primary_action)
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.secondary_action.label, "On O2")

    def test_surd_chamber_on_o2_uses_leave_stop_primary_and_off_o2_secondary(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        engine.start_handoff(
            InWaterToSurdHandoff(
                entry_kind=SurdEntryKind.L40_NORMAL,
                source_mode="AIR",
                input_depth_fsw=120,
                input_bottom_time_min=90,
                source_table_depth_fsw=120,
                source_table_bottom_time_min=90,
                left_water_stop_depth_fsw=40,
                remaining_in_water_obligation_sec=0.0,
                handed_off_at=current["now"],
            )
        )

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=15)

        presentation_model = build_presentation_model(engine.view())
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.label, "Off O2")

    def test_surd_penalty_on_o2_keeps_leave_stop_disabled_and_previews_air_break(self) -> None:
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

        presentation_model = build_presentation_model(engine.view())
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.status_value_text, "On O2")
        self.assertEqual(presentation_model.summary_text, "Next: Air Break for 5 min")
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.primary_action.action_name, "")
        self.assertEqual(presentation_model.secondary_action.label, "Off O2")

    def test_surd_penalty_air_break_makes_leave_stop_available_for_move_to_forty(self) -> None:
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

        presentation_model = build_presentation_model(engine.view(), schedule_label=engine.schedule_label())
        assert presentation_model.primary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "MOVE_CHAMBER")
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.summary_text, "Next: 40 fsw for 15 min")

    def test_air_o2_upcoming_o2_stop_keeps_next_line_green(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="145", depth_fsw=145)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=39)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)  # 50
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)  # 40

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_text, "Next: 30 fsw for 12 min")
        self.assertEqual(presentation_model.summary_kind, "o2")

    def test_air_o2_bottom_summary_marks_direct_o2_first_stop_green_for_190_8(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=5)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_text, "Next: 30 fsw for 1 min")
        self.assertEqual(presentation_model.summary_kind, "o2")

    def test_active_air_delay_presentation_shows_delay_status(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="78", depth_fsw=78)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=47)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(seconds=10)
        coordinator.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(minutes=2)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.phase_label, "Delay")
        self.assertEqual(presentation_model.status_value_text, "Delay")

    def test_air_clean_time_presentation_appears_after_reach_surface(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR_O2, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="190", depth_fsw=190)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=5)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=1)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=1)
        coordinator.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=1)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=4)
        coordinator.dispatch(EngineAction.LEAVE_STOP)
        coordinator.dispatch(EngineAction.REACH_SURFACE)

        presentation_model = build_presentation_model(coordinator.view(), schedule_label="190 / 10")
        self.assertEqual(presentation_model.phase_label, "Clean Time")
        self.assertEqual(presentation_model.status_value_text, "Clean Time")
        self.assertEqual(presentation_model.primary_value, "10:00")
        self.assertEqual(presentation_model.depth_inline_text, "Surface")
        self.assertIsNone(presentation_model.depth_timer_label)
        self.assertIsNone(presentation_model.remaining_label)
        self.assertEqual(presentation_model.summary_text, "190 / 10")
        self.assertEqual(presentation_model.summary_kind, "default")

    def test_mixed_gas_clean_time_presentation_prints_table_and_schedule_after_reach_surface(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: now)
        coordinator._mixed_gas.state = replace(
            coordinator._mixed_gas.state,
            phase=MixedGasPhase.COMPLETE,
            clean_time_timer=MixedGasTimer(kind=MixedGasTimerKind.CLEAN_TIME, timer=TimerState(started_at=now)),
            plan=MixedGasPlan(
                input_depth_fsw=220,
                input_bottom_time_min=14,
                table_depth_fsw=220,
                table_bottom_time_min=20,
                stops=(),
            ),
        )

        presentation_model = build_presentation_model(coordinator.view(), schedule_label=coordinator.schedule_label())
        self.assertEqual(presentation_model.phase_label, "Clean Time")
        self.assertEqual(presentation_model.status_value_text, "Clean Time")
        self.assertEqual(presentation_model.primary_value, "10:00")
        self.assertEqual(presentation_model.depth_inline_text, "Surface")
        self.assertEqual(presentation_model.summary_text, "220 / 20")
        self.assertEqual(presentation_model.summary_kind, "default")

    def test_final_ascent_prioritizes_reach_surface_over_delay(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="78", depth_fsw=78)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_BOTTOM)
        current["now"] += timedelta(minutes=47)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        coordinator.dispatch(EngineAction.REACH_STOP)
        current["now"] += timedelta(minutes=17)
        coordinator.dispatch(EngineAction.LEAVE_STOP)

        presentation_model = build_presentation_model(coordinator.view())
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "REACH_SURFACE")
        self.assertEqual(presentation_model.secondary_action.action_name, "START_DELAY")
        self.assertEqual(presentation_model.summary_text, "Next: Reach Surface")
        self.assertEqual(presentation_model.detail_text, "")

    def test_mixed_gas_final_ascent_hides_line_six_and_shows_reach_surface(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: current["now"])
        coordinator.set_depth(raw_text="220", depth_fsw=220)
        coordinator.set_bottom_mix(raw_text="14.0", bottom_mix_o2_percent=14.0)

        coordinator.dispatch(EngineAction.LEAVE_SURFACE)
        coordinator.dispatch(EngineAction.REACH_STOP)
        coordinator.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        coordinator.dispatch(EngineAction.CONVERT_TO_AIR)
        coordinator.dispatch(EngineAction.LEAVE_BOTTOM)

        presentation_model = build_presentation_model(coordinator.view())
        self.assertEqual(presentation_model.summary_text, "Next: Reach Surface")
        self.assertEqual(presentation_model.detail_text, "")
        assert presentation_model.primary_action is not None
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.action_name, "REACH_SURFACE")
        self.assertEqual(presentation_model.secondary_action.action_name, "START_DELAY")

    def test_presentation_log_rows_render_derived_dive_log_entries(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(kind=AuditEventKind.MODE_LAUNCHED, at=now, payload={"mode": "AIR"}),
                AuditEvent(kind=AuditEventKind.INPUT_UPDATED, at=now, payload={"field": "depth_fsw", "raw_text": "78", "value": 78}),
                AuditEvent(kind=AuditEventKind.ACTION_DISPATCHED, at=now, payload={"action": "LEAVE_SURFACE"}),
                AuditEvent(kind=AuditEventKind.LEFT_SURFACE, at=now),
            ),
        )
        self.assertEqual(
            [row.summary for row in presentation_model.log_rows],
            [
                "LS",
            ],
        )
        self.assertEqual([row.tone for row in presentation_model.log_rows], ["default"])

    def test_mixed_gas_log_rows_show_grace_based_bottom_time_anchor_at_leave_twenty(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(kind=AuditEventKind.LEFT_STOP, at=now, payload={"depth_fsw": 20, "gas": "bottom_mix", "bottom_time_anchor": "grace_5_min"}),
            ),
        )
        self.assertEqual([row.summary for row in presentation_model.log_rows], ["Leave 20 fsw | BT @ 5:00"])

    def test_mixed_gas_log_rows_render_bottom_mix_confirmation_as_gas_change(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(
                    kind=AuditEventKind.REACHED_STOP,
                    at=now,
                    payload={"confirmation": "bottom_mix", "depth_fsw": 20},
                ),
            ),
        )
        self.assertEqual([row.summary for row in presentation_model.log_rows], ["On Bottom-mix"])

    def test_mixed_gas_log_rows_render_fifty_fifty_confirmation_as_gas_change(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(
                    kind=AuditEventKind.REACHED_STOP,
                    at=now,
                    payload={"confirmation": "50_50", "depth_fsw": 80},
                ),
            ),
        )
        self.assertEqual([row.summary for row in presentation_model.log_rows], ["On 50/50"])

    def test_mixed_gas_delay_log_row_shows_recompute_branch_and_schedule_change(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.MIXED_GAS, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(
                    kind=AuditEventKind.DELAY_RESOLVED,
                    at=now,
                    payload={
                        "branch": "first_stop_add_to_bottom_time",
                        "previous_schedule": "220 / 10",
                        "updated_schedule": "220 / 20",
                    },
                ),
            ),
        )
        self.assertEqual([row.summary for row in presentation_model.log_rows], ["Delay Recompute | first_stop_add_to_bottom_time | 220 / 10 -> 220 / 20"])

    def test_invalid_action_rows_are_hidden_from_user_dive_log(self) -> None:
        now = datetime(2026, 4, 25, 12, 0, 0)
        coordinator = _coordinator_from_mode(EngineMode.AIR, now_provider=lambda: now)
        presentation_model = build_presentation_model(
            coordinator.view(),
            audit_events=(
                AuditEvent(kind=AuditEventKind.INVALID_ACTION, at=now, payload={"action": "REACH_BOTTOM"}),
            ),
        )
        self.assertEqual(presentation_model.log_rows, ())


if __name__ == "__main__":
    unittest.main()
