from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.surd_engine import (
    SurfaceEngine,
    SurfaceIntent,
    SurfaceIntervalSubphase,
    SurfacePhase,
    build_l40_surface_handoff,
)
from dive_stopwatch.core.air_o2_profiles import build_surface_profile


class SURDEngineTests(unittest.TestCase):
    def _current_segment(self, engine: SurfaceEngine):
        plan = engine.state.surd_chamber_plan
        index = engine.state.current_o2_segment_index
        self.assertIsNotNone(plan)
        self.assertIsNotNone(index)
        return plan.segments[index]

    def _new_engine(self, *, depth: int = 150, bottom_time: int = 45, schedule: str = "150 / 45 Z"):
        current = {"now": datetime(2026, 4, 20, 12, 0, 0)}
        engine = SurfaceEngine(now_provider=lambda: current["now"])
        handoff = build_l40_surface_handoff(
            source_mode="SURDO2",
            input_depth_fsw=depth,
            input_bottom_time_min=bottom_time,
            source_profile_schedule_text=schedule,
            event_log=("L2 12:00:00",),
            handed_off_at=current["now"],
        )
        engine.start_handoff(handoff)
        return engine, current

    def _reach_surface(self, engine: SurfaceEngine, current: dict, *, at: timedelta = timedelta(minutes=1)) -> None:
        current["now"] += at
        engine.dispatch(SurfaceIntent.PRIMARY)

    def _leave_surface(self, engine: SurfaceEngine, current: dict, *, after: timedelta = timedelta(minutes=1)) -> None:
        current["now"] += after
        engine.dispatch(SurfaceIntent.PRIMARY)

    def _reach_bottom_50(self, engine: SurfaceEngine, current: dict, *, after: timedelta = timedelta(minutes=1)) -> None:
        current["now"] += after
        engine.dispatch(SurfaceIntent.PRIMARY)

    def _start_on_o2(self, engine: SurfaceEngine) -> None:
        engine.dispatch(SurfaceIntent.SECONDARY)

    def _normal_flow_to_r50(self, engine: SurfaceEngine, current: dict) -> None:
        self._reach_surface(engine, current)
        self._leave_surface(engine, current)
        self._reach_bottom_50(engine, current)

    def _normal_flow_to_on_o2(self, engine: SurfaceEngine, current: dict) -> None:
        self._normal_flow_to_r50(engine, current)
        self._start_on_o2(engine)

    def _complete_first_o2_period_and_start_air_break(self, engine: SurfaceEngine, current: dict) -> None:
        self._normal_flow_to_on_o2(engine, current)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(SurfaceIntent.PRIMARY)

    def test_build_surface_profile_uses_air_schedule_and_chamber_periods(self) -> None:
        profile = build_surface_profile(150, 45)

        self.assertEqual(profile.table_depth_fsw, 150)
        self.assertEqual(profile.table_bottom_time_min, 45)
        self.assertEqual([(stop.depth_fsw, stop.duration_min, stop.gas) for stop in profile.in_water_stops], [(50, 3, "air"), (40, 8, "air")])
        self.assertEqual(profile.chamber_o2_half_periods, 4)
        self.assertEqual(profile.repeat_group, "Z")

    def test_l40_handoff_starts_surface_ascent_and_prompts_reach_surface(self) -> None:
        engine, current = self._new_engine()
        current["now"] += timedelta(seconds=30)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.SURFACE_INTERVAL)
        self.assertEqual(engine.state.interval_subphase, SurfaceIntervalSubphase.ASCENT_TO_SURFACE)
        self.assertEqual(snap.status_text, "40 -> Surface")
        self.assertEqual(snap.depth_text, "20 fsw")
        self.assertEqual(snap.detail_text, "")
        self.assertEqual(snap.summary_text, "Next: Undress")
        self.assertEqual(snap.primary_button_label, "Reach Surface")
        self.assertTrue(snap.primary_button_enabled)
        self.assertTrue(snap.primary_text.startswith("00:30"))
        self.assertEqual(engine.recall_lines()[:2], (
            "SurD start from 40 fsw 12:00:00",
            "Traveling 40 -> Surface 12:00:00",
        ))

    def test_reaching_surface_starts_undress_phase(self) -> None:
        engine, current = self._new_engine()
        self._reach_surface(engine, current, at=timedelta(seconds=90))
        snap = engine.snapshot()

        self.assertEqual(engine.state.interval_subphase, SurfaceIntervalSubphase.UNDRESS)
        self.assertEqual(snap.depth_text, "Surface")
        self.assertEqual(snap.summary_text, "Next: Surface -> 50 fsw")
        self.assertEqual(snap.primary_button_label, "Leave Surface")
        self.assertTrue(snap.primary_button_enabled)
        self.assertEqual(engine.recall_lines()[-2:], ("RS 12:01:30", "Undress 12:01:30"))

    def test_leaving_surface_starts_surface_to_fifty_phase(self) -> None:
        engine, current = self._new_engine()
        self._reach_surface(engine, current)
        self._leave_surface(engine, current)
        snap = engine.snapshot()

        self.assertEqual(engine.state.interval_subphase, SurfaceIntervalSubphase.SURFACE_TO_CHAMBER_50)
        self.assertEqual(snap.status_text, "Surface -> 50 fsw")
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: 50 fsw")
        self.assertEqual(snap.primary_button_label, "Reach Bottom")
        self.assertTrue(snap.primary_button_enabled)
        self.assertEqual(engine.recall_lines()[-2:], ("LS 12:02:00", "Traveling Surface -> Chamber 50 12:02:00"))

    def test_primary_in_surface_interval_advances_only_one_explicit_step(self) -> None:
        engine, current = self._new_engine()
        self._reach_surface(engine, current, at=timedelta(seconds=30))

        self.assertEqual(engine.state.phase, SurfacePhase.SURFACE_INTERVAL)
        self.assertEqual(engine.state.interval_subphase, SurfaceIntervalSubphase.UNDRESS)

    def test_reaching_bottom_at_fifty_waits_for_on_o2_confirmation(self) -> None:
        engine, current = self._new_engine()
        self._normal_flow_to_r50(engine, current)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(snap.status_text, "50 fsw")
        self.assertEqual(snap.depth_text, "50 fsw")
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 1)
        self.assertEqual(current_segment.depth_fsw, 50)
        self.assertEqual(current_segment.duration_sec, 15 * 60)
        self.assertEqual(snap.summary_text, "Next: 50 fsw for 15 min")
        self.assertEqual(snap.secondary_button_label, "On O2")
        self.assertTrue(snap.secondary_button_enabled)
        self.assertIn("RB 12:03:00", engine.recall_lines())
        self.assertIn("Chamber 50 12:03:00", engine.recall_lines())

    def test_on_o2_at_fifty_sets_next_to_forty_for_fifteen_minutes(self) -> None:
        engine, current = self._new_engine()
        self._normal_flow_to_on_o2(engine, current)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(snap.status_text, "50 fsw O2")
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: 40 fsw for 15 min")
        self.assertEqual(snap.secondary_button_label, "Off O2")
        self.assertTrue(snap.secondary_button_enabled)
        self.assertEqual(snap.detail_text, "O2 00:00 | 15:00 left")
        self.assertIn("On O2 50 12:03:00", engine.recall_lines())
        self.assertIn("50 fsw O2 12:03:00", engine.recall_lines())

    def test_chamber_o2_secondary_toggles_off_o2_and_preserves_remaining_time(self) -> None:
        engine, current = self._new_engine()
        self._normal_flow_to_on_o2(engine, current)
        current["now"] += timedelta(minutes=3)

        before = engine.snapshot()
        self.assertEqual(before.detail_text, "O2 03:00 | 12:00 left")
        self.assertEqual(before.secondary_button_label, "Off O2")
        self.assertTrue(before.secondary_button_enabled)

        engine.dispatch(SurfaceIntent.SECONDARY)
        off_o2 = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(off_o2.status_text, "OFF O2")
        self.assertEqual(off_o2.status_value_kind, "off_o2")
        self.assertEqual(off_o2.primary_value_kind, "off_o2")
        self.assertEqual(off_o2.detail_kind, "off_o2")
        self.assertEqual(off_o2.summary_text, "Next: On O2")
        self.assertEqual(off_o2.secondary_button_label, "On O2")
        self.assertTrue(off_o2.secondary_button_enabled)
        self.assertEqual(off_o2.detail_text, "Off O2 00:00 | 12:00 left")
        self.assertIn("Off O2 12:06:00", engine.recall_lines())

        current["now"] += timedelta(minutes=2)
        still_off = engine.snapshot()
        self.assertEqual(still_off.detail_text, "Off O2 02:00 | 12:00 left")

        engine.dispatch(SurfaceIntent.SECONDARY)
        resumed = engine.snapshot()

        self.assertEqual(resumed.status_text, "50 fsw O2")
        self.assertEqual(resumed.status_value_kind, "o2")
        self.assertEqual(resumed.detail_kind, "o2")
        self.assertEqual(resumed.secondary_button_label, "Off O2")
        self.assertEqual(resumed.detail_text, "O2 03:00 | 12:00 left")
        self.assertIn("On O2 50 12:08:00", engine.recall_lines())
        self.assertIn("50 fsw O2 12:08:00", engine.recall_lines())

    def test_first_oxygen_period_requires_user_input_to_move_from_50_to_40_segment(self) -> None:
        engine, current = self._new_engine()
        self._normal_flow_to_on_o2(engine, current)
        current["now"] += timedelta(minutes=15)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 50)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 1)
        self.assertEqual(current_segment.depth_fsw, 50)
        self.assertEqual(snap.status_text, "50 fsw O2")
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: Move chamber to 40 fsw")
        self.assertEqual(snap.detail_text, "First 50 fsw segment complete")
        self.assertEqual(snap.primary_button_label, "Chamber 40")
        self.assertTrue(snap.primary_button_enabled)

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 40)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 1)
        self.assertEqual(current_segment.depth_fsw, 40)
        self.assertEqual(snap.status_text, "40 fsw O2")
        self.assertEqual(snap.depth_text, "40 fsw")
        self.assertEqual(snap.summary_text, "First O2 period: 40 fsw segment")
        self.assertEqual(snap.detail_text, "O2 00:00 | 15:00 left")
        self.assertEqual(engine.recall_lines()[-2:], (
            "Chamber 40 12:18:00",
            "40 fsw O2 12:18:00",
        ))

    def test_first_oxygen_period_requires_user_input_to_start_air_break(self) -> None:
        engine, current = self._new_engine()
        self._normal_flow_to_on_o2(engine, current)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=15)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 40)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 1)
        self.assertEqual(current_segment.depth_fsw, 40)
        self.assertEqual(snap.summary_text, "Next: Start air break")
        self.assertEqual(snap.detail_text, "First O2 period complete")
        self.assertEqual(snap.primary_button_label, "Start Air Break")
        self.assertTrue(snap.primary_button_enabled)

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_AIR_BREAK)
        self.assertEqual(snap.status_text, "40 fsw Air Break")
        self.assertEqual(snap.depth_text, "40 fsw")
        self.assertEqual(snap.status_value_kind, "air_break")
        self.assertEqual(snap.primary_value_kind, "air_break")
        self.assertEqual(snap.detail_kind, "air_break")
        self.assertEqual(snap.summary_text, "Chamber air break")
        self.assertEqual(snap.detail_text, "Air 00:00 | 05:00 left")
        self.assertEqual(engine.recall_lines()[-2:], (
            "Air break start 12:33:00",
            "40 fsw Air Break 12:33:00",
        ))

    def test_air_break_requires_user_input_to_resume_period_2(self) -> None:
        engine, current = self._new_engine()
        self._complete_first_o2_period_and_start_air_break(engine, current)
        current["now"] += timedelta(minutes=5)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_AIR_BREAK)
        self.assertEqual(snap.summary_text, "Next: Resume O2 period 2")
        self.assertEqual(snap.detail_text, "Air break complete")
        self.assertEqual(snap.primary_button_label, "Resume O2")
        self.assertTrue(snap.primary_button_enabled)

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 40)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 2)
        self.assertEqual(current_segment.depth_fsw, 40)
        self.assertEqual(current_segment.duration_sec, 30 * 60)
        self.assertEqual(snap.summary_text, "O2 period 2")
        self.assertEqual(snap.detail_text, "O2 00:00 | 30:00 left")
        self.assertEqual(engine.recall_lines()[-2:], (
            "On O2 40 12:38:00",
            "40 fsw O2 12:38:00",
        ))

    def test_final_period_does_not_offer_extra_air_break(self) -> None:
        engine, current = self._new_engine()
        self._complete_first_o2_period_and_start_air_break(engine, current)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=30)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 2)
        self.assertEqual(snap.summary_text, "Next: Surface")
        self.assertEqual(snap.detail_text, "Final O2 period complete")
        self.assertEqual(snap.primary_button_label, "Reach Surface")
        self.assertTrue(snap.primary_button_enabled)

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.COMPLETE)
        self.assertEqual(snap.status_text, "CLEAN TIME")
        self.assertEqual(snap.depth_text, "Surface")
        self.assertEqual(snap.primary_text, "10:00")
        self.assertEqual(engine.recall_lines()[-2:], (
            "RS 13:08:00",
            "Surface 13:08:00",
        ))

    def test_air_break_can_move_chamber_from_40_to_30_before_period_5(self) -> None:
        engine, current = self._new_engine(depth=170, bottom_time=90, schedule="170 / 90")
        self._normal_flow_to_on_o2(engine, current)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=15)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=5)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=30)
        engine.dispatch(SurfaceIntent.PRIMARY)
        current["now"] += timedelta(minutes=5)

        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_AIR_BREAK)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 40)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 4)
        self.assertEqual(current_segment.depth_fsw, 40)
        self.assertEqual(snap.summary_text, "Next: Move chamber to 30 fsw")
        self.assertEqual(snap.primary_button_label, "Chamber 30")
        self.assertTrue(snap.primary_button_enabled)

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_AIR_BREAK)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 30)
        self.assertEqual(snap.summary_text, "Next: Resume O2 period 5")
        self.assertEqual(snap.primary_button_label, "Resume O2")

        engine.dispatch(SurfaceIntent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.phase, SurfacePhase.CHAMBER_OXYGEN)
        self.assertEqual(engine.state.current_chamber_depth_fsw, 30)
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 5)
        self.assertEqual(current_segment.depth_fsw, 30)
        self.assertEqual(current_segment.duration_sec, 30 * 60)
        self.assertEqual(snap.summary_text, "O2 period 5")
        self.assertEqual(snap.detail_text, "O2 00:00 | 30:00 left")
        self.assertIn("Chamber 30 14:23:00", engine.recall_lines())
        self.assertIn("On O2 30 14:23:00", engine.recall_lines())
        self.assertIn("30 fsw O2 14:23:00", engine.recall_lines())

    def test_surface_interval_over_five_minutes_flags_penalty_path(self) -> None:
        engine, current = self._new_engine()
        current["now"] += timedelta(minutes=5, seconds=10)
        snap = engine.snapshot()

        self.assertEqual(snap.summary_text, "Next: Chamber 50 with penalty")
        self.assertEqual(snap.detail_text, "05:00-07:00 adds 15 min O2 at 50")
        self.assertEqual(snap.primary_value_kind, "warning")
        self._reach_surface(engine, current, at=timedelta())
        self._leave_surface(engine, current, after=timedelta())
        self._reach_bottom_50(engine, current, after=timedelta())
        self.assertEqual(engine.recall_lines()[0:2], (
            "SurD start from 40 fsw 12:00:00",
            "Traveling 40 -> Surface 12:00:00",
        ))
        self.assertIn("RS 12:05:10", engine.recall_lines())
        self.assertIn("Undress 12:05:10", engine.recall_lines())
        self.assertIn("LS 12:05:10", engine.recall_lines())
        self.assertIn("Traveling Surface -> Chamber 50 12:05:10", engine.recall_lines())
        self.assertIn("Surface interval penalty (+15 O2 @ 50) 12:05:10", engine.recall_lines())
        self.assertIn("RB 12:05:10", engine.recall_lines())
        self.assertIn("Chamber 50 12:05:10", engine.recall_lines())
        snap = engine.snapshot()
        current_segment = self._current_segment(engine)
        self.assertEqual(current_segment.period_number, 1)
        self.assertEqual(current_segment.depth_fsw, 50)
        self.assertEqual(current_segment.duration_sec, 30 * 60)
        self.assertEqual(snap.summary_text, "Next: 50 fsw for 30 min")
        self.assertEqual(snap.secondary_button_label, "On O2")

    def test_surface_interval_over_seven_minutes_marks_exceeded_in_red(self) -> None:
        engine, current = self._new_engine()
        current["now"] += timedelta(minutes=7, seconds=10)

        snap = engine.snapshot()

        self.assertEqual(snap.summary_text, "Surface interval exceeded")
        self.assertEqual(snap.summary_value_kind, "air_break")
        self.assertEqual(snap.primary_value_kind, "air_break")


if __name__ == "__main__":
    unittest.main()
