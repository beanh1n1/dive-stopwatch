"""
Mixed Gas engine parity tests — verifies correctness against US Diving Manual Rev 7 rules
and the ENGINE_V2 design documents.

Coverage areas:
  - Later stop timer anchored at leave-prior time (T_L1), not arrival (T_R2)
  - First stop timer anchored at arrival time (T_R1)
  - 50/50 stop: stop_timer at T_L1 (obligation), shift_timer at T_confirm (display)
  - 30 fsw O2 stop: shift_timer at arrival, stop_timer reset at CONFIRM_ON_O2
  - Air break pauses stop_timer; obligation preserved through break
  - traveling_on_o2 flag set when traveling between consecutive O2 stops
  - AWAITING_50_50_CONFIRM triggered on LEAVE_BOTTOM when depth > 90, no 90 stop
  - Sub-16% O2 bottom mix requires air descent to 20 fsw
  - Sub-16% bottom timer anchor: grace cap at 5 min from LEAVE_SURFACE
  - Phase and gas_state label chain through a full profile
  - End-to-end 150/10 scenario trace
"""

from __future__ import annotations

from dataclasses import replace
import unittest
from datetime import datetime, timedelta

from dive_stopwatch.engine_v2 import EngineAction, MixedGasEngine
from dive_stopwatch.engine_v2.modes.mixed_gas.plan import build_mixed_gas_plan
from dive_stopwatch.engine_v2.projection.presentation_builder import build_presentation_model
from dive_stopwatch.engine_v2.modes.mixed_gas.state import (
    MixedGasBreathingGas,
    MixedGasPlan,
    MixedGasPhase,
    MixedGasShiftState,
    MixedGasStop,
    MixedGasTimer,
    MixedGasTimerKind,
)
from dive_stopwatch.engine_v2.contracts.timers import TimerState, elapsed as timer_elapsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 1, 1, 12, 0, 0)


def _make_engine(depth_fsw: int = 150, o2_percent: float = 18.4) -> tuple[dict, MixedGasEngine]:
    clock = {"now": T0}
    engine = MixedGasEngine(now_provider=lambda: clock["now"])
    engine.set_depth(raw_text=str(depth_fsw), depth_fsw=depth_fsw)
    engine.set_bottom_mix(raw_text=str(o2_percent), bottom_mix_o2_percent=o2_percent)
    return clock, engine


def _plan_150_10() -> MixedGasPlan:
    plan = build_mixed_gas_plan(depth_fsw=150, bottom_time_min=10, bottom_mix_o2_percent=18.4)
    assert plan is not None
    return plan


def _plan_100_30() -> MixedGasPlan:
    plan = build_mixed_gas_plan(depth_fsw=100, bottom_time_min=30, bottom_mix_o2_percent=18.4)
    assert plan is not None
    return plan


def _plan_70min_o2() -> MixedGasPlan:
    """Single 70-min O2 stop at 30 fsw — long enough that air break fires at 30 min
    with > 35 min remaining (above the Mixed Gas suppression threshold)."""
    return MixedGasPlan(
        input_depth_fsw=90,
        input_bottom_time_min=30,
        table_depth_fsw=90,
        table_bottom_time_min=30,
        stops=(MixedGasStop(index=1, depth_fsw=30, gas="o2", duration_min=70),),
    )


def _reach_first_stop(clock: dict, engine: MixedGasEngine, plan: MixedGasPlan) -> None:
    """Drive engine from READY to AT_STOP at the first decompression stop."""
    engine.set_plan(plan)
    engine.dispatch(EngineAction.LEAVE_SURFACE)
    clock["now"] += timedelta(minutes=10)
    engine.dispatch(EngineAction.REACH_BOTTOM)
    clock["now"] += timedelta(minutes=20)
    engine.dispatch(EngineAction.LEAVE_BOTTOM)
    clock["now"] += timedelta(minutes=5)
    engine.dispatch(EngineAction.REACH_STOP)


# ---------------------------------------------------------------------------
# Rule 0: Reviewed CSV/table pipeline remains authoritative
# ---------------------------------------------------------------------------

class TableBackedPlanAuthorityTests(unittest.TestCase):
    """
    These tests are intentionally table-backed rather than synthetic. They lock:

      - reviewed CSV row selection
      - next-supported depth snapping
      - next-supported bottom-time snapping
      - authoritative shallow stop chain for SURD-selected rows

    This protects against the class of regressions where handcrafted plans still
    pass while the real mixed-gas table pipeline drifts.
    """

    def test_reviewed_150_10_row_matches_expected_stop_chain(self) -> None:
        plan = build_mixed_gas_plan(depth_fsw=150, bottom_time_min=10, bottom_mix_o2_percent=18.4)

        assert plan is not None
        self.assertEqual((plan.table_depth_fsw, plan.table_bottom_time_min), (150, 10))
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops],
            [(50, 10, "50_50"), (40, 10, "50_50"), (30, 7, "o2"), (20, 8, "o2")],
        )

    def test_depth_199_snaps_to_reviewed_200_row(self) -> None:
        plan = build_mixed_gas_plan(depth_fsw=199, bottom_time_min=10, bottom_mix_o2_percent=14.0)

        assert plan is not None
        self.assertEqual((plan.table_depth_fsw, plan.table_bottom_time_min), (200, 10))
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops],
            [(80, 7, "50_50"), (50, 10, "50_50"), (40, 10, "50_50"), (30, 11, "o2"), (20, 17, "o2")],
        )

    def test_bottom_time_11_snaps_to_reviewed_190_20_row(self) -> None:
        plan = build_mixed_gas_plan(depth_fsw=190, bottom_time_min=11, bottom_mix_o2_percent=14.0)

        assert plan is not None
        self.assertEqual((plan.table_depth_fsw, plan.table_bottom_time_min), (190, 20))
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops],
            [(80, 7, "50_50"), (60, 2, "50_50"), (50, 10, "50_50"), (40, 10, "50_50"), (30, 19, "o2"), (20, 34, "o2")],
        )

    def test_selected_surd_table_backed_210_10_collapses_only_from_real_forty_stop(self) -> None:
        plan = build_mixed_gas_plan(depth_fsw=210, bottom_time_min=10, bottom_mix_o2_percent=14.0)
        assert plan is not None

        clock, engine = _make_engine(depth_fsw=210, o2_percent=14.0)
        engine.state = replace(
            engine.state,
            selected_surd=True,
            phase=MixedGasPhase.AT_STOP,
            breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
            plan=plan,
            current_stop_index=3,  # 40 fsw from the reviewed 210/10 row
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=clock["now"])),
        )

        view = engine.view()
        self.assertEqual(view.current_stop_depth_fsw, 40)
        self.assertEqual(view.pending_action_text, "Surface")
        self.assertIsNone(view.next_stop_depth_fsw)
        self.assertIsNone(view.next_stop_duration_min)

    def test_first_stop_delay_recompute_selects_authoritative_220_20_row(self) -> None:
        clock, engine = _make_engine(depth_fsw=220, o2_percent=14.0)

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)
        clock["now"] += timedelta(minutes=4)
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        clock["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.START_DELAY)
        clock["now"] += timedelta(minutes=3, seconds=25)
        engine.dispatch(EngineAction.END_DELAY)

        assert engine.state.plan is not None
        self.assertEqual((engine.state.plan.table_depth_fsw, engine.state.plan.table_bottom_time_min), (220, 20))
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in engine.state.plan.stops],
            [(90, 7, "50_50"), (70, 3, "50_50"), (60, 7, "50_50"), (50, 10, "50_50"), (40, 10, "50_50"), (30, 23, "o2"), (20, 41, "o2")],
        )


# ---------------------------------------------------------------------------
# User-facing next-action contract: Mixed Gas pending action text
# ---------------------------------------------------------------------------

class PendingActionPresentationTests(unittest.TestCase):
    """Lock operator-visible next-action text where the Mixed Gas contract is explicit."""

    def test_ready_summary_shows_leave_surface(self) -> None:
        _, engine = _make_engine(depth_fsw=150, o2_percent=18.4)

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Leave Surface")

    def test_prebottom_shift_summary_shows_confirm_bottom_mix(self) -> None:
        clock, engine = _make_engine(depth_fsw=210, o2_percent=14.0)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Confirm bottom-mix")

    def test_waiting_on_50_50_summary_shows_confirm_50_50(self) -> None:
        clock, engine = _make_engine()
        _reach_first_stop(clock, engine, _plan_150_10())

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Confirm 50/50")

    def test_waiting_on_o2_summary_shows_on_o2(self) -> None:
        clock, engine = _make_engine(depth_fsw=100, o2_percent=18.4)
        _reach_first_stop(clock, engine, _plan_100_30())
        engine.dispatch(EngineAction.CONFIRM_50_50)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: On O2")

    def test_selected_surd_forty_stop_summary_shows_surface(self) -> None:
        plan = build_mixed_gas_plan(depth_fsw=210, bottom_time_min=10, bottom_mix_o2_percent=14.0)
        assert plan is not None
        clock, engine = _make_engine(depth_fsw=210, o2_percent=14.0)
        engine.state = replace(
            engine.state,
            selected_surd=True,
            phase=MixedGasPhase.AT_STOP,
            breathing_gas=MixedGasBreathingGas.HELIOX_50_50,
            plan=plan,
            current_stop_index=3,
            stop_timer=MixedGasTimer(kind=MixedGasTimerKind.STOP, timer=TimerState(started_at=clock["now"])),
        )

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Surface | 1 period at 50")


# ---------------------------------------------------------------------------
# Rule 1: Stop timer anchor — later stops vs first stop
# ---------------------------------------------------------------------------

class LaterStopAnchorTests(unittest.TestCase):
    """
    US Diving Manual / ENGINE_V2 rule: For the *first* decompression stop the
    obligation clock starts at arrival. For every *subsequent* stop the clock
    starts at the moment the diver left the prior stop (T_L{n}), so that travel
    time already counts toward the new obligation.
    """

    def test_first_stop_timer_anchored_at_arrival(self) -> None:
        clock, engine = _make_engine()
        engine.set_plan(_plan_150_10())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        t_arrival = T0 + timedelta(minutes=35)
        clock["now"] = t_arrival
        engine.dispatch(EngineAction.REACH_STOP)

        assert engine.state.stop_timer is not None
        self.assertEqual(engine.state.stop_timer.timer.started_at, t_arrival)

    def test_later_stop_timer_anchored_at_leave_prior_not_arrival(self) -> None:
        clock, engine = _make_engine()
        engine.set_plan(_plan_150_10())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)

        # Leave first stop at T+36, travel 4 min to reach second stop at T+40
        t_l1 = T0 + timedelta(minutes=36)
        t_r2 = T0 + timedelta(minutes=40)
        clock["now"] = t_l1
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] = t_r2
        engine.dispatch(EngineAction.REACH_STOP)

        assert engine.state.stop_timer is not None
        self.assertEqual(
            engine.state.stop_timer.timer.started_at,
            t_l1,
            "Later stop anchor must be T_L1 (leave-prior), not T_R2 (arrival)",
        )

    def test_later_stop_remaining_counts_from_leave_prior(self) -> None:
        clock, engine = _make_engine()
        engine.set_plan(_plan_150_10())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)

        t_l1 = T0 + timedelta(minutes=36)
        t_r2 = T0 + timedelta(minutes=40)
        clock["now"] = t_l1
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] = t_r2
        engine.dispatch(EngineAction.REACH_STOP)

        # 4 min elapsed since T_L1; 10 min obligation → 6 min remaining
        clock["now"] = t_r2  # now = T_R2, elapsed from T_L1 = 4 min
        view = engine.view()
        self.assertAlmostEqual(view.current_stop_remaining_sec, 6 * 60, delta=1.0)


# ---------------------------------------------------------------------------
# Rule 2: 50/50 confirmation — obligation timer vs display timer
# ---------------------------------------------------------------------------

class FiftyFiftyConfirmationTests(unittest.TestCase):
    """
    On REACH_STOP at a 50/50 stop, stop_timer anchors at T_L1 (obligation).
    After CONFIRM_50_50, shift_timer anchors at T_confirm (display/elapsed),
    while stop_timer remains at its original T_L1 anchor.
    """

    def test_confirm_50_50_sets_shift_timer_at_confirmation_time(self) -> None:
        clock, engine = _make_engine()
        _reach_first_stop(clock, engine, _plan_150_10())
        # First stop is index 1 (50 fsw, 50_50): arrives at T+35, shift_state=AWAITING_50_50_CONFIRM

        t_confirm = T0 + timedelta(minutes=37)
        clock["now"] = t_confirm
        engine.dispatch(EngineAction.CONFIRM_50_50)

        assert engine.state.shift_timer is not None
        self.assertEqual(engine.state.shift_timer.timer.started_at, t_confirm)

    def test_confirm_50_50_leaves_stop_timer_anchor_unchanged(self) -> None:
        clock, engine = _make_engine()
        engine.set_plan(_plan_150_10())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        t_arrival = T0 + timedelta(minutes=35)
        clock["now"] = t_arrival
        engine.dispatch(EngineAction.REACH_STOP)
        stop_anchor_before = engine.state.stop_timer.timer.started_at

        clock["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.CONFIRM_50_50)

        self.assertEqual(engine.state.stop_timer.timer.started_at, stop_anchor_before)

    def test_await_50_50_gas_state_name_is_waiting(self) -> None:
        clock, engine = _make_engine()
        _reach_first_stop(clock, engine, _plan_150_10())
        view = engine.view()
        self.assertEqual(view.gas_state_name, "WAITING_ON_50_50")

    def test_after_50_50_confirm_gas_state_name_is_heliox(self) -> None:
        clock, engine = _make_engine()
        _reach_first_stop(clock, engine, _plan_150_10())
        engine.dispatch(EngineAction.CONFIRM_50_50)
        view = engine.view()
        self.assertEqual(view.gas_state_name, "HELIOX_50_50")


# ---------------------------------------------------------------------------
# Rule 3: 30 fsw O2 stop — shift_timer at arrival, stop_timer at confirmation
# ---------------------------------------------------------------------------

class O2StopConfirmationTests(unittest.TestCase):
    """
    On REACH_STOP at the 30 fsw O2 stop:
      - stop_timer is None (no obligation starts yet)
      - shift_timer starts at arrival (TSV timer for crew verification)
    After CONFIRM_ON_O2:
      - stop_timer anchors at the confirmation time
      - shift_timer is cleared
    """

    def _reach_o2_stop(self, clock: dict, engine: MixedGasEngine) -> None:
        """Drive to AT_STOP at the 30 fsw O2 stop."""
        engine.set_plan(_plan_100_30())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        # First stop: 40 fsw 50/50
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        clock["now"] += timedelta(minutes=10)   # complete 40 fsw stop
        engine.dispatch(EngineAction.LEAVE_STOP)

        # 30 fsw O2 stop
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)

    def test_o2_stop_arrival_sets_shift_timer_no_stop_timer(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        t_arrival = T0 + timedelta(minutes=58)
        clock["now"] = T0
        self._reach_o2_stop(clock, engine)

        self.assertIsNone(engine.state.stop_timer, "stop_timer must be None until O2 confirmed")
        self.assertIsNotNone(engine.state.shift_timer, "shift_timer must be set at arrival")

    def test_o2_stop_gas_state_waiting_before_confirm(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        self._reach_o2_stop(clock, engine)
        view = engine.view()
        self.assertEqual(view.gas_state_name, "WAITING_ON_O2")

    def test_confirm_on_o2_sets_stop_timer_at_confirmation_clears_shift_timer(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        self._reach_o2_stop(clock, engine)
        t_confirm = clock["now"] + timedelta(minutes=1)
        clock["now"] = t_confirm
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        assert engine.state.stop_timer is not None
        self.assertEqual(engine.state.stop_timer.timer.started_at, t_confirm)
        self.assertIsNone(engine.state.shift_timer, "shift_timer must be cleared after confirm")

    def test_confirm_on_o2_gas_state_is_on_o2(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        self._reach_o2_stop(clock, engine)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        view = engine.view()
        self.assertEqual(view.gas_state_name, "ON_O2")


# ---------------------------------------------------------------------------
# Rule 4: Air break — pauses stop_timer, obligation preserved through break
# ---------------------------------------------------------------------------

class AirBreakObligationTests(unittest.TestCase):
    """
    TOGGLE_OFF_O2 (air break start) pauses stop_timer so the remaining
    obligation seconds do not advance during the break.  After ending the
    5-minute break, obligation resumes from exactly where it paused.
    """

    def _reach_o2_stop_confirmed(self, clock: dict, engine: MixedGasEngine) -> None:
        """Drive engine to AT_STOP at the 30 fsw O2 stop (70-min obligation, confirmed)."""
        engine.set_plan(_plan_70min_o2())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)   # 30 fsw O2 → AWAITING_O2_CONFIRM
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

    def test_air_break_pauses_stop_timer(self) -> None:
        clock, engine = _make_engine(depth_fsw=90)
        self._reach_o2_stop_confirmed(clock, engine)

        # Advance 30 min — at this point remaining = 40 min > 35 min suppression → break due
        t_break_start = clock["now"] + timedelta(minutes=30)
        clock["now"] = t_break_start
        remaining_before = engine.view().current_stop_remaining_sec
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        # Advance 2 min during air break
        clock["now"] = t_break_start + timedelta(minutes=2)
        remaining_during = engine.view().current_stop_remaining_sec

        self.assertAlmostEqual(
            remaining_before, remaining_during, delta=1.0,
            msg="remaining must not change while stop_timer is paused",
        )

    def test_air_break_resumes_obligation_from_paused_point(self) -> None:
        clock, engine = _make_engine(depth_fsw=90)
        self._reach_o2_stop_confirmed(clock, engine)

        t_break_start = clock["now"] + timedelta(minutes=30)
        clock["now"] = t_break_start
        remaining_before = engine.view().current_stop_remaining_sec
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        # Complete 5-min air break
        t_break_end = t_break_start + timedelta(minutes=5)
        clock["now"] = t_break_end
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        # 1 minute after resuming O2
        clock["now"] = t_break_end + timedelta(minutes=1)
        remaining_after = engine.view().current_stop_remaining_sec

        self.assertAlmostEqual(
            remaining_after, remaining_before - 60, delta=1.0,
            msg="obligation should advance from the paused point after air break ends",
        )

    def test_air_break_gas_state_is_air_break(self) -> None:
        clock, engine = _make_engine(depth_fsw=90)
        self._reach_o2_stop_confirmed(clock, engine)
        clock["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        view = engine.view()
        self.assertEqual(view.gas_state_name, "AIR_BREAK")


# ---------------------------------------------------------------------------
# Rule 5: AWAITING_50_50_CONFIRM on LEAVE_BOTTOM
# ---------------------------------------------------------------------------

class FiftyFiftyOnLeaveBottomTests(unittest.TestCase):
    """
    Rule 9-8.2.1: When leaving a depth > 90 fsw where the plan has no explicit
    90 fsw stop, the diver must confirm 50/50 gas at the first stop.
    LEAVE_BOTTOM must set shift_state=AWAITING_50_50_CONFIRM.
    Conversely, when a 90 fsw stop exists, the engine must NOT pre-set
    AWAITING_50_50_CONFIRM on LEAVE_BOTTOM.
    """

    def test_awaiting_50_50_set_when_no_90_stop_and_deep(self) -> None:
        clock, engine = _make_engine(depth_fsw=150)
        # Plan with no 90 fsw stop — comes from depth > 90
        engine.set_plan(_plan_150_10())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        self.assertEqual(engine.state.shift_state, MixedGasShiftState.AWAITING_50_50_CONFIRM)

    def test_awaiting_50_50_not_set_when_plan_has_90_stop(self) -> None:
        clock, engine = _make_engine(depth_fsw=220)
        # 220 fsw / 18.4% / 20 min has a 90 fsw stop
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        self.assertNotEqual(engine.state.shift_state, MixedGasShiftState.AWAITING_50_50_CONFIRM)

    def test_awaiting_50_50_not_set_for_shallow_no_decompression(self) -> None:
        clock, engine = _make_engine(depth_fsw=60)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        # Should go to TRAVEL_TO_SURFACE, not TRAVEL_TO_FIRST_STOP
        self.assertEqual(engine.state.phase.name, "TRAVEL_TO_SURFACE")


# ---------------------------------------------------------------------------
# Rule 6: Sub-16% O2 bottom mix — air descent to 20 fsw required
# ---------------------------------------------------------------------------

class Sub16BottomMixTests(unittest.TestCase):
    """
    Rule 9-6.4: Bottom mixes below 16% O2 require the diver to breathe air
    to 20 fsw before switching gases.  The engine must use
    DESCENT_TO_20_ON_AIR phase and anchor the bottom timer correctly.
    """

    def test_sub_16_requires_descent_to_20_on_air_phase(self) -> None:
        clock, engine = _make_engine(depth_fsw=200, o2_percent=14.0)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        self.assertEqual(engine.state.phase.name, "DESCENT_TO_20_ON_AIR")

    def test_sub_16_bottom_timer_anchored_at_leave_twenty_within_grace(self) -> None:
        clock, engine = _make_engine(depth_fsw=200, o2_percent=14.0)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        t_ls = T0

        # Reach 20 fsw at T+2 min (within 5-min grace window)
        clock["now"] = t_ls + timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)

        # Leave 20 fsw at T+3 min (still within grace)
        t_leave_twenty = t_ls + timedelta(minutes=3)
        clock["now"] = t_leave_twenty
        engine.dispatch(EngineAction.LEAVE_STOP)

        # Reach bottom
        clock["now"] = t_leave_twenty + timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        # Bottom timer should start at leave_twenty (T+3, within grace)
        assert engine.state.bottom_timer is not None
        self.assertEqual(engine.state.bottom_timer.timer.started_at, t_leave_twenty)

    def test_sub_16_bottom_timer_capped_at_grace_limit_when_delayed_at_20(self) -> None:
        clock, engine = _make_engine(depth_fsw=200, o2_percent=14.0)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        t_ls = T0

        clock["now"] = t_ls + timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_BOTTOM_MIX)

        # Leave 20 fsw 8 min after surface — well past 5-min grace
        t_leave_twenty = t_ls + timedelta(minutes=8)
        clock["now"] = t_leave_twenty
        engine.dispatch(EngineAction.LEAVE_STOP)

        clock["now"] = t_leave_twenty + timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_BOTTOM)

        # Bottom anchor should be capped at T_LS + 5 min (grace limit), not T+8
        assert engine.state.bottom_timer is not None
        expected_anchor = t_ls + timedelta(minutes=5)
        self.assertEqual(engine.state.bottom_timer.timer.started_at, expected_anchor)


# ---------------------------------------------------------------------------
# Rule 7: traveling_on_o2 flag
# ---------------------------------------------------------------------------

class TravelingOnO2Tests(unittest.TestCase):
    """
    traveling_on_o2 must be True while ascending between consecutive O2 stops
    (e.g. 30 fsw → 20 fsw) so the UI can show continued O2 usage during travel.
    It must be False when leaving a non-O2 stop.
    """

    def test_traveling_on_o2_true_between_o2_stops(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        engine.set_plan(_plan_100_30())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        # First stop: 40 fsw 50/50
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.LEAVE_STOP)

        # Travel to 30 fsw and arrive
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        clock["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)

        # Now traveling from 30 fsw O2 stop → 20 fsw O2 stop
        view = engine.view()
        self.assertTrue(view.traveling_on_o2, "traveling_on_o2 must be True between O2 stops")

    def test_traveling_on_o2_false_after_50_50_stop(self) -> None:
        clock, engine = _make_engine(depth_fsw=100)
        engine.set_plan(_plan_100_30())
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        clock["now"] += timedelta(minutes=30)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        # Leave the first (40 fsw 50/50) stop
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        engine.dispatch(EngineAction.CONFIRM_50_50)
        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.LEAVE_STOP)

        # Traveling from 50/50 stop → O2 stop: NOT traveling on O2
        view = engine.view()
        self.assertFalse(view.traveling_on_o2)


# ---------------------------------------------------------------------------
# Rule 8: Phase and gas_state label chain
# ---------------------------------------------------------------------------

class GasStateLabelChainTests(unittest.TestCase):
    """
    End-to-end label sequence through a multi-gas profile verifies the
    gas_state_name transitions follow the correct protocol chain.
    """

    def test_label_chain_through_150_10_profile(self) -> None:
        clock, engine = _make_engine(depth_fsw=150)
        engine.set_plan(_plan_150_10())

        # READY — diver is on the surface breathing air
        self.assertEqual(engine.view().gas_state_name, "AIR")

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        # DESCENT_TO_BOTTOM — switched to bottom mix
        self.assertEqual(engine.view().gas_state_name, "BOTTOM_MIX")

        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        self.assertEqual(engine.view().phase_name, "BOTTOM")

        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.REACH_STOP)
        # AT_STOP at 50 fsw — awaiting 50/50
        self.assertEqual(engine.view().gas_state_name, "WAITING_ON_50_50")

        engine.dispatch(EngineAction.CONFIRM_50_50)
        self.assertEqual(engine.view().gas_state_name, "HELIOX_50_50")

        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        # AT_STOP at 40 fsw — still 50/50
        self.assertEqual(engine.view().gas_state_name, "HELIOX_50_50")

        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        # AT_STOP at 30 fsw — awaiting O2 confirm
        self.assertEqual(engine.view().gas_state_name, "WAITING_ON_O2")

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        self.assertEqual(engine.view().gas_state_name, "ON_O2")

        clock["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        # AT_STOP at 20 fsw — O2 (no waiting this time)
        self.assertEqual(engine.view().gas_state_name, "ON_O2")


# ---------------------------------------------------------------------------
# Rule 9: Full 150/10 scenario trace
# ---------------------------------------------------------------------------

class ScenarioTraceTests(unittest.TestCase):
    """
    End-to-end scenario trace for 150 fsw / 10 min bottom time (18.4% O2 mix).
    Verifies: stop depths, durations, obligation timers, phase sequence, and
    final COMPLETE phase after reaching surface.
    """

    def test_full_150_10_scenario(self) -> None:
        clock, engine = _make_engine(depth_fsw=150)
        plan = _plan_150_10()
        engine.set_plan(plan)

        # ── Descent ──────────────────────────────────────────────────────
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        self.assertEqual(engine.state.phase.name, "DESCENT_TO_BOTTOM")

        clock["now"] += timedelta(minutes=10)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        self.assertEqual(engine.state.phase.name, "BOTTOM")

        clock["now"] += timedelta(minutes=20)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        self.assertEqual(engine.state.phase.name, "TRAVEL_TO_FIRST_STOP")
        self.assertEqual(engine.state.plan.table_depth_fsw, 150)
        self.assertEqual(engine.state.plan.table_bottom_time_min, 10)

        # ── 50 fsw 50/50 (10 min) ────────────────────────────────────────
        t_r1 = clock["now"] + timedelta(minutes=5)
        clock["now"] = t_r1
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 50)
        self.assertEqual(engine.state.shift_state, MixedGasShiftState.AWAITING_50_50_CONFIRM)

        engine.dispatch(EngineAction.CONFIRM_50_50)

        # Obligation: 10 min from T_R1; at T_R1 + 9 min → 60 sec remain
        clock["now"] = t_r1 + timedelta(minutes=9)
        self.assertAlmostEqual(engine.view().current_stop_remaining_sec, 60.0, delta=1.0)

        t_l1 = t_r1 + timedelta(minutes=10)
        clock["now"] = t_l1
        engine.dispatch(EngineAction.LEAVE_STOP)
        self.assertEqual(engine.state.phase.name, "TRAVEL_TO_FIRST_STOP")

        # ── 40 fsw 50/50 (10 min) ────────────────────────────────────────
        t_r2 = t_l1 + timedelta(minutes=3)
        clock["now"] = t_r2
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)
        self.assertEqual(engine.state.stop_timer.timer.started_at, t_l1)

        # At T_R2: 3 min elapsed from T_L1 → 7 min remain
        self.assertAlmostEqual(engine.view().current_stop_remaining_sec, 7 * 60, delta=1.0)

        t_l2 = t_l1 + timedelta(minutes=10)
        clock["now"] = t_l2
        engine.dispatch(EngineAction.LEAVE_STOP)

        # ── 30 fsw O2 (7 min) ────────────────────────────────────────────
        t_r3 = t_l2 + timedelta(minutes=3)
        clock["now"] = t_r3
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 30)
        self.assertEqual(engine.view().gas_state_name, "WAITING_ON_O2")
        self.assertIsNone(engine.state.stop_timer)

        t_c3 = t_r3 + timedelta(seconds=30)
        clock["now"] = t_c3
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        self.assertEqual(engine.state.stop_timer.timer.started_at, t_c3)

        # Obligation: 7 min from T_C3; at T_C3 + 6 min → 60 sec remain
        clock["now"] = t_c3 + timedelta(minutes=6)
        self.assertAlmostEqual(engine.view().current_stop_remaining_sec, 60.0, delta=1.0)

        t_l3 = t_c3 + timedelta(minutes=7)
        clock["now"] = t_l3
        engine.dispatch(EngineAction.LEAVE_STOP)

        # traveling_on_o2 between O2 stops
        self.assertTrue(engine.view().traveling_on_o2)

        # ── 20 fsw O2 (8 min) ────────────────────────────────────────────
        t_r4 = t_l3 + timedelta(minutes=3)
        clock["now"] = t_r4
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 20)
        self.assertEqual(engine.view().gas_state_name, "ON_O2")

        t_l4 = t_l3 + timedelta(minutes=8)
        clock["now"] = t_l4
        engine.dispatch(EngineAction.LEAVE_STOP)
        self.assertEqual(engine.state.phase.name, "TRAVEL_TO_SURFACE")

        # ── Surface ───────────────────────────────────────────────────────
        clock["now"] = t_l4 + timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.state.phase.name, "COMPLETE")
        self.assertEqual(engine.view().gas_state_name, "CLEAN_TIME")


if __name__ == "__main__":
    unittest.main()
