from datetime import datetime, timedelta
import unittest

from dive_stopwatch.minimal.engine import DivePhase, Engine, Intent
from dive_stopwatch.minimal.profiles import DecoMode


class MinimalEngineTests(unittest.TestCase):
    def test_stopwatch_start_stop_and_reset(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])

        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(seconds=12)
        running = engine.snapshot()
        self.assertEqual(running.status_text, "RUNNING")

        engine.dispatch(Intent.PRIMARY)
        stopped = engine.snapshot()
        self.assertEqual(stopped.status_text, "READY")
        self.assertTrue(stopped.primary_text.startswith("00:12"))

        engine.dispatch(Intent.SECONDARY)
        reset = engine.snapshot()
        self.assertEqual(reset.primary_text, "00:00.0")

    def test_stopwatch_lap_is_visible_in_log_and_detail(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])

        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(seconds=12, milliseconds=300)
        engine.dispatch(Intent.SECONDARY)

        snap = engine.snapshot()
        self.assertEqual(snap.secondary_button_label, "Lap")
        self.assertEqual(snap.detail_text, "Laps: 1")
        self.assertEqual(engine.state.stopwatch.lap_count, 1)
        self.assertEqual(engine.state.ui_log[-1], "Lap 1 00:12.3")

    def test_mode_cycles_stopwatch_dive_air_air_o2_then_back(self) -> None:
        engine = Engine(now_provider=lambda: datetime(2026, 4, 12, 12, 0, 0))
        self.assertEqual(engine.snapshot().mode_text, "STOPWATCH")
        self.assertIsNone(engine.state.deco_mode)

        engine.dispatch(Intent.MODE)
        self.assertEqual(engine.state.deco_mode, DecoMode.AIR)
        self.assertEqual(engine.snapshot().mode_text, "AIR")

        engine.dispatch(Intent.MODE)
        self.assertEqual(engine.state.deco_mode, DecoMode.AIR_O2)
        self.assertEqual(engine.snapshot().mode_text, "AIR/O2")

        engine.dispatch(Intent.MODE)
        self.assertIsNone(engine.state.deco_mode)
        snap = engine.snapshot()
        self.assertEqual(snap.mode_text, "STOPWATCH")

    def test_basic_dive_progression_builds_profile_and_stop(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)

        engine.dispatch(Intent.PRIMARY)  # LS
        self.assertEqual(engine.state.dive.phase, DivePhase.DESCENT)

        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)

        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        self.assertEqual(engine.state.dive.phase, DivePhase.TRAVEL)
        self.assertEqual(engine.state.dive.profile.table_depth_fsw, 150)
        self.assertEqual(engine.state.dive.profile.table_bottom_time_min, 45)

        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1
        snap = engine.snapshot()
        self.assertEqual(engine.state.dive.phase, DivePhase.AT_STOP)
        self.assertEqual(snap.status_text, "AT STOP")
        self.assertEqual(snap.depth_text, "50 fsw")

    def test_surface_enters_clean_time_and_shows_final_table_schedule(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("60")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=10)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.PRIMARY)  # RS

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.SURFACE)
        self.assertEqual(snap.status_text, "CLEAN TIME")
        self.assertEqual(snap.primary_text, "10:00")
        self.assertEqual(snap.depth_text, "60 / 12 B")
        self.assertEqual(snap.summary_text, "Monitor diver for signs and symptoms of AGE")
        self.assertFalse(snap.primary_button_enabled)
        self.assertFalse(snap.secondary_button_enabled)

    def test_bottom_phase_shows_no_secondary_action_until_supported(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB

        snap = engine.snapshot()
        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(snap.primary_button_label, "Leave Bottom")
        self.assertEqual(snap.secondary_button_label, "")
        self.assertFalse(snap.secondary_button_enabled)

    def test_bottom_phase_shows_no_decompression_limit_countdown(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2, seconds=20)
        engine.dispatch(Intent.PRIMARY)  # RB

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(snap.depth_text, "120 fsw")
        self.assertEqual(snap.remaining_text, "Bottom: 12:40 left")
        self.assertEqual(snap.summary_text, "Next: Surface")

    def test_bottom_countdown_switches_from_no_decompression_limit_to_deco_row(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=15)
        engine.dispatch(Intent.PRIMARY)  # RB at no-D limit

        at_limit = engine.snapshot()
        self.assertEqual(at_limit.remaining_text, "Bottom: 00:00 left")
        self.assertEqual(at_limit.summary_text, "Next: Surface")

        current["now"] += timedelta(seconds=40)
        after_limit = engine.snapshot()
        self.assertEqual(after_limit.remaining_text, "Bottom: 04:20 left")
        self.assertEqual(after_limit.summary_text, "Next: 20 fsw for 4m")

    def test_descent_hold_start_and_end_sequence(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS

        before = engine.snapshot()
        self.assertEqual(before.secondary_button_label, "Hold")
        self.assertTrue(before.secondary_button_enabled)

        engine.dispatch(Intent.SECONDARY)  # H1 start
        current["now"] += timedelta(seconds=20)
        holding = engine.snapshot()
        self.assertEqual(holding.secondary_button_label, "Stop Hold")
        self.assertTrue(holding.detail_text.startswith("H1"))
        self.assertTrue(engine.state.ui_log[-1].startswith("H1 start "))

        engine.dispatch(Intent.SECONDARY)  # H1 end
        after = engine.snapshot()
        self.assertEqual(after.secondary_button_label, "Hold")
        self.assertEqual(after.detail_text, "")
        self.assertTrue(engine.state.ui_log[-1].startswith("H1 end "))

    def test_descent_hold_freezes_current_depth_estimate(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS

        current["now"] += timedelta(seconds=15)
        self.assertEqual(engine.snapshot().depth_text, "15 fsw")

        engine.dispatch(Intent.SECONDARY)  # H1 start
        current["now"] += timedelta(seconds=20)
        self.assertEqual(engine.snapshot().depth_text, "15 fsw")

        engine.dispatch(Intent.SECONDARY)  # H1 end
        current["now"] += timedelta(seconds=5)
        self.assertEqual(engine.snapshot().depth_text, "20 fsw")

    def test_descent_shows_estimated_depth_without_depth_input(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS

        current["now"] += timedelta(seconds=18)

        self.assertEqual(engine.snapshot().depth_text, "18 fsw")

    def test_bottom_without_depth_prompts_for_md_before_schedule(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(snap.depth_text, "Max -- fsw")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Input max depth for table/schedule")

    def test_first_o2_confirmation_uses_secondary_at_first_o2_stop(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30

        before = engine.snapshot()
        self.assertEqual(before.status_text, "AT O2 STOP")
        self.assertEqual(before.secondary_button_label, "On O2")

        engine.dispatch(Intent.SECONDARY)
        self.assertEqual(engine.state.dive.oxygen.first_confirmed_at, current["now"])
        self.assertTrue(engine.state.ui_log[-1].startswith("On O2 "))

    def test_first_o2_stop_shows_tsv_until_on_o2(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        current["now"] += timedelta(seconds=20)

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.primary_text, "TSV 06:20.0")
        self.assertEqual(snap.remaining_text, "")

    def test_first_stop_o2_uses_arrival_to_on_o2_for_tsv(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=57)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 30
        current["now"] += timedelta(seconds=20)

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.primary_text, "TSV 00:20.0")
        self.assertEqual(snap.remaining_text, "")

    def test_travel_to_first_o2_stop_keeps_traveling_status(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=57)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(seconds=20)

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "TRAVELING")
        self.assertEqual(snap.status_value_text, "Traveling")

    def test_second_o2_stop_timer_continues_from_prior_o2_departure(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=90)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(minutes=26)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=14)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R4 20

        snap = engine.snapshot()

        self.assertEqual(snap.primary_text, "02:00.0")
        self.assertEqual(snap.remaining_text, "Stop: 93:00 left")

    def test_air_o2_first_stop_summary_advances_to_forty(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.AT_STOP)
        self.assertEqual(engine.state.dive.current_stop_index, 1)
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: 40 fsw for 8m")

    def test_reentering_same_depth_before_travel_action_does_not_surface(self) -> None:
        current = {"now": datetime(2026, 4, 12, 10, 1, 5)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] = datetime(2026, 4, 12, 10, 3, 9)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] = datetime(2026, 4, 12, 11, 23, 16)
        engine.dispatch(Intent.PRIMARY)  # LB

        self.assertEqual(engine.snapshot().summary_text, "Next: 50 fsw for 7m")

        engine.set_depth_text("120")  # mirrors GUI resync before button press
        current["now"] = datetime(2026, 4, 12, 11, 25, 37)
        engine.dispatch(Intent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.AT_STOP)
        self.assertEqual(engine.state.dive.current_stop_index, 1)
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: 40 fsw for 26m")

    def test_first_stop_delay_recomputes_from_live_travel_depth(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB

        original = engine.state.dive.profile
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.SECONDARY)  # delay start
        self.assertEqual(engine.state.dive.active_delay.depth_fsw, 115)

        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.SECONDARY)  # delay end + recompute

        updated = engine.state.dive.profile
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertGreater(updated.table_bottom_time_min, original.table_bottom_time_min)
        self.assertNotEqual(updated.stops, original.stops)
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.before_profile, original)
        self.assertEqual(engine.state.dive.last_delay_recompute.after_profile, updated)
        self.assertTrue(engine.state.ui_log[-1].startswith("Schedule updated (+"))

    def test_between_stop_delay_restarts_remaining_schedule_when_recomputed(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("190")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=37)
        engine.dispatch(Intent.PRIMARY)  # LB
        original = engine.state.dive.profile

        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1 80
        engine.dispatch(Intent.PRIMARY)  # L1 80
        current["now"] += timedelta(seconds=2)
        engine.dispatch(Intent.SECONDARY)  # delay start
        self.assertEqual(engine.state.dive.active_delay.depth_fsw, 79)
        self.assertTrue(engine.state.ui_log[-1].startswith("Delay 1 start "))

        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.SECONDARY)  # delay end + recompute

        updated = engine.state.dive.profile
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertIsNone(engine.state.dive.current_stop_index)
        self.assertGreater(updated.table_bottom_time_min, original.table_bottom_time_min)
        self.assertEqual(updated.stops[0].depth_fsw, 70)
        self.assertTrue(any(line.startswith("Delay 1 end ") for line in engine.state.ui_log))
        self.assertTrue(engine.state.ui_log[-1].startswith("Schedule updated (+"))
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.before_profile, original)
        self.assertEqual(engine.state.dive.last_delay_recompute.after_profile, updated)

    def test_incomplete_air_break_logs_warning(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=30)
        engine.dispatch(Intent.SECONDARY)  # start air break

        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.SECONDARY)  # warn incomplete break

        self.assertTrue(engine.state.ui_log[-1].startswith("Complete break first (03:00)"))

    def test_o2_stop_shows_time_until_air_break_due(self) -> None:
        current = {"now": datetime(2026, 4, 13, 10, 22, 2)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)

        current["now"] = datetime(2026, 4, 13, 10, 22, 2)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] = datetime(2026, 4, 13, 10, 24, 5)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] = datetime(2026, 4, 13, 11, 44, 9)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] = datetime(2026, 4, 13, 11, 47, 20)
        engine.dispatch(Intent.PRIMARY)  # R1
        current["now"] = datetime(2026, 4, 13, 11, 54, 25)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] = datetime(2026, 4, 13, 11, 55, 29)
        engine.dispatch(Intent.PRIMARY)  # R2
        current["now"] = datetime(2026, 4, 13, 12, 21, 37)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] = datetime(2026, 4, 13, 12, 22, 40)
        engine.dispatch(Intent.PRIMARY)  # R3
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] = datetime(2026, 4, 13, 12, 36, 59)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] = datetime(2026, 4, 13, 12, 38, 2)
        engine.dispatch(Intent.PRIMARY)  # R4

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.depth_text, "20 fsw")
        self.assertEqual(snap.summary_text, "Next: Air break in 14:38")

    def test_final_twenty_stop_with_thirty_five_minutes_or_less_remaining_requires_no_air_break(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=87)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(minutes=26)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=14)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R4 20
        current["now"] += timedelta(minutes=45)

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.remaining_text, "Stop: 33:00 left")
        self.assertEqual(snap.summary_text, "Next: Surface")
        self.assertEqual(snap.secondary_button_label, "")
        self.assertFalse(snap.secondary_button_enabled)

    def test_first_o2_stop_timer_anchors_to_on_o2_confirmation(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30

        current["now"] += timedelta(seconds=45)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(seconds=20)

        snap = engine.snapshot()
        self.assertEqual(snap.primary_text, "00:20.0")

    def test_active_air_break_uses_summary_for_return_and_clears_detail(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=30)
        engine.dispatch(Intent.SECONDARY)  # start air break
        current["now"] += timedelta(minutes=2)

        snap = engine.snapshot()
        self.assertEqual(snap.primary_text, "02:00.0")
        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.remaining_text, "Air Break: 03:00 left")
        self.assertEqual(snap.summary_text, "Next: O2 for 00:00")
        self.assertEqual(snap.detail_text, "")

    def test_o2_stop_prefers_next_stop_over_future_air_break_when_next_stop_exists(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=5)

        snap = engine.snapshot()

        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.remaining_text, "Stop: 07:00 left")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40m")

    def test_o2_stop_with_next_stop_never_shows_future_air_break_summary(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=11)

        snap = engine.snapshot()

        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40m")
        self.assertFalse(snap.summary_text.startswith("Next: Air break in"))

    def test_test_time_label_and_depth_required_before_leaving_bottom(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.dispatch(Intent.MODE)
        ready = engine.snapshot()
        self.assertEqual(ready.primary_button_label, "Leave Surface")
        self.assertTrue(ready.primary_button_enabled)
        engine.dispatch(Intent.PRIMARY)  # LS allowed without depth
        self.assertEqual(engine.state.dive.phase, DivePhase.DESCENT)
        self.assertTrue(engine.state.ui_log[-1].startswith("LS "))
        engine.dispatch(Intent.PRIMARY)  # RB allowed without depth
        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        before_lb = engine.state.ui_log
        engine.dispatch(Intent.PRIMARY)  # LB blocked without depth
        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(engine.state.ui_log, before_lb)

        engine.advance_test_time(300)
        self.assertEqual(engine.test_time_label(), "Test Time: +05:00")

    def test_reset_clears_all_dive_state_including_depth(self) -> None:
        current = {"now": datetime(2026, 4, 13, 9, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB

        engine.dispatch(Intent.RESET)
        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.READY)
        self.assertEqual(engine.state.dive.depth_input_text, "")
        self.assertIsNone(engine.state.dive.profile)
        self.assertEqual(snap.mode_text, "AIR")
        self.assertEqual(snap.status_text, "READY")
        self.assertEqual(snap.depth_text, "Max -- fsw")
        self.assertEqual(snap.primary_button_label, "Leave Surface")


if __name__ == "__main__":
    unittest.main()
