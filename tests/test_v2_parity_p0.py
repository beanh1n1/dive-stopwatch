from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.tables import DecompressionMode, build_basic_air_o2_decompression_profile
from dive_stopwatch.v2.core import EngineV2
from dive_stopwatch.v2.models import IntentV2, ModeV2


def _build_manual_example_controller_to_fifty():
    from dive_stopwatch.v2.dive_controller import DiveController

    controller = DiveController()
    start = datetime(2026, 3, 30, 9, 0, 0)
    controller.start(start)
    controller.start(start + timedelta(minutes=3))
    controller.start(start + timedelta(minutes=42))
    controller.start(start + timedelta(minutes=45, seconds=20))
    return controller, start


def _build_manual_example_controller_to_thirty():
    from dive_stopwatch.v2.dive_controller import DiveController

    controller = DiveController()
    start = datetime(2026, 3, 30, 9, 0, 0)
    controller.start(start)
    controller.start(start + timedelta(minutes=3))
    controller.start(start + timedelta(minutes=42))
    controller.start(start + timedelta(minutes=45, seconds=20))
    controller.lap(start + timedelta(minutes=47, seconds=20))
    controller.start(start + timedelta(minutes=47, seconds=40))
    controller.lap(start + timedelta(minutes=53, seconds=40))
    controller.start(start + timedelta(minutes=54))
    return controller, start


def _build_manual_example_controller_to_forty():
    from dive_stopwatch.v2.dive_controller import DiveController

    controller = DiveController()
    start = datetime(2026, 3, 30, 9, 0, 0)
    controller.start(start)
    controller.start(start + timedelta(minutes=3))
    controller.start(start + timedelta(minutes=42))
    controller.start(start + timedelta(minutes=45, seconds=20))
    controller.lap(start + timedelta(minutes=47, seconds=20))
    controller.start(start + timedelta(minutes=47, seconds=40))
    return controller, start


def _build_v2_engine(controller, now, *, first_o2_confirmed_at=None, oxygen_segment_started_at=None):
    engine = EngineV2(now_provider=lambda: now)
    engine.state.mode = ModeV2.DIVE
    engine.state.deco_mode = DecompressionMode.AIR_O2
    engine.state.depth_text = "145"
    engine.state.dive = controller
    engine.state.first_o2_confirmed_at = first_o2_confirmed_at
    latest_arrival = controller.latest_arrival_event()
    engine.state.first_o2_confirmed_stop_number = latest_arrival.stop_number if latest_arrival is not None else None
    engine.state.oxygen_segment_started_at = oxygen_segment_started_at
    return engine


class V2P0ParityTests(unittest.TestCase):
    def test_phase_sequence_ready_to_clean_time(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("60")
        engine.dispatch(IntentV2.MODE)  # DIVE

        self.assertEqual(engine.snapshot().status.value, "READY")
        engine.dispatch(IntentV2.PRIMARY)  # LS
        self.assertEqual(engine.snapshot().status.value, "DESCENT")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        self.assertEqual(engine.snapshot().status.value, "BOTTOM")

        current["now"] += timedelta(minutes=10)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        self.assertEqual(engine.snapshot().status.value, "TRAVELING")

        current["now"] += timedelta(minutes=1)
        engine.dispatch(IntentV2.PRIMARY)  # RS for no-deco profile
        self.assertEqual(engine.snapshot().status.value, "SURFACE")

    def test_descent_hold_start_end_sequence(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("120")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS

        engine.dispatch(IntentV2.SECONDARY)  # hold start
        current["now"] += timedelta(seconds=20)
        engine.dispatch(IntentV2.SECONDARY)  # hold end

        self.assertEqual(len(engine.state.dive.descent_hold_events), 2)
        self.assertEqual(engine.state.dive.descent_hold_events[0].kind, "start")
        self.assertEqual(engine.state.dive.descent_hold_events[1].kind, "end")
        self.assertEqual(engine.state.dive.descent_hold_events[0].index, 1)
        self.assertEqual(engine.state.dive.descent_hold_events[1].index, 1)

    def test_ascent_stop_arrival_departure_sequence(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB
        current["now"] += timedelta(minutes=3, seconds=20)
        engine.dispatch(IntentV2.PRIMARY)  # R1
        current["now"] += timedelta(minutes=2)
        engine.dispatch(IntentV2.SECONDARY)  # L1

        stop_events = engine.state.dive.ascent_stop_events
        self.assertEqual([event.kind for event in stop_events], ["reach", "leave"])
        self.assertEqual([event.index for event in stop_events], [1, 1])

    def test_ascent_delay_start_end_sequence(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB -> ascent travel

        engine.dispatch(IntentV2.SECONDARY)  # delay start
        current["now"] += timedelta(minutes=1)
        engine.dispatch(IntentV2.SECONDARY)  # delay end

        delay_events = engine.state.dive.ascent_delay_events
        self.assertEqual(len(delay_events), 2)
        self.assertEqual(delay_events[0].kind, "start")
        self.assertEqual(delay_events[1].kind, "end")
        self.assertEqual(delay_events[0].index, 1)
        self.assertEqual(delay_events[1].index, 1)

    def test_anchor_first_air_stop(self) -> None:
        controller, start = _build_manual_example_controller_to_fifty()
        profile = build_basic_air_o2_decompression_profile(145, 39)
        v2 = _build_v2_engine(controller, start + timedelta(minutes=45, seconds=20))

        self.assertEqual(v2._current_stop_anchor(profile), start + timedelta(minutes=45, seconds=20))

    def test_anchor_second_air_stop(self) -> None:
        controller, start = _build_manual_example_controller_to_forty()
        profile = build_basic_air_o2_decompression_profile(145, 39)
        v2 = _build_v2_engine(controller, start + timedelta(minutes=47, seconds=40))

        self.assertEqual(v2._current_stop_anchor(profile), start + timedelta(minutes=47, seconds=20))

    def test_anchor_first_o2_stop(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        profile = build_basic_air_o2_decompression_profile(145, 39)
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        v2 = _build_v2_engine(
            controller,
            start + timedelta(minutes=55),
            first_o2_confirmed_at=confirmed_at,
            oxygen_segment_started_at=confirmed_at,
        )

        self.assertEqual(v2._current_stop_anchor(profile), confirmed_at)

    def test_anchor_first_o2_stop_before_confirmation_is_none(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        profile = build_basic_air_o2_decompression_profile(145, 39)
        v2 = _build_v2_engine(controller, start + timedelta(minutes=54))

        self.assertIsNone(v2._current_stop_anchor(profile))

    def test_awaiting_first_o2_confirmation(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        v2 = _build_v2_engine(controller, start + timedelta(minutes=54))
        profile = build_basic_air_o2_decompression_profile(145, 39)

        self.assertTrue(v2._awaiting_first_o2_confirmation(profile))

    def test_can_start_air_break_at_30min_boundary(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        at_boundary = confirmed_at + timedelta(minutes=30)
        v2 = _build_v2_engine(
            controller,
            at_boundary,
            first_o2_confirmed_at=confirmed_at,
            oxygen_segment_started_at=confirmed_at,
        )
        profile = build_basic_air_o2_decompression_profile(145, 39)

        self.assertTrue(v2._can_start_air_break(profile))

    def test_cannot_start_air_break_before_30min_threshold(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        before_boundary = confirmed_at + timedelta(minutes=29, seconds=59)
        v2 = _build_v2_engine(
            controller,
            before_boundary,
            first_o2_confirmed_at=confirmed_at,
            oxygen_segment_started_at=confirmed_at,
        )
        profile = build_basic_air_o2_decompression_profile(145, 39)

        self.assertFalse(v2._can_start_air_break(profile))

    def test_can_start_air_break_at_20_stop(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        controller.lap(start + timedelta(minutes=61, seconds=30))
        controller.start(start + timedelta(minutes=61, seconds=50))
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        now = start + timedelta(minutes=100)
        v2 = _build_v2_engine(
            controller,
            now,
            first_o2_confirmed_at=confirmed_at,
            oxygen_segment_started_at=confirmed_at,
        )
        profile = build_basic_air_o2_decompression_profile(145, 39)

        self.assertTrue(v2._can_start_air_break(profile))

    def test_anchor_20_fsw_o2_stop(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        controller.lap(start + timedelta(minutes=61, seconds=30))
        controller.start(start + timedelta(minutes=61, seconds=50))
        profile = build_basic_air_o2_decompression_profile(145, 39)
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        v2 = _build_v2_engine(
            controller,
            start + timedelta(minutes=62),
            first_o2_confirmed_at=confirmed_at,
            oxygen_segment_started_at=confirmed_at,
        )

        self.assertEqual(v2._current_stop_anchor(profile), start + timedelta(minutes=61, seconds=30))

    def test_first_o2_confirmation_gate_sets_anchor_and_not_break(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 54, 30)}
        controller, _ = _build_manual_example_controller_to_thirty()
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.state.mode = ModeV2.DIVE
        engine.state.deco_mode = DecompressionMode.AIR_O2
        engine.state.depth_text = "145"
        engine.state.dive = controller

        profile = build_basic_air_o2_decompression_profile(145, 39)
        self.assertTrue(engine._awaiting_first_o2_confirmation(profile))

        engine.dispatch(IntentV2.SECONDARY)  # confirm On O2

        self.assertEqual(engine.state.first_o2_confirmed_at, current["now"])
        self.assertEqual(engine.state.oxygen_segment_started_at, current["now"])
        self.assertIsNone(engine._active_air_break())

    def test_at_o2_stop_detection_for_30_and_20_fsw(self) -> None:
        controller, start = _build_manual_example_controller_to_thirty()
        engine = _build_v2_engine(
            controller,
            start + timedelta(minutes=54, seconds=30),
            first_o2_confirmed_at=start + timedelta(minutes=54, seconds=30),
            oxygen_segment_started_at=start + timedelta(minutes=54, seconds=30),
        )
        profile = build_basic_air_o2_decompression_profile(145, 39)

        self.assertTrue(engine._is_at_o2_stop(profile))

        controller.lap(start + timedelta(minutes=61, seconds=30))
        controller.start(start + timedelta(minutes=61, seconds=50))
        engine.state.first_o2_confirmed_at = start + timedelta(minutes=54, seconds=30)
        engine.state.oxygen_segment_started_at = start + timedelta(minutes=54, seconds=30)

        self.assertTrue(engine._is_at_o2_stop(profile))

    def test_air_break_timer_anchor_and_elapsed(self) -> None:
        current = {"now": datetime(2026, 3, 30, 10, 24, 30)}
        controller, start = _build_manual_example_controller_to_thirty()
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.state.mode = ModeV2.DIVE
        engine.state.deco_mode = DecompressionMode.AIR_O2
        engine.state.depth_text = "145"
        engine.state.dive = controller
        engine.state.first_o2_confirmed_at = confirmed_at
        engine.state.first_o2_confirmed_stop_number = 3
        engine.state.oxygen_segment_started_at = confirmed_at

        engine.dispatch(IntentV2.SECONDARY)  # start break at 30:00
        active_break = engine._active_air_break()
        self.assertIsNotNone(active_break)
        self.assertEqual(active_break.timestamp, current["now"])
        self.assertEqual(engine.snapshot().detail, "Air Break 00:00.0")

        current["now"] += timedelta(minutes=2)
        self.assertEqual(engine.snapshot().detail, "Air Break 02:00.0")

    def test_tsv_anchor_starts_on_leave_40_when_first_o2_is_30(self) -> None:
        current = {"now": datetime(2026, 3, 30, 9, 53, 50)}
        controller, start = _build_manual_example_controller_to_thirty()
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.state.mode = ModeV2.DIVE
        engine.state.deco_mode = DecompressionMode.AIR_O2
        engine.state.depth_text = "145"
        engine.state.dive = controller

        # Leave 40 happens at 09:53:40 in the fixture.
        self.assertEqual(engine.snapshot().primary, "00:10 TSV")

        # Reach 30 at 09:54:00, still waiting for first O2 confirmation.
        current["now"] = start + timedelta(minutes=54)
        self.assertEqual(engine.snapshot().primary, "00:20 TSV")

    def test_next_action_bottom_reports_required_stop_and_time(self) -> None:
        current = {"now": datetime(2026, 4, 11, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)

        summary = engine.snapshot().summary
        self.assertTrue(summary.startswith("Next: 50 fsw for "))
        self.assertTrue(summary.endswith("m"))

    def test_next_action_air_break_precedence_when_due(self) -> None:
        current = {"now": datetime(2026, 3, 30, 10, 24, 30)}
        controller, start = _build_manual_example_controller_to_thirty()
        confirmed_at = start + timedelta(minutes=54, seconds=30)
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.state.mode = ModeV2.DIVE
        engine.state.deco_mode = DecompressionMode.AIR_O2
        engine.state.depth_text = "145"
        engine.state.dive = controller
        engine.state.first_o2_confirmed_at = confirmed_at
        engine.state.first_o2_confirmed_stop_number = 3
        engine.state.oxygen_segment_started_at = confirmed_at

        # At exactly 30:00 oxygen elapsed, break is due and should take precedence over next stop text.
        self.assertEqual(engine.snapshot().summary, "Next: 5 min Air break in 00:00")


if __name__ == "__main__":
    unittest.main()
