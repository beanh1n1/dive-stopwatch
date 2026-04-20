from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.engine import DivePhase, Engine, Intent
from dive_stopwatch.core.profiles import DecoMode, DelayOutcome


class CoreEngineTests(unittest.TestCase):
    def _reach_final_twenty_departure_point(self, engine: Engine, current: dict[str, datetime]) -> None:
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=37)
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
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 20
        current["now"] += timedelta(minutes=34, seconds=40)
        self.assertEqual(engine.snapshot().summary_text, "Next: Surface")
        engine.dispatch(Intent.PRIMARY)  # L4

    def test_stopwatch_start_stop_and_reset(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])

        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(seconds=12)
        running = engine.snapshot()
        self.assertEqual(running.status_text, "RUNNING")
        self.assertEqual(running.primary_button_label, "Start/Stop")
        self.assertEqual(running.secondary_button_label, "Lap/Split")
        self.assertTrue(running.secondary_button_enabled)

        engine.dispatch(Intent.PRIMARY)
        stopped = engine.snapshot()
        self.assertEqual(stopped.status_text, "STOPPED")
        self.assertTrue(stopped.primary_text.startswith("00:12"))
        self.assertEqual(stopped.primary_button_label, "Start/Stop")
        self.assertEqual(stopped.secondary_button_label, "Lap/Split")
        self.assertFalse(stopped.secondary_button_enabled)

        engine.dispatch(Intent.SECONDARY)
        reset = engine.snapshot()
        self.assertEqual(reset.status_text, "READY")
        self.assertEqual(reset.primary_text, "00:00.0")

    def test_stopwatch_lap_split_and_recall(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])

        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(seconds=12, milliseconds=300)
        engine.dispatch(Intent.SECONDARY)
        current["now"] += timedelta(seconds=8)
        engine.dispatch(Intent.SECONDARY)

        snap = engine.snapshot()
        self.assertEqual(snap.secondary_button_label, "Lap/Split")
        self.assertEqual(snap.depth_text, "Lap 00:08")
        self.assertEqual(snap.depth_timer_text, "Split 00:20")
        self.assertEqual(snap.remaining_text, "Prev Lap 00:12 | Split 00:12")
        self.assertEqual(snap.detail_text, "")
        self.assertEqual(
            engine.recall_lines(),
            (
                "Total   00:20.3",
                "L1   Lap 00:12.3  Split 00:12.3",
                "L2   Lap 00:08.0  Split 00:20.3",
            ),
        )

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

    def test_mode_cycle_preserves_depth_input_but_clears_live_dive_work(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.SECONDARY)  # delay start

        self.assertIsNotNone(engine.state.dive.profile)
        self.assertIsNotNone(engine.state.dive.active_delay)

        engine.dispatch(Intent.MODE)

        self.assertEqual(engine.state.deco_mode, DecoMode.AIR_O2)
        self.assertEqual(engine.state.dive.depth_input_text, "145")
        self.assertEqual(engine.state.dive.phase, DivePhase.READY)
        self.assertIsNone(engine.state.dive.profile)
        self.assertIsNone(engine.state.dive.current_stop_index)
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertIsNone(engine.state.dive.last_delay_recompute)

    def test_first_stop_recompute_persists_updated_profile_through_arrival(self) -> None:
        current = {"now": datetime(2026, 4, 19, 11, 6, 13)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] = datetime(2026, 4, 19, 11, 8, 19)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] = datetime(2026, 4, 19, 12, 8, 29)
        engine.dispatch(Intent.PRIMARY)  # LB

        for timestamp in (
            datetime(2026, 4, 19, 12, 9, 32),
            datetime(2026, 4, 19, 12, 11, 35),
            datetime(2026, 4, 19, 12, 11, 43),
            datetime(2026, 4, 19, 12, 14, 48),
            datetime(2026, 4, 19, 12, 15, 25),
            datetime(2026, 4, 19, 12, 45, 30),
        ):
            current["now"] = timestamp
            engine.dispatch(Intent.SECONDARY)

        updated_travel = engine.snapshot()
        self.assertEqual(updated_travel.summary_text, "Next: 40 fsw for 46 min")

        current["now"] = datetime(2026, 4, 19, 12, 46, 41)
        engine.dispatch(Intent.PRIMARY)  # R1
        at_first_stop = engine.snapshot()
        self.assertEqual(at_first_stop.depth_text, "40 fsw")
        self.assertEqual(at_first_stop.depth_timer_text, "46:00 left")
        self.assertEqual(at_first_stop.remaining_text, "")
        self.assertEqual(at_first_stop.summary_text, "Next: 30 fsw for 38 min")

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
        self.assertEqual(snap.summary_text, "")
        self.assertFalse(snap.primary_button_enabled)
        self.assertFalse(snap.secondary_button_enabled)

    def test_clean_time_counts_down_to_surface_boundary(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("78")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=47)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 20
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L1
        engine.dispatch(Intent.PRIMARY)  # RS

        clean_time = engine.snapshot()
        self.assertEqual(engine.state.dive.phase, DivePhase.SURFACE)
        self.assertEqual(clean_time.status_text, "CLEAN TIME")
        self.assertEqual(clean_time.primary_text, "10:00")
        self.assertEqual(clean_time.depth_text, "80 / 50 M")
        self.assertEqual(clean_time.summary_text, "")

        current["now"] += timedelta(minutes=9, seconds=59)
        countdown = engine.snapshot()
        self.assertEqual(countdown.status_text, "CLEAN TIME")
        self.assertEqual(countdown.primary_text, "00:01")
        self.assertEqual(countdown.depth_text, "80 / 50 M")

        current["now"] += timedelta(seconds=1)
        surface = engine.snapshot()
        self.assertEqual(surface.status_text, "SURFACE")
        self.assertEqual(surface.primary_text, "SURFACE")
        self.assertEqual(surface.depth_text, "80 / 50 M")
        self.assertEqual(surface.summary_text, "")

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
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: Surface")

    def test_bottom_no_decompression_countdown_keeps_default_display_kinds(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2, seconds=20)
        engine.dispatch(Intent.PRIMARY)  # RB

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(snap.status_text, "BOTTOM")
        self.assertEqual(snap.status_value_kind, "default")
        self.assertEqual(snap.depth_timer_text, "12:40 remaining")
        self.assertEqual(snap.depth_timer_kind, "default")
        self.assertEqual(snap.summary_text, "Next: Surface")
        self.assertEqual(snap.summary_value_kind, "default")

    def test_twenty_fsw_or_shallower_shows_no_bottom_time_limit(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("20")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=30)

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.BOTTOM)
        self.assertEqual(snap.depth_text, "20 fsw")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.depth_timer_text, "")
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
        self.assertEqual(at_limit.remaining_text, "")
        self.assertEqual(at_limit.summary_text, "Next: Surface")

        current["now"] += timedelta(seconds=40)
        after_limit = engine.snapshot()
        self.assertEqual(after_limit.remaining_text, "")
        self.assertEqual(after_limit.summary_text, "Next: 20 fsw for 4 min")

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
        self.assertEqual(snap.depth_text, "__ fsw")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.depth_timer_text, "")
        self.assertEqual(snap.summary_text, "Next: Input Max Depth for table/schedule")

    def test_ready_state_shows_no_decompression_preview_after_depth_input_and_clears_on_ls(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.dispatch(Intent.MODE)  # AIR
        engine.set_depth_text("68")

        ready = engine.snapshot()
        self.assertEqual(ready.status_text, "READY")
        self.assertEqual(ready.summary_text, "No-D Limit: 70 / 48 Z")

        engine.dispatch(Intent.PRIMARY)  # LS
        descent = engine.snapshot()
        self.assertEqual(descent.status_text, "DESCENT")
        self.assertEqual(descent.summary_text, "Next: --")

    def test_first_o2_confirmation_uses_secondary_at_first_o2_stop(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)
        current["now"] += timedelta(minutes=37)
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
        current["now"] += timedelta(minutes=37)
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

    def test_first_o2_stop_from_bottom_keeps_traveling_until_r1_then_uses_tsv(self) -> None:
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

        traveling = engine.snapshot()
        self.assertEqual(traveling.status_text, "TRAVELING")
        self.assertEqual(traveling.status_value_text, "Traveling")

        engine.dispatch(Intent.PRIMARY)  # R1 30
        current["now"] += timedelta(seconds=20)

        at_stop = engine.snapshot()
        self.assertEqual(at_stop.status_text, "AT O2 STOP")
        self.assertEqual(at_stop.primary_text, "TSV 00:20.0")
        self.assertEqual(at_stop.secondary_button_label, "On O2")

        engine.dispatch(Intent.SECONDARY)
        on_o2 = engine.snapshot()
        self.assertEqual(on_o2.status_text, "AT O2 STOP")
        self.assertEqual(on_o2.status_value_text, "On O2")
        self.assertIsNotNone(engine.state.dive.oxygen.first_confirmed_at)

    def test_first_o2_stop_from_bottom_shows_planned_stop_obligation_before_on_o2(self) -> None:
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
        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.depth_timer_text, "14:00 left")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 39 min")
        self.assertEqual(snap.secondary_button_label, "On O2")

    def test_first_o2_stop_after_air_stop_shows_travel_then_tsv_acceptance_state(self) -> None:
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

        traveling = engine.snapshot()
        self.assertEqual(traveling.status_text, "TRAVELING")
        self.assertEqual(traveling.status_value_text, "Traveling")
        self.assertEqual(traveling.depth_text, "40 fsw")
        self.assertEqual(traveling.primary_text, "00:00.0")
        self.assertEqual(traveling.summary_text, "Next: 30 fsw for 12 min")

        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30

        at_o2 = engine.snapshot()
        self.assertEqual(at_o2.status_text, "AT O2 STOP")
        self.assertEqual(at_o2.status_value_text, "TSV")
        self.assertEqual(at_o2.primary_text, "TSV 06:00.0")
        self.assertEqual(at_o2.depth_text, "30 fsw")
        self.assertEqual(at_o2.depth_timer_text, "12:00 left")
        self.assertEqual(at_o2.summary_text, "Next: 20 fsw for 40 min")
        self.assertEqual(at_o2.primary_button_label, "Leave Stop")
        self.assertEqual(at_o2.secondary_button_label, "On O2")

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

    def test_leaving_stop_early_is_logged(self) -> None:
        current = {"now": datetime(2026, 4, 19, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB -> 150/45
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50

        at_first_stop = engine.snapshot()
        self.assertEqual(at_first_stop.depth_text, "50 fsw")
        self.assertEqual(at_first_stop.depth_timer_text, "03:00 left")

        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.PRIMARY)  # L1 early

        self.assertTrue(engine.state.ui_log[-2].startswith("L1 "))
        self.assertEqual(engine.state.ui_log[-1], "Left 50 fsw early (02:00 remaining)")

    def test_arriving_at_stop_early_is_logged(self) -> None:
        current = {"now": datetime(2026, 4, 19, 12, 30, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB -> 150/45
        current["now"] += timedelta(minutes=2, seconds=50)
        engine.dispatch(Intent.PRIMARY)  # R1 early by 30s

        self.assertTrue(engine.state.ui_log[-2].startswith("R1 "))
        self.assertEqual(engine.state.ui_log[-1], "Arrived 50 fsw early (00:30 before planned travel time)")

    def test_arriving_at_surface_early_is_logged(self) -> None:
        current = {"now": datetime(2026, 4, 19, 13, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(Intent.PRIMARY)  # LB -> 150/45
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=12)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 20
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=40)
        engine.dispatch(Intent.PRIMARY)  # L4
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L4 (converted air stop)
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # RS early by 20s

        self.assertTrue(engine.state.ui_log[-2].startswith("RS "))
        self.assertEqual(engine.state.ui_log[-1], "Arrived Surface early (00:20 before planned travel time)")

    def test_o2_travel_state_preserves_continuity_between_30_and_20(self) -> None:
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
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=14)
        engine.dispatch(Intent.PRIMARY)  # L3

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "TRAVELING")
        self.assertEqual(snap.status_value_text, "On O2/ Traveling")
        self.assertEqual(snap.primary_text, "00:00.0")
        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.depth_timer_text, "40:00 left")
        self.assertEqual(snap.depth_timer_kind, "o2")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40 min")
        self.assertEqual(snap.summary_value_kind, "o2")
        self.assertEqual(snap.primary_button_label, "Reach Stop")
        self.assertEqual(snap.secondary_button_label, "Delay")

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
        self.assertEqual(snap.remaining_text, "")

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
        self.assertEqual(snap.summary_text, "Next: 40 fsw for 8 min")

    def test_later_air_stop_timer_is_anchored_to_previous_leave_stop(self) -> None:
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
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 40

        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.AT_STOP)
        self.assertEqual(snap.depth_text, "40 fsw")
        self.assertEqual(snap.primary_text, "00:20.0")
        self.assertEqual(snap.depth_timer_text, "07:40 left")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: 30 fsw for 12 min")

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

        self.assertEqual(engine.snapshot().summary_text, "Next: 50 fsw for 7 min")

        engine.set_depth_text("120")  # mirrors GUI resync before button press
        current["now"] = datetime(2026, 4, 12, 11, 25, 37)
        engine.dispatch(Intent.PRIMARY)
        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.AT_STOP)
        self.assertEqual(engine.state.dive.current_stop_index, 1)
        self.assertEqual(snap.depth_text, "50 fsw")
        self.assertEqual(snap.summary_text, "Next: 40 fsw for 26 min")

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

    def test_exact_sixty_second_first_stop_delay_is_ignored_without_schedule_update_log(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("121")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=52)
        engine.dispatch(Intent.PRIMARY)  # LB

        original = engine.state.dive.profile
        self.assertIsNotNone(original)

        current["now"] += timedelta(seconds=100)
        engine.dispatch(Intent.SECONDARY)  # delay start above 50 fsw
        self.assertGreater(engine.state.dive.active_delay.depth_fsw, 50)

        current["now"] += timedelta(seconds=60)
        engine.dispatch(Intent.SECONDARY)  # exact 60s delay end

        updated = engine.state.dive.profile
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertEqual(updated, original)
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertFalse(engine.state.dive.last_delay_recompute.schedule_changed)
        self.assertFalse(any(line.startswith("Schedule updated (+") for line in engine.state.ui_log))
        self.assertTrue(any(line == "Delay <= 1m, schedule unchanged" for line in engine.state.ui_log))

    def test_shallow_first_stop_delay_extends_first_stop_without_table_recompute(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("113")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=52)
        engine.dispatch(Intent.PRIMARY)  # LB

        original = engine.state.dive.profile
        self.assertIsNotNone(original)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in original.stops], [(30, 19), (20, 116)])

        current["now"] += timedelta(seconds=140)
        engine.dispatch(Intent.SECONDARY)  # delay start at <= 50 fsw
        self.assertLessEqual(engine.state.dive.active_delay.depth_fsw, 50)

        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.SECONDARY)  # delay end

        updated = engine.state.dive.profile
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertEqual(updated.table_depth_fsw, original.table_depth_fsw)
        self.assertEqual(updated.table_bottom_time_min, original.table_bottom_time_min)
        self.assertEqual([(stop.depth_fsw, stop.duration_min) for stop in updated.stops], [(30, 23), (20, 116)])
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.ADD_TO_FIRST_STOP)
        self.assertEqual(engine.state.dive.last_delay_recompute.after_profile, updated)
        self.assertTrue(engine.state.ui_log[-1].startswith("First stop extended (+4m)"))

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

    def test_first_stop_delay_freezes_travel_depth_and_remaining_during_fast_forward(self) -> None:
        current = {"now": datetime(2026, 4, 12, 19, 54, 41)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] = datetime(2026, 4, 12, 19, 56, 49)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] = datetime(2026, 4, 12, 20, 13, 0)
        engine.dispatch(Intent.PRIMARY)  # LB

        current["now"] = datetime(2026, 4, 12, 20, 13, 2)
        engine.dispatch(Intent.SECONDARY)  # delay start
        active_delay = engine.snapshot()
        self.assertEqual(active_delay.depth_text, "119 fsw")

        current["now"] = datetime(2026, 4, 12, 20, 15, 15)
        delayed = engine.snapshot()
        self.assertEqual(delayed.depth_text, "119 fsw")

        engine.dispatch(Intent.SECONDARY)  # delay end + recompute
        resumed = engine.snapshot()
        self.assertEqual(resumed.depth_text, "119 fsw")
        self.assertTrue(engine.state.ui_log[-1].startswith("Schedule updated (+3m)"))

        current["now"] += timedelta(seconds=10)
        after_resume = engine.snapshot()
        self.assertEqual(after_resume.depth_text, "114 fsw")

    def test_between_stop_exact_sixty_second_delay_is_ignored_without_schedule_update(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("121")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=57)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1 40

        original = engine.state.dive.profile
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # delay start

        current["now"] += timedelta(seconds=60)
        engine.dispatch(Intent.SECONDARY)  # exact 60s delay end

        snap = engine.snapshot()
        self.assertEqual(engine.state.dive.profile, original)
        self.assertEqual(engine.state.dive.current_stop_index, 1)
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertFalse(engine.state.dive.last_delay_recompute.schedule_changed)
        self.assertEqual(snap.summary_text, "Next: 30 fsw for 28 min")
        self.assertFalse(any(line.startswith("Schedule updated (+") for line in engine.state.ui_log))
        self.assertTrue(any(line == "Delay <= 1m, schedule unchanged" for line in engine.state.ui_log))

    def test_shallow_between_stop_delay_over_one_minute_keeps_schedule_but_logs_actual_delay(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("121")
        engine.dispatch(Intent.MODE)  # AIR
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=57)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1 40

        original = engine.state.dive.profile
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # delay start at <= 50 fsw

        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.SECONDARY)  # delay end

        snap = engine.snapshot()
        self.assertEqual(engine.state.dive.profile, original)
        self.assertEqual(engine.state.dive.current_stop_index, 1)
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.IGNORE_DELAY)
        self.assertEqual(engine.state.dive.last_delay_recompute.delay_min, 2)
        self.assertFalse(engine.state.dive.last_delay_recompute.schedule_changed)
        self.assertEqual(snap.summary_text, "Next: 30 fsw for 28 min")
        self.assertFalse(any(line.startswith("Schedule updated (+") for line in engine.state.ui_log))
        self.assertTrue(any(line == "Delay (+2m) did not change schedule" for line in engine.state.ui_log))

    def test_off_o2_resumes_without_five_minute_break_requirement(self) -> None:
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
        engine.dispatch(Intent.SECONDARY)  # Off O2

        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.SECONDARY)  # Back on O2

        self.assertTrue(engine.state.ui_log[-2].startswith("Off O2 "))
        self.assertTrue(engine.state.ui_log[-1].startswith("Back on O2 "))

    def test_off_o2_state_counts_elapsed_deviation_and_shows_return_prompt(self) -> None:
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
        engine.dispatch(Intent.SECONDARY)  # Off O2

        off_o2_start = engine.snapshot()
        current["now"] += timedelta(minutes=2)
        before_attempt = engine.snapshot()
        engine.dispatch(Intent.SECONDARY)  # Back on O2
        after_attempt = engine.snapshot()

        self.assertEqual(off_o2_start.status_value_text, "Off O2")
        self.assertEqual(off_o2_start.status_value_kind, "off_o2")
        self.assertEqual(off_o2_start.summary_text, "Next: On O2")
        self.assertEqual(off_o2_start.primary_button_label, "Convert to Air")
        self.assertEqual(off_o2_start.secondary_button_label, "On O2")
        self.assertTrue(off_o2_start.secondary_button_enabled)
        self.assertEqual(off_o2_start.primary_text, "00:00.0")
        self.assertEqual(before_attempt.status_value_text, "Off O2")
        self.assertEqual(before_attempt.summary_text, "Next: On O2")
        self.assertEqual(before_attempt.primary_button_label, "Convert to Air")
        self.assertEqual(before_attempt.secondary_button_label, "On O2")
        self.assertTrue(before_attempt.secondary_button_enabled)
        self.assertEqual(before_attempt.primary_text, "02:00.0")
        self.assertEqual(before_attempt.depth_timer_text, off_o2_start.depth_timer_text)
        self.assertEqual(after_attempt.status_value_text, "On O2")
        self.assertEqual(after_attempt.secondary_button_label, "Off O2")

    def test_off_o2_state_uses_default_status_and_return_summary(self) -> None:
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
        engine.dispatch(Intent.SECONDARY)  # Off O2
        current["now"] += timedelta(minutes=2)

        snap = engine.snapshot()

        self.assertEqual(snap.status_value_text, "Off O2")
        self.assertEqual(snap.status_value_kind, "off_o2")
        self.assertEqual(snap.primary_value_kind, "off_o2")
        self.assertEqual(snap.depth_timer_kind, "o2")
        self.assertEqual(snap.summary_value_kind, "o2")

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

    def test_delay_detail_text_is_visible_only_while_delay_is_active(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("190")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=37)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=2)
        engine.dispatch(Intent.SECONDARY)  # delay start

        active_delay = engine.snapshot()
        self.assertTrue(active_delay.detail_text.startswith("D1 ("))
        self.assertTrue(active_delay.summary_text.startswith("Next:"))
        self.assertTrue(engine.state.dive.active_delay is not None)

        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.SECONDARY)  # delay end + recompute
        finished_delay = engine.snapshot()
        self.assertEqual(finished_delay.detail_text, "")
        self.assertTrue(finished_delay.summary_text.startswith("Next:"))
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)

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
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: Surface")
        self.assertEqual(snap.secondary_button_label, "Off O2")
        self.assertTrue(snap.secondary_button_enabled)

    def test_total_continuous_o2_of_thirty_five_minutes_or_less_never_surfaces_air_break(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("170")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=27)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        current["now"] += timedelta(minutes=5)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        engine.dispatch(Intent.SECONDARY)  # On O2

        at_thirty = engine.snapshot()
        self.assertEqual(at_thirty.depth_text, "30 fsw")
        self.assertEqual(at_thirty.summary_text, "Next: 20 fsw for 30 min")
        self.assertEqual(at_thirty.secondary_button_label, "Off O2")
        self.assertTrue(at_thirty.secondary_button_enabled)

        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 20

        at_twenty = engine.snapshot()
        self.assertEqual(at_twenty.depth_text, "20 fsw")
        self.assertEqual(at_twenty.summary_text, "Next: Surface")
        self.assertEqual(at_twenty.secondary_button_label, "Off O2")
        self.assertTrue(at_twenty.secondary_button_enabled)

        current["now"] += timedelta(minutes=26, seconds=21)
        still_no_break = engine.snapshot()
        self.assertEqual(still_no_break.depth_text, "20 fsw")
        self.assertEqual(still_no_break.summary_text, "Next: Surface")
        self.assertEqual(still_no_break.secondary_button_label, "Off O2")
        self.assertTrue(still_no_break.secondary_button_enabled)

    def test_oxygen_delay_during_travel_from_thirty_to_twenty_reduces_twenty_stop(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=37)
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
        current["now"] += timedelta(minutes=7)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=10)
        engine.dispatch(Intent.SECONDARY)  # delay start in O2 travel
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.SECONDARY)  # delay end

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.depth_text, "25 fsw")
        self.assertEqual(after_delay.summary_text, "Next: 20 fsw for 33 min")
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(engine.state.dive.last_delay_recompute.credited_o2_min, 2)
        self.assertEqual(engine.state.dive.last_delay_recompute.air_interruption_min, 0)
        self.assertTrue(engine.state.ui_log[-1].startswith("O2 delay credited (+2m)"))

        current["now"] += timedelta(seconds=10)
        engine.dispatch(Intent.PRIMARY)  # R4 20
        at_twenty = engine.snapshot()
        self.assertEqual(at_twenty.depth_text, "20 fsw")
        self.assertEqual(at_twenty.remaining_text, "")

    def test_oxygen_delay_credit_caps_at_thirty_minutes_and_resets_o2_segment_after_air_interrupt(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("190")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=32)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # R1 70
        current["now"] += timedelta(minutes=4)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 60
        current["now"] += timedelta(minutes=5)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 50
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 40
        current["now"] += timedelta(minutes=8)
        engine.dispatch(Intent.PRIMARY)  # L4
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R5 30
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=13)
        engine.dispatch(Intent.PRIMARY)  # L5
        engine.dispatch(Intent.SECONDARY)  # delay start
        current["now"] += timedelta(minutes=20)
        engine.dispatch(Intent.SECONDARY)  # delay end

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.summary_text, "Next: 20 fsw for 28 min")
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.O2_DELAY_CREDIT)
        self.assertEqual(engine.state.dive.last_delay_recompute.credited_o2_min, 17)
        self.assertEqual(engine.state.dive.last_delay_recompute.air_interruption_min, 3)
        self.assertTrue(any("O2 delay interruption (3m air) ignored for O2 credit" == line for line in engine.state.ui_log))

        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R6 20
        at_twenty = engine.snapshot()
        self.assertEqual(at_twenty.depth_text, "20 fsw")
        self.assertEqual(at_twenty.summary_text, "Next: Surface")
        self.assertEqual(at_twenty.secondary_button_label, "Off O2")
        self.assertTrue(at_twenty.secondary_button_enabled)

    def test_oxygen_surface_departure_delay_after_final_o2_period_shifts_to_air_while_waiting(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        self._reach_final_twenty_departure_point(engine, current)

        current["now"] += timedelta(seconds=10)
        engine.dispatch(Intent.SECONDARY)  # delay start
        current["now"] += timedelta(minutes=1)
        while_delayed = engine.snapshot()
        self.assertEqual(while_delayed.status_text, "TRAVELING")
        self.assertEqual(while_delayed.status_value_text, "Traveling")
        self.assertEqual(while_delayed.primary_value_kind, "default")

    def test_oxygen_surface_departure_delay_logs_air_only_interrupt_and_resets_o2_on_end(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        self._reach_final_twenty_departure_point(engine, current)

        current["now"] += timedelta(seconds=10)
        engine.dispatch(Intent.SECONDARY)  # delay start
        current["now"] += timedelta(minutes=5)
        engine.dispatch(Intent.SECONDARY)  # delay end

        after_delay = engine.snapshot()
        self.assertEqual(after_delay.status_value_text, "On O2/ Traveling")
        self.assertEqual(after_delay.summary_text, "Next: Surface")
        self.assertIsNotNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(engine.state.dive.last_delay_recompute.outcome, DelayOutcome.O2_SURFACE_DELAY)
        self.assertEqual(engine.state.dive.last_delay_recompute.delay_min, 5)
        self.assertEqual(engine.state.dive.last_delay_recompute.credited_o2_min, 0)
        self.assertEqual(engine.state.dive.last_delay_recompute.air_interruption_min, 5)
        self.assertEqual(engine.state.ui_log[-1], "20 fsw O2 departure delay interruption (5m air) ignored")
        self.assertEqual(engine.state.ui_log[-2], "20 fsw departure delay ignored (+5m); 5m on air before surface")
        self.assertEqual(engine.state.dive.oxygen.segment_started_at, current["now"])

    def test_final_twenty_o2_stop_carries_continuous_o2_air_break_timer(self) -> None:
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

        snap = engine.snapshot()
        self.assertEqual(snap.summary_text, "Next: Air break in 14:00")

        current["now"] += timedelta(minutes=14)
        due = engine.snapshot()
        self.assertEqual(due.summary_text, "Next: Air break in 00:00")
        self.assertEqual(due.secondary_button_label, "Off O2")

    def test_exact_thirty_minute_continuous_o2_threshold_becomes_due_at_thirty_fsw(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("190")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=90)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R1 90
        current["now"] += timedelta(minutes=11)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 80
        current["now"] += timedelta(minutes=19)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 70
        current["now"] += timedelta(minutes=20)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 60
        current["now"] += timedelta(minutes=21)
        engine.dispatch(Intent.PRIMARY)  # L4
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R5 50
        current["now"] += timedelta(minutes=28)
        engine.dispatch(Intent.PRIMARY)  # L5
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R6 40
        current["now"] += timedelta(minutes=51)
        engine.dispatch(Intent.PRIMARY)  # L6
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R7 40
        current["now"] += timedelta(minutes=55)
        engine.dispatch(Intent.PRIMARY)  # L7
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R8 30
        engine.dispatch(Intent.SECONDARY)  # On O2

        current["now"] += timedelta(minutes=29, seconds=59)
        before_due = engine.snapshot()
        self.assertEqual(before_due.depth_text, "30 fsw")
        self.assertEqual(before_due.summary_text, "Next: Air break in 00:01")
        self.assertEqual(before_due.secondary_button_label, "Off O2")
        self.assertTrue(before_due.secondary_button_enabled)

        current["now"] += timedelta(seconds=1)
        due = engine.snapshot()
        self.assertEqual(due.depth_text, "30 fsw")
        self.assertEqual(due.summary_text, "Next: Air break in 00:00")
        self.assertEqual(due.secondary_button_label, "Off O2")
        self.assertTrue(due.secondary_button_enabled)

    def test_mixed_stop_anchor_chain_keeps_expected_anchor_semantics(self) -> None:
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

        first_air = engine.snapshot()
        self.assertEqual(first_air.depth_text, "50 fsw")
        self.assertEqual(first_air.primary_text, "00:00.0")
        self.assertEqual(first_air.remaining_text, "")
        self.assertEqual(first_air.summary_text, "Next: 40 fsw for 8 min")

        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R2 40

        later_air = engine.snapshot()
        self.assertEqual(later_air.depth_text, "40 fsw")
        self.assertEqual(later_air.primary_text, "02:00.0")
        self.assertEqual(later_air.remaining_text, "")
        self.assertEqual(later_air.summary_text, "Next: 30 fsw for 12 min")

        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(minutes=6)
        engine.dispatch(Intent.PRIMARY)  # R3 30

        first_o2 = engine.snapshot()
        self.assertEqual(first_o2.depth_text, "30 fsw")
        self.assertEqual(first_o2.status_value_text, "TSV")
        self.assertEqual(first_o2.primary_text, "TSV 06:00.0")
        self.assertEqual(first_o2.summary_text, "Next: 20 fsw for 40 min")

        engine.dispatch(Intent.SECONDARY)  # On O2
        on_o2 = engine.snapshot()
        self.assertEqual(on_o2.primary_text, "00:00.0")
        self.assertEqual(on_o2.remaining_text, "")
        self.assertEqual(on_o2.summary_text, "Next: 20 fsw for 40 min")
        self.assertEqual(on_o2.secondary_button_label, "Off O2")

        current["now"] += timedelta(minutes=14)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(minutes=2)
        engine.dispatch(Intent.PRIMARY)  # R4 20

        next_o2 = engine.snapshot()
        self.assertEqual(next_o2.depth_text, "20 fsw")
        self.assertEqual(next_o2.status_value_text, "On O2")
        self.assertEqual(next_o2.primary_text, "02:00.0")
        self.assertEqual(next_o2.remaining_text, "")
        self.assertEqual(next_o2.summary_text, "Next: Air break in 14:00")

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

    def test_off_o2_uses_summary_for_return_and_clears_detail(self) -> None:
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
        engine.dispatch(Intent.SECONDARY)  # Off O2
        current["now"] += timedelta(minutes=2)

        snap = engine.snapshot()
        self.assertEqual(snap.primary_text, "02:00.0")
        self.assertEqual(snap.depth_text, "30 fsw")
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: On O2")
        self.assertEqual(snap.detail_text, "")
        self.assertEqual(snap.primary_button_label, "Convert to Air")
        self.assertEqual(snap.secondary_button_label, "On O2")
        self.assertTrue(snap.secondary_button_enabled)

    def test_off_o2_time_does_not_reduce_required_o2_obligation(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] += timedelta(minutes=81)
        engine.dispatch(Intent.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.PRIMARY)  # R1 80
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 70
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 60
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L3
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R4 50
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L4
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R5 40
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L5
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R6 30
        engine.dispatch(Intent.SECONDARY)  # On O2

        current["now"] += timedelta(minutes=30)
        before_break = engine.snapshot()
        self.assertEqual(before_break.status_text, "AT O2 STOP")
        self.assertEqual(before_break.status_value_text, "On O2")
        self.assertEqual(before_break.summary_text, "Next: Air break in 00:00")
        self.assertEqual(before_break.secondary_button_label, "Off O2")

        engine.dispatch(Intent.SECONDARY)
        break_start = engine.snapshot()
        self.assertEqual(break_start.status_value_text, "Off O2")
        self.assertEqual(break_start.remaining_text, "")
        self.assertEqual(break_start.summary_text, "Next: On O2")
        self.assertEqual(break_start.primary_text, "00:00.0")
        self.assertEqual(break_start.primary_button_label, "Convert to Air")
        self.assertEqual(break_start.secondary_button_label, "On O2")
        self.assertTrue(break_start.secondary_button_enabled)

    def test_convert_to_air_replaces_remaining_o2_schedule_at_current_stop(self) -> None:
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
        current["now"] += timedelta(minutes=3)
        engine.dispatch(Intent.SECONDARY)  # Off O2

        off_o2 = engine.snapshot()
        self.assertEqual(off_o2.primary_button_label, "Convert to Air")
        self.assertEqual(off_o2.secondary_button_label, "On O2")
        self.assertEqual(off_o2.depth_timer_text, "09:00 left")

        engine.dispatch(Intent.PRIMARY)  # Convert to Air

        converted = engine.snapshot()
        self.assertEqual(converted.status_value_text, "At Stop")
        self.assertEqual(converted.depth_text, "30 fsw")
        self.assertEqual(converted.primary_text, "00:00.0")
        self.assertEqual(converted.depth_timer_text, "18:00 left")
        self.assertEqual(converted.summary_text, "Next: 20 fsw for 142 min")
        self.assertEqual(converted.primary_button_label, "Leave Stop")
        self.assertEqual(converted.secondary_button_label, "")
        self.assertEqual(engine.state.dive.profile.mode, DecoMode.AIR)
        self.assertEqual([(stop.depth_fsw, stop.duration_min, stop.gas) for stop in engine.state.dive.profile.stops], [(50, 3, "air"), (40, 8, "air"), (30, 18, "air"), (20, 142, "air")])
        self.assertTrue(engine.state.ui_log[-2].startswith("Convert to Air "))
        self.assertEqual(engine.state.ui_log[-1], "Converted remaining O2 at 30 fsw to 18 min air 150/45 [50/3,40/8,30/12,20/40] -> 150/45 [50/3,40/8,30/18,20/142]")

    def test_convert_to_air_handles_air_profile_with_shifted_stop_indexes(self) -> None:
        current = {"now": datetime(2026, 4, 19, 21, 9, 28)}
        engine = Engine(now_provider=lambda: current["now"])
        engine.set_depth_text("190")
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.MODE)
        engine.dispatch(Intent.PRIMARY)  # LS
        current["now"] = datetime(2026, 4, 19, 21, 11, 30)
        engine.dispatch(Intent.PRIMARY)  # RB
        current["now"] = datetime(2026, 4, 19, 21, 21, 35)
        engine.dispatch(Intent.PRIMARY)  # LB -> 190/13
        current["now"] = datetime(2026, 4, 19, 21, 21, 38)
        engine.dispatch(Intent.PRIMARY)  # R1 50
        current["now"] = datetime(2026, 4, 19, 21, 22, 40)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] = datetime(2026, 4, 19, 21, 23, 42)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] = datetime(2026, 4, 19, 21, 25, 45)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] = datetime(2026, 4, 19, 21, 26, 47)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        current["now"] = datetime(2026, 4, 19, 21, 26, 48)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] = datetime(2026, 4, 19, 21, 26, 49)
        engine.dispatch(Intent.SECONDARY)  # Off O2

        off_o2 = engine.snapshot()
        self.assertEqual(off_o2.primary_button_label, "Convert to Air")
        self.assertEqual(off_o2.depth_text, "30 fsw")
        self.assertEqual(off_o2.depth_timer_text, "01:59 left")

        engine.dispatch(Intent.PRIMARY)  # Convert to Air

        converted = engine.snapshot()
        self.assertEqual(engine.state.dive.profile.mode, DecoMode.AIR)
        self.assertEqual(engine.state.dive.current_stop_index, 2)
        self.assertEqual(converted.depth_text, "30 fsw")
        self.assertEqual(converted.depth_timer_text, "03:00 left")
        self.assertEqual(converted.summary_text, "Next: 20 fsw for 16 min")

    def test_o2_stop_prefers_next_stop_until_air_break_due_occurs_before_stop_end(self) -> None:
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
        self.assertEqual(snap.remaining_text, "")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40 min")

    def test_o2_stop_with_next_stop_keeps_next_stop_summary_when_break_is_later(self) -> None:
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
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40 min")

    def test_next_row_never_previews_later_action_when_nearer_action_exists(self) -> None:
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
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L1
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R2 40
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # L2
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.PRIMARY)  # R3 30
        current["now"] += timedelta(seconds=20)
        engine.dispatch(Intent.SECONDARY)  # On O2
        current["now"] += timedelta(minutes=1)

        snap = engine.snapshot()

        self.assertEqual(snap.status_text, "AT O2 STOP")
        self.assertEqual(snap.status_value_text, "On O2")
        self.assertEqual(snap.summary_text, "Next: 20 fsw for 40 min")
        self.assertEqual(snap.summary_value_kind, "o2")
        self.assertNotIn("Air break", snap.summary_text)

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
        current["now"] += timedelta(minutes=1)
        engine.dispatch(Intent.SECONDARY)  # delay start

        engine.dispatch(Intent.RESET)
        snap = engine.snapshot()

        self.assertEqual(engine.state.dive.phase, DivePhase.READY)
        self.assertEqual(engine.state.dive.depth_input_text, "")
        self.assertIsNone(engine.state.dive.profile)
        self.assertIsNone(engine.state.dive.active_delay)
        self.assertIsNone(engine.state.dive.last_delay_recompute)
        self.assertEqual(snap.mode_text, "AIR")
        self.assertEqual(snap.status_text, "READY")
        self.assertEqual(snap.depth_text, "Max -- fsw")
        self.assertEqual(snap.primary_button_label, "Leave Surface")


if __name__ == "__main__":
    unittest.main()
