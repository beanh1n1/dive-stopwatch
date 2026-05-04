"""
Parity tests for the V2 Air engine against design rules and named scenarios.

Rule IDs reference the US Diving Manual Rev 7 / Change A chapter 9:
  9-6.4   Stop timing semantics
  9-8.2.1 First O2 stop (TSV) anchor branches
  9-8.2.2 Continuous O2 exposure, air breaks, terminal exception
  9-8.1   No-decompression boundary
  9-11.3  First-stop delay corrections
"""
from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2 import AirEngine, EngineAction
from dive_stopwatch.engine_v2.domain.air_o2_profiles import DecoMode, DelayOutcome
from dive_stopwatch.engine_v2.projection.presentation_builder import build_presentation_model


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_engine(mode=DecoMode.AIR_O2, depth=145):
    current = {"now": datetime(2026, 1, 1, 8, 0, 0)}
    engine = AirEngine(mode=mode, now_provider=lambda: current["now"])
    engine.set_depth(raw_text=str(depth), depth_fsw=depth)
    return engine, current


def _reach_bottom(engine, current, *, descent_min=3, bottom_min):
    """LS → descent → RB → wait bottom_min → return"""
    engine.dispatch(EngineAction.LEAVE_SURFACE)
    current["now"] += timedelta(minutes=descent_min)
    engine.dispatch(EngineAction.REACH_BOTTOM)
    current["now"] += timedelta(minutes=bottom_min)


def _wait_until_leaveable(engine, current):
    remaining = engine.view().current_stop_remaining_sec
    if remaining is not None and remaining > 0:
        current["now"] += timedelta(seconds=remaining)


def _reach_twenty_on_o2_for_120_90(engine, current):
    """Traverse 120/90 profile to 20 fsw ON_O2.

    Profile (120 fsw, 90 min in-water): 50/7 air, 40/26 air, 30/14 o2, 20/80 o2
    """
    _reach_bottom(engine, current, descent_min=3, bottom_min=87)  # 90 min in-water
    engine.dispatch(EngineAction.LEAVE_BOTTOM)
    current["now"] += timedelta(minutes=3)
    engine.dispatch(EngineAction.REACH_STOP)  # 50 air
    _wait_until_leaveable(engine, current)
    engine.dispatch(EngineAction.LEAVE_STOP)
    current["now"] += timedelta(minutes=2)
    engine.dispatch(EngineAction.REACH_STOP)  # 40 air
    _wait_until_leaveable(engine, current)
    engine.dispatch(EngineAction.LEAVE_STOP)
    current["now"] += timedelta(minutes=2)
    engine.dispatch(EngineAction.REACH_STOP)  # 30 o2 (WAITING_ON_O2)
    engine.dispatch(EngineAction.CONFIRM_ON_O2)
    current["now"] += timedelta(minutes=14)
    engine.dispatch(EngineAction.LEAVE_STOP)
    current["now"] += timedelta(minutes=2)
    engine.dispatch(EngineAction.REACH_STOP)  # 20 o2 (ON_O2 carries)


# ---------------------------------------------------------------------------
# Rule 9-6.4: Stop timing semantics
# ---------------------------------------------------------------------------

class LaterStopAnchorTests(unittest.TestCase):
    """Rule 9-6.4: Later stop timing begins when diver LEAVES prior stop."""

    def test_first_air_stop_timer_anchored_to_arrival_not_to_lb(self):
        """First stop: carried_elapsed_sec == 0 → remaining == full obligation."""
        engine, current = _make_engine(depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=37)  # 40 min in-water → 150/40
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # 50 fsw, first stop

        # 150/40 profile: 50 fsw for 2 min
        self.assertEqual(engine.state.stop_timer.timer.carried_elapsed_sec, 0.0)
        view = engine.view()
        self.assertEqual(view.current_stop_depth_fsw, 50)
        self.assertEqual(int(view.current_stop_remaining_sec), 2 * 60)

    def test_later_air_stop_carries_travel_elapsed_reducing_remaining_at_arrival(self):
        """Later stop: stop_timer carries travel elapsed, so remaining < full obligation on arrival."""
        engine, current = _make_engine(depth=145)
        # 150/45 profile (42 min in-water): 50/3, 40/8, 30/12, 20/40
        _reach_bottom(engine, current, descent_min=3, bottom_min=39)  # 42 min → 150/45
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # R1 @ 50
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        t_l1 = current["now"]
        current["now"] += timedelta(minutes=2)
        t_r2 = current["now"]
        engine.dispatch(EngineAction.REACH_STOP)  # R2 @ 40

        travel_sec = (t_r2 - t_l1).total_seconds()
        carried = engine.state.stop_timer.timer.carried_elapsed_sec
        # Carried elapsed equals the 2-min travel leg
        self.assertAlmostEqual(carried, travel_sec, delta=2)
        # Remaining at arrival is reduced by the carried travel time (8 min - 2 min travel)
        view = engine.view()
        self.assertAlmostEqual(view.current_stop_remaining_sec, 8 * 60 - travel_sec, delta=2)

    def test_three_stop_anchor_chain_each_later_stop_anchored_to_prior_leave(self):
        """Chain: R1 no-carry, R2 carries L1→R2, R3 carries L2→R3."""
        engine, current = _make_engine(depth=145)
        # 150/45: stops 50/3, 40/8, 30/12, 20/40
        _reach_bottom(engine, current, descent_min=3, bottom_min=39)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # R1 @ 50
        # R1: first stop — carried == 0
        self.assertEqual(engine.state.stop_timer.timer.carried_elapsed_sec, 0.0)

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        t_l1 = current["now"]
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # R2 @ 40
        # R2: carried == L1→R2 travel
        carried_r2 = engine.state.stop_timer.timer.carried_elapsed_sec
        self.assertAlmostEqual(carried_r2, (current["now"] - t_l1).total_seconds(), delta=2)
        self.assertGreater(carried_r2, 0)

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        t_l2 = current["now"]
        current["now"] += timedelta(minutes=2)
        # R3 is O2 stop — tsv_timer used instead of stop_timer
        engine.dispatch(EngineAction.REACH_STOP)  # R3 @ 30
        # tsv anchor verified in separate tests; confirm phase
        self.assertEqual(engine.state.phase.name, "AT_STOP")
        self.assertEqual(engine.state.gas_state.name, "WAITING_ON_O2")


# ---------------------------------------------------------------------------
# Rule 9-8.2.1: TSV anchor branches
# ---------------------------------------------------------------------------

class TSVAnchorTests(unittest.TestCase):
    """Rule 9-8.2.1: TSV timer anchored differently depending on whether a
    prior air stop was served (L40 branch) or first stop is O2 (R30 branch)."""

    def test_tsv_l40_branch_anchored_to_leave_of_last_air_stop(self):
        """L40 branch: tsv_timer.started_at == time of LEAVE_STOP at prior air stop."""
        engine, current = _make_engine(depth=145)
        # 150/45: 50(air), 40(air), 30(o2), 20(o2)
        _reach_bottom(engine, current, descent_min=3, bottom_min=39)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)  # R1 @ 50
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # R2 @ 40
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        t_l2 = current["now"]
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # R3 @ 30 (first O2)

        self.assertEqual(engine.state.gas_state.name, "WAITING_ON_O2")
        tsv_anchor = engine.state.tsv_timer.timer.started_at
        self.assertEqual(tsv_anchor, t_l2)

    def test_tsv_r30_branch_anchored_to_arrival_at_first_o2_stop(self):
        """R30 branch: tsv_timer.started_at == time of REACH_STOP (no prior air stop)."""
        engine, current = _make_engine(depth=100)
        # 100/70: stops 30(o2)/6, 20(o2)/39 — first stop IS 30 fsw O2
        _reach_bottom(engine, current, descent_min=3, bottom_min=67)  # 70 min in-water
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        t_r1 = current["now"]
        engine.dispatch(EngineAction.REACH_STOP)  # R1 @ 30 (first stop is O2)

        self.assertEqual(engine.state.gas_state.name, "WAITING_ON_O2")
        tsv_anchor = engine.state.tsv_timer.timer.started_at
        self.assertEqual(tsv_anchor, t_r1)

    def test_tsv_l40_vs_r30_anchor_differs_by_ascent_time(self):
        """L40 anchor is earlier than R30 anchor by the inter-stop ascent time."""
        # L40 branch: anchor = T_L2 (includes 40→30 ascent in TSV elapsed)
        e_l40, c_l40 = _make_engine(depth=145)
        _reach_bottom(e_l40, c_l40, descent_min=3, bottom_min=39)
        e_l40.dispatch(EngineAction.LEAVE_BOTTOM)
        c_l40["now"] += timedelta(minutes=3)
        e_l40.dispatch(EngineAction.REACH_STOP)   # R1 @ 50
        _wait_until_leaveable(e_l40, c_l40)
        e_l40.dispatch(EngineAction.LEAVE_STOP)
        c_l40["now"] += timedelta(minutes=2)
        e_l40.dispatch(EngineAction.REACH_STOP)   # R2 @ 40
        _wait_until_leaveable(e_l40, c_l40)
        e_l40.dispatch(EngineAction.LEAVE_STOP)
        t_l40_l2 = c_l40["now"]
        c_l40["now"] += timedelta(minutes=2)
        e_l40.dispatch(EngineAction.REACH_STOP)   # R3 @ 30
        t_l40_r3 = c_l40["now"]
        l40_anchor = e_l40.state.tsv_timer.timer.started_at
        l40_elapsed_at_r3 = (t_l40_r3 - l40_anchor).total_seconds()

        # R30 branch: anchor = T_R1 (TSV elapsed at arrival is 0)
        e_r30, c_r30 = _make_engine(depth=100)
        _reach_bottom(e_r30, c_r30, descent_min=3, bottom_min=67)
        e_r30.dispatch(EngineAction.LEAVE_BOTTOM)
        c_r30["now"] += timedelta(minutes=3)
        t_r30_r1 = c_r30["now"]
        e_r30.dispatch(EngineAction.REACH_STOP)   # R1 @ 30 (first stop, R30 branch)
        r30_anchor = e_r30.state.tsv_timer.timer.started_at
        r30_elapsed_at_r1 = (t_r30_r1 - r30_anchor).total_seconds()

        # L40 branch: TSV already has 2 min elapsed at R3 (the ascent time)
        self.assertAlmostEqual(l40_elapsed_at_r3, 120.0, delta=2)
        # R30 branch: TSV elapsed is 0 at R1 (anchored to arrival)
        self.assertAlmostEqual(r30_elapsed_at_r1, 0.0, delta=1)


# ---------------------------------------------------------------------------
# User-facing next-action contract: AIR pending action text
# ---------------------------------------------------------------------------

class PendingActionPresentationTests(unittest.TestCase):
    """Lock operator-visible next-action text where the AIR contract is explicit."""

    def test_bottom_summary_shows_first_required_stop(self) -> None:
        engine, current = _make_engine(depth=120)
        _reach_bottom(engine, current, descent_min=3, bottom_min=87)  # 120/90

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: 50 fsw for 7 min")


# ---------------------------------------------------------------------------
# Rule 9-8.2.2: Air break obligation preservation
# ---------------------------------------------------------------------------

class AirBreakObligationTests(unittest.TestCase):
    """Rule 9-8.2.2: Air-break time does NOT reduce the O2 stop obligation."""

    def test_air_break_pauses_stop_timer_obligation_unchanged_during_and_after(self):
        """remaining_sec is identical immediately before, during, and after a 5-min break."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=120)
        _reach_twenty_on_o2_for_120_90(engine, current)

        # Advance to exactly the 30-min continuous O2 mark → break due
        # Continuous from confirm: 14 min at 30 + 2 min travel = 16 min so far.
        # Need 14 more min at 20 to hit 30 min.
        current["now"] += timedelta(minutes=14)
        self.assertIn("AIR_BREAK_DUE", [w.name for w in engine.view().warnings])

        remaining_before = engine.view().current_stop_remaining_sec

        # Start air break
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual(engine.view().gas_state_name, "AIR_BREAK")

        # During break — remaining must not change
        current["now"] += timedelta(minutes=2)
        remaining_during = engine.view().current_stop_remaining_sec
        self.assertAlmostEqual(remaining_during, remaining_before, delta=1)

        # End break (need full 5 min break)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)  # end break after 5 min
        remaining_after = engine.view().current_stop_remaining_sec

        # Immediately after resuming, obligation same as before the break
        self.assertAlmostEqual(remaining_after, remaining_before, delta=1)

    def test_air_break_at_30_fsw_available_when_obligation_exceeds_30_min(self):
        """Break must become available at 30 fsw if remaining O2 obligation > 35 min.

        Scenario: 30 fsw 14 min, then 20 fsw 80 min — staying at 30 fsw for
        30 min triggers the break while future 20 fsw stop still has 80 min.
        """
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=120)
        # 120/90: 50/7/air, 40/26/air, 30/14/o2, 20/80/o2
        _reach_bottom(engine, current, descent_min=3, bottom_min=87)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # 50 air
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 40 air
        current["now"] += timedelta(minutes=26)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 30 o2
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        # At 29:59 continuous — break not yet due
        current["now"] += timedelta(minutes=29, seconds=59)
        self.assertNotIn("AIR_BREAK_DUE", [w.name for w in engine.view().warnings])

        # At exactly 30:00 continuous — break due
        current["now"] += timedelta(seconds=1)
        self.assertIn("AIR_BREAK_DUE", [w.name for w in engine.view().warnings])

        # Still at 30 fsw — TOGGLE_OFF_O2 should transition to AIR_BREAK (not INTERRUPTED)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        view = engine.view()
        self.assertEqual(view.gas_state_name, "AIR_BREAK")
        self.assertEqual(view.current_stop_depth_fsw, 30)

    def test_terminal_35_min_remaining_suppresses_air_break(self):
        """When total remaining O2 ≤ 35 min, no new air break is required (already covered
        by existing test_air_break_due_warning_clears_at_exact_35_min_remaining_boundary,
        but this verifies it from the obligation perspective at 20 fsw)."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=120)
        _reach_twenty_on_o2_for_120_90(engine, current)

        # Advance to where exactly 35 min remains at 20 fsw (no future O2 stops)
        # remaining = 80*60 - elapsed_stop_timer
        # We need remaining == 35*60 == 2100
        # elapsed_stop_timer at arrival = carry (2 min travel) = 120
        # After X more sec: remaining = 4800 - (120 + X) = 2100 → X = 2580 sec = 43 min
        current["now"] += timedelta(seconds=2580)
        view = engine.view()
        self.assertAlmostEqual(view.current_stop_remaining_sec, 35 * 60, delta=2)
        # At exactly 35 min remaining — break should NOT be due
        self.assertNotIn("AIR_BREAK_DUE", [w.name for w in view.warnings])

    def test_air_break_due_one_second_before_35_min_cutoff(self):
        """Break is due when remaining is 35 min + 1 sec (just above the cutoff)."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=120)
        _reach_twenty_on_o2_for_120_90(engine, current)

        # Advance to where 35 min + 1 sec remains
        # elapsed_stop = 120 + X; remaining = 4800 - (120 + X) = 2101 → X = 2579
        current["now"] += timedelta(seconds=2579)
        view = engine.view()
        self.assertAlmostEqual(view.current_stop_remaining_sec, 35 * 60 + 1, delta=2)
        # Continuous O2 = 14(30fsw) + 2(travel) + (2579/60 ≈ 43 min at 20) > 30 min → break due
        self.assertIn("AIR_BREAK_DUE", [w.name for w in view.warnings])


# ---------------------------------------------------------------------------
# Rule 9-11.3: Delay corrections
# ---------------------------------------------------------------------------

class DelayBoundaryTests(unittest.TestCase):
    """Rule 9-11.3: First-stop delay correction branches."""

    def _setup_travel_to_first_stop(self, depth=145, descent_min=3, bottom_min=39):
        """Return engine in TRAVEL_TO_FIRST_STOP phase (145 fsw → 150/45 profile)."""
        engine, current = _make_engine(depth=depth)
        _reach_bottom(engine, current, descent_min=descent_min, bottom_min=bottom_min)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(seconds=30)
        return engine, current

    def test_first_stop_delay_exactly_60_seconds_is_ignored(self):
        """A delay of exactly 60 s at a deep depth must be ignored (no recompute)."""
        engine, current = self._setup_travel_to_first_stop()
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=60)
        engine.dispatch(EngineAction.END_DELAY)

        self.assertEqual(engine.state.delay.outcome, DelayOutcome.IGNORE_DELAY)

    def test_first_stop_delay_61_seconds_at_deep_depth_triggers_recompute(self):
        """A delay of 61 s at depth > 50 fsw triggers a schedule recompute."""
        engine, current = self._setup_travel_to_first_stop()
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=61)
        engine.dispatch(EngineAction.END_DELAY)

        self.assertEqual(engine.state.delay.outcome, DelayOutcome.RECOMPUTE)

    def test_first_stop_delay_at_shallow_depth_adds_to_first_stop_only(self):
        """A delay > 1 min at a shallow depth (≤ 50 fsw) adds to first stop, no recompute."""
        engine, current = self._setup_travel_to_first_stop()
        # Advance until display_depth is around 40 fsw (after ~100 fsw ascent from 145)
        # At 30 fsw/min ascent: 145 → 40 fsw takes (105/30)*60 = 210 sec
        current["now"] += timedelta(seconds=210)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=90)
        engine.dispatch(EngineAction.END_DELAY)

        # Depth at delay was ≤ 50 fsw → ADD_TO_FIRST_STOP
        self.assertEqual(engine.state.delay.outcome, DelayOutcome.ADD_TO_FIRST_STOP)

    def test_delay_boundary_exactly_1_minute_between_stops_is_ignored(self):
        """Between-stop delay of exactly 1 min (60 s) is always ignored."""
        engine, current = _make_engine(depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=39)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # R1 @ 50 air
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)   # L1
        current["now"] += timedelta(seconds=10)
        engine.dispatch(EngineAction.START_DELAY)
        current["now"] += timedelta(seconds=60)
        engine.dispatch(EngineAction.END_DELAY)

        self.assertEqual(engine.state.delay.outcome, DelayOutcome.IGNORE_DELAY)


# ---------------------------------------------------------------------------
# Rule 9-8.1: No-decompression boundary crossover
# ---------------------------------------------------------------------------

class NoDCompBoundaryTests(unittest.TestCase):
    """Rule 9-8.1: While at bottom, crossing the no-D limit changes next action
    from Surface to first required decompression stop."""

    def test_no_d_boundary_bottom_next_stop_is_none_before_limit(self):
        """At exactly the NDL, no deco profile is shown yet."""
        engine, current = _make_engine(mode=DecoMode.AIR, depth=78)
        # NDL for 78 fsw (rounds to 80) = 39 min
        # surface_timer starts at LS; elapsed_min ceiling = NDL iff LS elapsed = 39 min exactly
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        # At exactly 39 min from LS: elapsed_min = ceil(39*60 / 60) = 39 ≤ limit=39 → no deco
        current["now"] += timedelta(minutes=36)  # 3+36 = 39 min from LS
        view = engine.view()
        self.assertIsNone(view.bottom_next_stop_depth_fsw)

    def test_no_d_boundary_bottom_next_stop_appears_one_second_after_limit(self):
        """One second past the NDL, first deco stop appears in the bottom preview."""
        engine, current = _make_engine(mode=DecoMode.AIR, depth=78)
        engine.dispatch(EngineAction.LEAVE_SURFACE)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        # At 39 min from LS: still no deco
        current["now"] += timedelta(minutes=36)
        self.assertIsNone(engine.view().bottom_next_stop_depth_fsw)
        # 1 more second: elapsed_min = ceil((39*60+1)/60) = 40 > 39 → deco appears
        current["now"] += timedelta(seconds=1)
        view = engine.view()
        self.assertIsNotNone(view.bottom_next_stop_depth_fsw)
        self.assertEqual(view.bottom_next_stop_depth_fsw, 20)


# ---------------------------------------------------------------------------
# O2 continuity across travel
# ---------------------------------------------------------------------------

class O2ContinuityTravelTests(unittest.TestCase):
    """Rule 9-8.2.2: O2 continuity carries across the 30→20 travel leg."""

    def test_traveling_on_o2_flag_set_between_o2_stops(self):
        """After leaving a 30 fsw O2 stop while ON_O2, traveling_on_o2 is True."""
        engine, current = _make_engine(depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=37)  # 150/40 profile
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # 50 air
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 40 air
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 30 o2
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)   # L3 @ 30

        view = engine.view()
        self.assertTrue(view.traveling_on_o2)
        self.assertEqual(view.gas_state_name, "ON_O2")

    def test_o2_continuity_timer_consumes_20_fsw_obligation_during_travel(self):
        """During 30→20 travel, active_timer.remaining_sec reflects 20 fsw obligation minus elapsed."""
        engine, current = _make_engine(depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=37)  # 150/40
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # 50
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 40
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 30 o2
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)   # L3

        # After 2 min of travel, remaining_sec for 20 fsw = 35*60 - 120
        current["now"] += timedelta(minutes=2)
        view = engine.view()
        self.assertTrue(view.traveling_on_o2)
        self.assertAlmostEqual(view.active_timer.remaining_sec, 35 * 60 - 120, delta=2)


# ---------------------------------------------------------------------------
# Full scenario traces
# ---------------------------------------------------------------------------

class ScenarioTraceTests(unittest.TestCase):
    """End-to-end traces validating key state at each landmark event."""

    def test_scenario_air_80_50_profile_and_stop_structure(self):
        """SCENARIO_air_80_50: 78 fsw / 47 min bottom → table 80/50, single air stop 20/17."""
        engine, current = _make_engine(mode=DecoMode.AIR, depth=78)
        _reach_bottom(engine, current, descent_min=3, bottom_min=47)  # 50 min in-water → 80/50
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        view_lb = engine.view()
        # Table resolved on leave-bottom (bottom_table_* is only set during BOTTOM phase;
        # after leaving, check the plan state and travel-phase view fields directly)
        self.assertEqual(engine.state.plan.profile.table_depth_fsw, 80)
        self.assertEqual(engine.state.plan.profile.table_bottom_time_min, 50)
        self.assertEqual(view_lb.next_stop_depth_fsw, 20)
        self.assertEqual(view_lb.next_stop_duration_min, 17)
        self.assertEqual(view_lb.phase_name, "TRAVEL_TO_FIRST_STOP")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)  # R1 @ 20
        view_r1 = engine.view()
        self.assertEqual(view_r1.phase_name, "AT_STOP")
        self.assertEqual(view_r1.gas_state_name, "AIR")
        self.assertEqual(view_r1.current_stop_depth_fsw, 20)
        self.assertEqual(int(view_r1.current_stop_remaining_sec), 17 * 60)
        self.assertIsNone(view_r1.next_stop_depth_fsw)  # surface next

        current["now"] += timedelta(minutes=17)
        engine.dispatch(EngineAction.LEAVE_STOP)  # L1
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        view_rs = engine.view()
        self.assertEqual(view_rs.phase_name, "COMPLETE")
        self.assertEqual(view_rs.gas_state_name, "CLEAN_TIME")
        self.assertIsNotNone(view_rs.active_timer)
        self.assertEqual(view_rs.active_timer.role.name, "CLEAN_TIME")
        self.assertAlmostEqual(view_rs.active_timer.remaining_sec, 10 * 60, delta=2)

    def test_scenario_air_o2_150_40_full_profile_and_gas_transition_chain(self):
        """SCENARIO_air_o2_150_40: table 150/40, stops 50/2/air, 40/6/air, 30/7/o2, 20/35/o2."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=37)  # 40 min → 150/40
        engine.dispatch(EngineAction.LEAVE_BOTTOM)

        # --- 50 fsw air stop ---
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)
        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 50)
        self.assertEqual(v.gas_state_name, "AIR")
        self.assertEqual(v.next_stop_depth_fsw, 40)

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)

        # --- 40 fsw air stop ---
        engine.dispatch(EngineAction.REACH_STOP)
        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 40)
        self.assertEqual(v.gas_state_name, "AIR")
        self.assertEqual(v.next_stop_depth_fsw, 30)

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)

        # --- 30 fsw o2 stop (TSV waiting) ---
        engine.dispatch(EngineAction.REACH_STOP)
        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 30)
        self.assertEqual(v.gas_state_name, "WAITING_ON_O2")
        self.assertEqual(v.obligation.name, "CONFIRM_ON_O2")
        self.assertEqual(v.next_stop_depth_fsw, 20)

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        v = engine.view()
        self.assertEqual(v.gas_state_name, "ON_O2")
        self.assertEqual(v.current_stop_depth_fsw, 30)

        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)

        # --- 30→20 travel on O2 ---
        v = engine.view()
        self.assertTrue(v.traveling_on_o2)
        self.assertEqual(v.gas_state_name, "ON_O2")

        current["now"] += timedelta(minutes=2)

        # --- 20 fsw o2 stop (continuity carries) ---
        engine.dispatch(EngineAction.REACH_STOP)
        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 20)
        self.assertEqual(v.gas_state_name, "ON_O2")
        # remaining at arrival = 35 min - travel carry (2 min)
        self.assertAlmostEqual(v.current_stop_remaining_sec, 35 * 60 - 120, delta=2)

        current["now"] += timedelta(minutes=33)  # serve remaining ≈ 33 min
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        v = engine.view()
        self.assertEqual(v.phase_name, "COMPLETE")
        self.assertEqual(v.gas_state_name, "CLEAN_TIME")

    def test_scenario_first_o2_stop_from_bottom_r30_profile_no_prior_air_stops(self):
        """SCENARIO_first_o2_stop_from_bottom: 100/70 → stops only 30/6 o2, 20/39 o2."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=100)
        _reach_bottom(engine, current, descent_min=3, bottom_min=67)  # 70 in-water
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # R1 @ 30 (first stop is O2)

        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 30)
        self.assertEqual(v.gas_state_name, "WAITING_ON_O2")
        # TSV anchor == arrival (R30 branch verified in TSVAnchorTests)
        # Next: 20 fsw o2
        self.assertEqual(v.next_stop_depth_fsw, 20)
        self.assertEqual(v.next_stop_gas_name, "o2")

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        v = engine.view()
        self.assertEqual(v.gas_state_name, "ON_O2")
        self.assertEqual(int(v.current_stop_remaining_sec), 6 * 60)


# ---------------------------------------------------------------------------
# Phase and gas_state label completeness
# ---------------------------------------------------------------------------

class PhaseGasStateLabelTests(unittest.TestCase):
    """Verify status-label chain across a full AIR/O2 dive (SCENARIO_air_o2_150_40)."""

    def test_phase_transitions_across_150_40_profile(self):
        """phase_name follows READY→DESCENT→BOTTOM→TRAVEL→AT_STOP→…→COMPLETE."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=145)

        self.assertEqual(engine.view().phase_name, "READY")

        engine.dispatch(EngineAction.LEAVE_SURFACE)
        self.assertEqual(engine.view().phase_name, "DESCENT")

        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_BOTTOM)
        self.assertEqual(engine.view().phase_name, "BOTTOM")

        current["now"] += timedelta(minutes=37)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        self.assertEqual(engine.view().phase_name, "TRAVEL_TO_FIRST_STOP")

        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # 50 air
        self.assertEqual(engine.view().phase_name, "AT_STOP")
        self.assertEqual(engine.view().gas_state_name, "AIR")

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        self.assertEqual(engine.view().phase_name, "TRAVEL_TO_FIRST_STOP")
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 40 air
        self.assertEqual(engine.view().gas_state_name, "AIR")

        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 30 o2 — WAITING_ON_O2
        self.assertEqual(engine.view().gas_state_name, "WAITING_ON_O2")

        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        self.assertEqual(engine.view().gas_state_name, "ON_O2")

        current["now"] += timedelta(minutes=7)
        engine.dispatch(EngineAction.LEAVE_STOP)
        self.assertEqual(engine.view().gas_state_name, "ON_O2")

        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 20 o2
        self.assertEqual(engine.view().gas_state_name, "ON_O2")

        current["now"] += timedelta(minutes=33)
        engine.dispatch(EngineAction.LEAVE_STOP)
        self.assertEqual(engine.view().phase_name, "TRAVEL_TO_SURFACE")

        current["now"] += timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.view().phase_name, "COMPLETE")
        self.assertEqual(engine.view().gas_state_name, "CLEAN_TIME")

    def test_next_stop_always_nearest_obligation_not_future(self):
        """At 40 fsw stop, next_stop shows 30 fsw, not 20 fsw."""
        engine, current = _make_engine(mode=DecoMode.AIR_O2, depth=145)
        _reach_bottom(engine, current, descent_min=3, bottom_min=37)
        engine.dispatch(EngineAction.LEAVE_BOTTOM)
        current["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.REACH_STOP)   # 50
        _wait_until_leaveable(engine, current)
        engine.dispatch(EngineAction.LEAVE_STOP)
        current["now"] += timedelta(minutes=2)
        engine.dispatch(EngineAction.REACH_STOP)   # 40

        v = engine.view()
        self.assertEqual(v.current_stop_depth_fsw, 40)
        self.assertEqual(v.next_stop_depth_fsw, 30)   # nearest, not 20
        self.assertNotEqual(v.next_stop_depth_fsw, 20)


if __name__ == "__main__":
    unittest.main()
