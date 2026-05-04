from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.core.air_o2_profiles import DecoMode
from dive_stopwatch.core.redesign.air_v2 import (
    AirV2Action,
    AirV2EventKind,
    AirV2Obligation,
    AirV2Phase,
    AirV2TimerKind,
    derive_semantic_view,
    make_initial_state,
    reduce_action,
)


class AirV2ScaffoldTests(unittest.TestCase):
    def test_first_vertical_slice_no_decompression(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="60", depth_fsw=60)

        state = reduce_action(state, AirV2Action.LEAVE_SURFACE, now)
        self.assertEqual(state.phase, AirV2Phase.DESCENT)

        now += timedelta(minutes=2)
        state = reduce_action(state, AirV2Action.REACH_BOTTOM, now)
        self.assertEqual(state.phase, AirV2Phase.BOTTOM)

        now += timedelta(minutes=10)
        state = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)
        self.assertEqual(state.phase, AirV2Phase.TRAVEL_TO_SURFACE)
        self.assertIsNotNone(state.plan)
        self.assertTrue(state.plan.profile.is_no_decompression)

        view = derive_semantic_view(state, now)
        self.assertEqual(view.phase, AirV2Phase.TRAVEL_TO_SURFACE)
        self.assertEqual(view.obligation, AirV2Obligation.REACH_SURFACE)
        self.assertEqual(view.active_timer_kind, AirV2TimerKind.TRAVEL)
        self.assertIsNone(view.next_stop_depth_fsw)

    def test_first_vertical_slice_decompression(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="78", depth_fsw=78)

        state = reduce_action(state, AirV2Action.LEAVE_SURFACE, now)
        now += timedelta(minutes=3)
        state = reduce_action(state, AirV2Action.REACH_BOTTOM, now)
        now += timedelta(minutes=47)
        state = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)

        self.assertEqual(state.phase, AirV2Phase.TRAVEL_TO_FIRST_STOP)
        self.assertIsNotNone(state.plan)
        self.assertFalse(state.plan.profile.is_no_decompression)

        view = derive_semantic_view(state, now)
        self.assertEqual(view.obligation, AirV2Obligation.REACH_STOP)
        self.assertEqual(view.next_stop_depth_fsw, 20)
        self.assertEqual(view.next_stop_duration_min, 17)

    def test_reach_first_stop_exposes_current_stop_semantics(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="78", depth_fsw=78)

        state = reduce_action(state, AirV2Action.LEAVE_SURFACE, now)
        now += timedelta(minutes=3)
        state = reduce_action(state, AirV2Action.REACH_BOTTOM, now)
        now += timedelta(minutes=47)
        state = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)
        now += timedelta(minutes=3)
        state = reduce_action(state, AirV2Action.REACH_STOP, now)

        self.assertEqual(state.phase, AirV2Phase.AT_STOP)
        self.assertIsNotNone(state.plan)
        self.assertEqual(state.plan.current_stop_index, 1)
        self.assertEqual(state.events[-1].kind, AirV2EventKind.REACHED_STOP)

        view = derive_semantic_view(state, now)
        self.assertEqual(view.obligation, AirV2Obligation.LEAVE_STOP)
        self.assertEqual(view.active_timer_kind, AirV2TimerKind.STOP)
        self.assertEqual(view.current_stop_depth_fsw, 20)
        self.assertEqual(view.current_stop_duration_min, 17)
        self.assertEqual(view.current_stop_remaining_sec, 17 * 60)
        self.assertIsNone(view.next_stop_depth_fsw)

    def test_leave_first_stop_returns_to_surface_travel(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="78", depth_fsw=78)

        state = reduce_action(state, AirV2Action.LEAVE_SURFACE, now)
        now += timedelta(minutes=3)
        state = reduce_action(state, AirV2Action.REACH_BOTTOM, now)
        now += timedelta(minutes=47)
        state = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)
        now += timedelta(minutes=3)
        state = reduce_action(state, AirV2Action.REACH_STOP, now)
        now += timedelta(minutes=1)
        state = reduce_action(state, AirV2Action.LEAVE_STOP, now)

        self.assertEqual(state.phase, AirV2Phase.TRAVEL_TO_SURFACE)
        self.assertEqual(state.events[-1].kind, AirV2EventKind.LEFT_STOP)

        view = derive_semantic_view(state, now)
        self.assertEqual(view.obligation, AirV2Obligation.REACH_SURFACE)
        self.assertEqual(view.active_timer_kind, AirV2TimerKind.TRAVEL)

    def test_reach_surface_completes_no_decompression_slice(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="60", depth_fsw=60)

        state = reduce_action(state, AirV2Action.LEAVE_SURFACE, now)
        now += timedelta(minutes=2)
        state = reduce_action(state, AirV2Action.REACH_BOTTOM, now)
        now += timedelta(minutes=10)
        state = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)
        now += timedelta(minutes=1)
        state = reduce_action(state, AirV2Action.REACH_SURFACE, now)

        self.assertEqual(state.phase, AirV2Phase.COMPLETE)
        self.assertEqual(state.events[-1].kind, AirV2EventKind.REACHED_SURFACE)

    def test_invalid_action_does_not_change_phase(self) -> None:
        now = datetime(2026, 4, 24, 12, 0, 0)
        state = make_initial_state(mode=DecoMode.AIR, depth_text="60", depth_fsw=60)

        updated = reduce_action(state, AirV2Action.LEAVE_BOTTOM, now)

        self.assertEqual(updated.phase, AirV2Phase.READY)
        self.assertEqual(updated.events[-1].kind, AirV2EventKind.INVALID_ACTION)
        self.assertEqual(updated.events[-1].detail, "LEAVE_BOTTOM")


if __name__ == "__main__":
    unittest.main()
