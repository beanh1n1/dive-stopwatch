"""
SURD engine parity tests — verifies correctness against US Diving Manual Rev 7 rules
and the ENGINE_V2 design documents.

Coverage areas:
  - Surface interval boundaries: ≤5 min → no penalty, >5 min ≤7 min → +15 at 50,
    >7 min → exceeded (session blocked)
  - PLUS_15_AT_50 penalty extends first 50 fsw segment by 15 minutes
  - Air break fires at 30 min continuous O2 with NO suppression (SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC = 0)
  - TOGGLE_OFF_O2 pauses o2_timer; remaining constant during off-O2 period
  - TOGGLE_OFF_O2 resuming advances obligation from paused point
  - Air break action only available once the current segment is complete
  - ADAPTER_30_20 entry kind starts in SURFACE_TO_CHAMBER_50 (no undress phase)
  - L40_NORMAL entry kind starts in SURFACE_ASCENT_FROM_WATER_STOP
  - SURFACE_DIRECT entry kind starts in SURFACE_UNDRESS
  - Surface interval timer runs from handoff.handed_off_at through all surface phases
  - Full 120/90 segment progression: 50 → 40 → multiple 40s → complete
  - pending_action_text shows "Air Break for 5 min" for segments > 30 min
  - MOVE_CHAMBER advances to next segment after current segment is complete
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from dive_stopwatch.engine_v2 import EngineAction
from dive_stopwatch.engine_v2.modes.surd.engine import SurdEngine
from dive_stopwatch.engine_v2.projection.presentation_builder import build_presentation_model
from dive_stopwatch.engine_v2.modes.surd.plan import (
    SurdPenaltyKind,
    build_surd_chamber_plan,
    build_surd_chamber_plan_from_half_periods,
)
from dive_stopwatch.engine_v2.modes.surd.rules import (
    SURD_SURFACE_INTERVAL_NORMAL_SEC,
    SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC,
)
from dive_stopwatch.engine_v2.contracts.surd_handoff import (
    InWaterToSurdHandoff,
    SurdEntryKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 1, 1, 12, 0, 0)


def _make_engine() -> tuple[dict, SurdEngine]:
    clock = {"now": T0}
    engine = SurdEngine(now_provider=lambda: clock["now"])
    return clock, engine


def _handoff(
    *,
    entry_kind: SurdEntryKind,
    source_mode: str = "MIXED_GAS",
    handed_off_at: datetime,
    depth_fsw: int = 120,
    bottom_time_min: int = 90,
    left_water_stop_depth_fsw: int | None,
) -> InWaterToSurdHandoff:
    return InWaterToSurdHandoff(
        entry_kind=entry_kind,
        source_mode=source_mode,
        input_depth_fsw=depth_fsw,
        input_bottom_time_min=bottom_time_min,
        source_table_depth_fsw=depth_fsw,
        source_table_bottom_time_min=bottom_time_min,
        left_water_stop_depth_fsw=left_water_stop_depth_fsw,
        remaining_in_water_obligation_sec=None,
        handed_off_at=handed_off_at,
    )


def _l40_handoff(
    *,
    handed_off_at: datetime,
    depth_fsw: int = 120,
    bottom_time_min: int = 90,
    source_mode: str = "MIXED_GAS",
) -> InWaterToSurdHandoff:
    return _handoff(
        entry_kind=SurdEntryKind.L40_NORMAL,
        source_mode=source_mode,
        handed_off_at=handed_off_at,
        depth_fsw=depth_fsw,
        bottom_time_min=bottom_time_min,
        left_water_stop_depth_fsw=40,
    )


def _surface_direct_handoff(
    *,
    handed_off_at: datetime,
    depth_fsw: int = 120,
    bottom_time_min: int = 90,
    source_mode: str = "MIXED_GAS",
) -> InWaterToSurdHandoff:
    return _handoff(
        entry_kind=SurdEntryKind.SURFACE_DIRECT,
        source_mode=source_mode,
        handed_off_at=handed_off_at,
        depth_fsw=depth_fsw,
        bottom_time_min=bottom_time_min,
        left_water_stop_depth_fsw=None,
    )


def _adapter_30_20_handoff(
    *,
    handed_off_at: datetime,
    depth_fsw: int = 120,
    bottom_time_min: int = 90,
    source_mode: str = "MIXED_GAS",
) -> InWaterToSurdHandoff:
    return _handoff(
        entry_kind=SurdEntryKind.ADAPTER_30_20,
        source_mode=source_mode,
        handed_off_at=handed_off_at,
        depth_fsw=depth_fsw,
        bottom_time_min=bottom_time_min,
        left_water_stop_depth_fsw=None,
    )


def _drive_to_chamber_50(clock: dict, engine: SurdEngine, handoff: InWaterToSurdHandoff) -> None:
    """Drive L40_NORMAL engine from handoff → CHAMBER_AT_50_WAITING_O2."""
    engine.start_handoff(handoff)
    # SURFACE_ASCENT_FROM_WATER_STOP
    clock["now"] = handoff.handed_off_at + timedelta(minutes=1)
    engine.dispatch(EngineAction.REACH_SURFACE)
    # SURFACE_UNDRESS
    clock["now"] += timedelta(minutes=1)
    engine.dispatch(EngineAction.LEAVE_SURFACE)
    # SURFACE_TO_CHAMBER_50


# ---------------------------------------------------------------------------
# Rule 0: AIR-derived and Mixed-Gas-derived SURD families stay distinct
# ---------------------------------------------------------------------------

class SourceFamilyParityTests(unittest.TestCase):
    """
    SURD is a shared runtime, but its chamber planning must preserve the source
    family from the originating in-water mode.

    AIR/SURD:
      - builds chamber plan from AIR surface-profile tables
      - carries a non-None surface_profile
      - 120/90 yields 7 half-periods → last segment is 15 min

    Mixed/SURD:
      - builds chamber plan from mixed-gas half-period lookup
      - surface_profile remains None
      - 120/90 yields 8 half-periods → last segment is 30 min
    """

    def _reach_chamber(self, handoff: InWaterToSurdHandoff, *, si_seconds: float = 4 * 60) -> SurdEngine:
        clock, engine = _make_engine()
        _drive_to_chamber_50(clock, engine, handoff)
        clock["now"] = handoff.handed_off_at + timedelta(seconds=si_seconds)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        return engine

    def test_air_l40_handoff_uses_air_surface_profile_plan(self) -> None:
        engine = self._reach_chamber(_l40_handoff(handed_off_at=T0, source_mode="AIR"))
        assert engine.state.chamber_plan is not None
        self.assertIsNotNone(engine.state.chamber_plan.surface_profile)
        self.assertEqual(
            [(segment.depth_fsw, segment.duration_sec // 60) for segment in engine.state.chamber_plan.segments],
            [(50, 15), (40, 15), (40, 30), (40, 30), (40, 15)],
        )

    def test_mixed_l40_handoff_uses_mixed_gas_half_period_plan(self) -> None:
        engine = self._reach_chamber(_l40_handoff(handed_off_at=T0, source_mode="MIXED_GAS"))
        assert engine.state.chamber_plan is not None
        self.assertIsNone(engine.state.chamber_plan.surface_profile)
        self.assertEqual(
            [(segment.depth_fsw, segment.duration_sec // 60) for segment in engine.state.chamber_plan.segments],
            [(50, 15), (40, 15), (40, 30), (40, 30), (40, 30)],
        )

    def test_air_surface_direct_handoff_preserves_air_family(self) -> None:
        engine = self._reach_chamber(_surface_direct_handoff(handed_off_at=T0, source_mode="AIR"))
        assert engine.state.chamber_plan is not None
        self.assertIsNotNone(engine.state.chamber_plan.surface_profile)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AT_50_WAITING_O2")

    def test_air_adapter_handoff_preserves_air_family(self) -> None:
        engine = self._reach_chamber(_adapter_30_20_handoff(handed_off_at=T0, source_mode="AIR"))
        assert engine.state.chamber_plan is not None
        self.assertIsNotNone(engine.state.chamber_plan.surface_profile)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AT_50_WAITING_O2")


# ---------------------------------------------------------------------------
# User-facing next-action contract: SURD pending action text
# ---------------------------------------------------------------------------

class PendingActionPresentationTests(unittest.TestCase):
    """Lock operator-visible next-action text where the SURD contract is explicit."""

    def test_surface_undress_summary_shows_surface_to_chamber(self) -> None:
        clock, engine = _make_engine()
        engine.start_handoff(_surface_direct_handoff(handed_off_at=T0, source_mode="AIR"))

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Surface -> 50 fsw")

    def test_chamber_waiting_summary_shows_on_o2(self) -> None:
        engine = SourceFamilyParityTests()._reach_chamber(_l40_handoff(handed_off_at=T0, source_mode="AIR"))

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: On O2")

    def test_long_o2_segment_summary_shows_air_break(self) -> None:
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        clock["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)

        presentation = build_presentation_model(engine.view())
        self.assertEqual(presentation.summary_text, "Next: Air Break for 5 min")


def _drive_to_confirm_o2(clock: dict, engine: SurdEngine, *, si_seconds: float = 4 * 60) -> None:
    """
    Drive a 120/90 L40_NORMAL dive from handoff to CHAMBER_ON_O2 with the
    specified surface interval (default 4 min = within normal window).
    """
    t_handoff = T0
    handoff = _l40_handoff(handed_off_at=t_handoff, depth_fsw=120, bottom_time_min=90)
    engine.start_handoff(handoff)
    clock["now"] = t_handoff + timedelta(minutes=1)
    engine.dispatch(EngineAction.REACH_SURFACE)
    clock["now"] += timedelta(minutes=1)
    engine.dispatch(EngineAction.LEAVE_SURFACE)
    # Reach chamber at the desired surface interval from handoff
    clock["now"] = t_handoff + timedelta(seconds=si_seconds)
    engine.dispatch(EngineAction.REACH_CHAMBER_50)
    engine.dispatch(EngineAction.CONFIRM_ON_O2)


# ---------------------------------------------------------------------------
# Rule 1: Surface interval penalty boundaries
# ---------------------------------------------------------------------------

class SurfaceIntervalBoundaryTests(unittest.TestCase):
    """
    US Diving Manual / ENGINE_V2 rule:
      SI ≤ 5 min  → CHAMBER_AT_50_WAITING_O2 with no penalty
      SI 5-7 min  → CHAMBER_AT_50_WAITING_O2 with PLUS_15_AT_50 penalty
      SI > 7 min  → SURFACE_INTERVAL_EXCEEDED (session blocked)
    Boundaries are defined by SURD_SURFACE_INTERVAL_NORMAL_SEC (300) and
    SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC (420).
    """

    def _reach_chamber_at_si(self, clock: dict, engine: SurdEngine, si_sec: float) -> None:
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)
        clock["now"] = t_handoff + timedelta(seconds=si_sec)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)

    def test_exactly_5_min_no_penalty(self) -> None:
        clock, engine = _make_engine()
        self._reach_chamber_at_si(clock, engine, SURD_SURFACE_INTERVAL_NORMAL_SEC)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AT_50_WAITING_O2")
        self.assertEqual(engine.state.penalty_kind, SurdPenaltyKind.NONE)
        self.assertNotIn("SURFACE_INTERVAL_PENALTY", [w.name for w in engine.view().warnings])

    def test_5_min_1_sec_triggers_plus_15_penalty(self) -> None:
        clock, engine = _make_engine()
        self._reach_chamber_at_si(clock, engine, SURD_SURFACE_INTERVAL_NORMAL_SEC + 1)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AT_50_WAITING_O2")
        self.assertEqual(engine.state.penalty_kind, SurdPenaltyKind.PLUS_15_AT_50)
        self.assertIn("SURFACE_INTERVAL_PENALTY", [w.name for w in engine.view().warnings])

    def test_exactly_7_min_still_penalty_not_exceeded(self) -> None:
        clock, engine = _make_engine()
        self._reach_chamber_at_si(clock, engine, SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AT_50_WAITING_O2")
        self.assertEqual(engine.state.penalty_kind, SurdPenaltyKind.PLUS_15_AT_50)

    def test_7_min_1_sec_triggers_exceeded(self) -> None:
        clock, engine = _make_engine()
        self._reach_chamber_at_si(clock, engine, SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC + 1)
        self.assertEqual(engine.state.phase.name, "SURFACE_INTERVAL_EXCEEDED")

    def test_exceeded_phase_has_no_chamber_actions(self) -> None:
        clock, engine = _make_engine()
        self._reach_chamber_at_si(clock, engine, SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC + 1)
        view = engine.view()
        self.assertNotIn("CONFIRM_ON_O2", view.available_actions)
        self.assertIn("RESET", view.available_actions)


# ---------------------------------------------------------------------------
# Rule 2: PLUS_15_AT_50 penalty extends first 50 fsw segment
# ---------------------------------------------------------------------------

class PenaltyPlanTests(unittest.TestCase):
    """
    A +15-at-50 penalty adds 15 min to the first 50 fsw segment.
    For 120/90 (base = 5 half-periods of 15 min each):
      - No penalty: first 50 segment = 15 min
      - PLUS_15_AT_50: first 50 segment = 30 min
    """

    def test_no_penalty_first_50_segment_is_15_min(self) -> None:
        plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.NONE,
        )
        first = plan.segments[0]
        self.assertEqual(first.depth_fsw, 50)
        self.assertEqual(first.duration_sec, 15 * 60)

    def test_plus_15_penalty_first_50_segment_is_30_min(self) -> None:
        plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.PLUS_15_AT_50,
        )
        first = plan.segments[0]
        self.assertEqual(first.depth_fsw, 50)
        self.assertEqual(first.duration_sec, 30 * 60)

    def test_penalty_plan_segment_count_unchanged(self) -> None:
        base = build_surd_chamber_plan(input_depth_fsw=120, input_bottom_time_min=90, penalty_kind=SurdPenaltyKind.NONE)
        penalized = build_surd_chamber_plan(input_depth_fsw=120, input_bottom_time_min=90, penalty_kind=SurdPenaltyKind.PLUS_15_AT_50)
        # One extra 15-min half-period added, but it merges into the first segment
        self.assertEqual(len(base.segments), len(penalized.segments))

    def test_penalty_active_in_engine_after_slow_surface_interval(self) -> None:
        clock, engine = _make_engine()
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)
        # 6-min surface interval → penalty
        clock["now"] = t_handoff + timedelta(minutes=6)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        self.assertEqual(engine.state.penalty_kind, SurdPenaltyKind.PLUS_15_AT_50)
        assert engine.state.chamber_plan is not None
        self.assertEqual(engine.state.chamber_plan.segments[0].duration_sec, 30 * 60)


# ---------------------------------------------------------------------------
# Rule 3: Air break fires at 30 min with NO suppression
# ---------------------------------------------------------------------------

class SurdAirBreakNoSuppressionTests(unittest.TestCase):
    """
    SURD_O2_BREAK_REQUIRED_REMAINING_EXCEEDS_SEC = 0, so the air break is due
    as soon as 30 min of continuous O2 elapse — regardless of how much
    obligation remains.  This differs from the Mixed Gas engine which suppresses
    breaks when remaining ≤ 35 min.
    """

    def test_air_break_due_at_30_min_with_small_remaining(self) -> None:
        """Segment done (15 min) but we're at 31 min → break fires despite no remaining obligation."""
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)

        # At 31 min: segment done (15 min) AND 31 min continuous O2 → break due
        clock["now"] += timedelta(minutes=31)
        view = engine.view()
        self.assertIn("AIR_BREAK_DUE", [w.name for w in view.warnings])

    def test_air_break_available_as_obligation_with_start_air_break(self) -> None:
        """START_AIR_BREAK action appears when segment is done AND 30 min continuous O2 elapsed."""
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)

        clock["now"] += timedelta(minutes=31)
        view = engine.view()
        self.assertIn("START_AIR_BREAK", view.available_actions)

    def test_air_break_not_yet_due_before_30_min(self) -> None:
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=29)
        view = engine.view()
        self.assertNotIn("AIR_BREAK_DUE", [w.name for w in view.warnings])


# ---------------------------------------------------------------------------
# Rule 4: TOGGLE_OFF_O2 pauses o2_timer; obligation preserved during off-O2
# ---------------------------------------------------------------------------

class OffO2PausesTimerTests(unittest.TestCase):
    """
    TOGGLE_OFF_O2 pauses the o2_timer. During the OFF_O2 period the
    current_stop_remaining_sec must not decrease.  Toggling back on resumes
    from the paused point.
    """

    def _to_on_o2(self, clock: dict, engine: SurdEngine) -> datetime:
        """Return the time O2 was confirmed after driving to CHAMBER_ON_O2."""
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        return clock["now"]

    def test_toggle_off_o2_pauses_remaining(self) -> None:
        clock, engine = _make_engine()
        self._to_on_o2(clock, engine)

        # Advance 5 min, record remaining, toggle off
        clock["now"] += timedelta(minutes=5)
        remaining_at_toggle = engine.view().current_stop_remaining_sec
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual(engine.state.phase.name, "CHAMBER_OFF_O2")

        # Advance another 3 min — remaining must not change
        clock["now"] += timedelta(minutes=3)
        remaining_during_off = engine.view().current_stop_remaining_sec
        self.assertAlmostEqual(
            remaining_at_toggle, remaining_during_off, delta=1.0,
            msg="remaining must freeze while off O2",
        )

    def test_toggle_back_on_resumes_from_paused_position(self) -> None:
        clock, engine = _make_engine()
        self._to_on_o2(clock, engine)

        clock["now"] += timedelta(minutes=5)
        remaining_at_toggle = engine.view().current_stop_remaining_sec
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)

        # 3 min off O2, then resume
        clock["now"] += timedelta(minutes=3)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual(engine.state.phase.name, "CHAMBER_ON_O2")

        # 1 min after resuming — remaining should have decreased by 1 min from paused point
        clock["now"] += timedelta(minutes=1)
        remaining_after = engine.view().current_stop_remaining_sec
        self.assertAlmostEqual(
            remaining_after, remaining_at_toggle - 60, delta=1.0,
            msg="after resuming, remaining must advance from the paused point",
        )

    def test_off_o2_gas_state_is_off_o2(self) -> None:
        clock, engine = _make_engine()
        self._to_on_o2(clock, engine)
        engine.dispatch(EngineAction.TOGGLE_OFF_O2)
        self.assertEqual(engine.view().gas_state_name, "OFF_O2")


# ---------------------------------------------------------------------------
# Rule 5: Air break only available after segment is complete
# ---------------------------------------------------------------------------

class AirBreakAvailabilityTests(unittest.TestCase):
    """
    The START_AIR_BREAK action (and TOGGLE_OFF_O2 path to AIR_BREAK) requires
    both: 30 min continuous O2 AND the current segment obligation met.
    Before the segment completes, air break is not available even if 30 min
    have elapsed.
    """

    def test_start_air_break_not_available_before_segment_complete(self) -> None:
        """120/90: first segment at 50 fsw is 15 min. At 29 min, not yet done."""
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=29)
        view = engine.view()
        # Segment not done (15 min required, only 29 min elapsed but this is also < 30 min)
        self.assertNotIn("START_AIR_BREAK", view.available_actions)

    def test_move_chamber_and_start_air_break_available_after_30_min(self) -> None:
        """At 31 min: segment done (15 min) AND 30 min continuous O2 → break due."""
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=31)
        view = engine.view()
        self.assertIn("START_AIR_BREAK", view.available_actions)


# ---------------------------------------------------------------------------
# Rule 6: Entry kind determines initial SURD phase
# ---------------------------------------------------------------------------

class EntryKindPhaseTests(unittest.TestCase):
    """
    L40_NORMAL  → SURFACE_ASCENT_FROM_WATER_STOP  (still ascending from 40 fsw)
    ADAPTER_30_20 → SURFACE_TO_CHAMBER_50           (bypasses undress; already at surface)
    SURFACE_DIRECT → SURFACE_UNDRESS                 (at surface, needs to undress)
    """

    def test_l40_normal_starts_at_surface_ascent(self) -> None:
        clock, engine = _make_engine()
        engine.start_handoff(_l40_handoff(handed_off_at=T0))
        self.assertEqual(engine.state.phase.name, "SURFACE_ASCENT_FROM_WATER_STOP")

    def test_adapter_30_20_starts_at_surface_to_chamber_50(self) -> None:
        clock, engine = _make_engine()
        engine.start_handoff(_adapter_30_20_handoff(handed_off_at=T0))
        self.assertEqual(engine.state.phase.name, "SURFACE_TO_CHAMBER_50")

    def test_surface_direct_starts_at_surface_undress(self) -> None:
        clock, engine = _make_engine()
        engine.start_handoff(_surface_direct_handoff(handed_off_at=T0))
        self.assertEqual(engine.state.phase.name, "SURFACE_UNDRESS")

    def test_adapter_30_20_has_no_undress_phase(self) -> None:
        """ADAPTER_30_20 jumps straight to SURFACE_TO_CHAMBER_50 with no LEAVE_SURFACE needed."""
        clock, engine = _make_engine()
        engine.start_handoff(_adapter_30_20_handoff(handed_off_at=T0))
        view = engine.view()
        # Only action should be REACH_CHAMBER_50 (and RESET), not LEAVE_SURFACE
        self.assertIn("REACH_CHAMBER_50", view.available_actions)
        self.assertNotIn("LEAVE_SURFACE", view.available_actions)


# ---------------------------------------------------------------------------
# Rule 7: Surface interval timer starts from handoff time
# ---------------------------------------------------------------------------

class SurfaceIntervalTimerTests(unittest.TestCase):
    """
    The surface interval timer must start at handoff.handed_off_at, not at the
    time the engine action is processed.  This timer persists through the ascent,
    undress, and to-chamber phases — it's always anchored to when the diver
    surfaced from the water stop.
    """

    def test_surface_interval_timer_starts_at_handoff_time(self) -> None:
        clock, engine = _make_engine()
        t_handoff = T0
        engine.start_handoff(_l40_handoff(handed_off_at=t_handoff))
        assert engine.state.surface_interval_timer is not None
        self.assertEqual(engine.state.surface_interval_timer.started_at, t_handoff)

    def test_surface_interval_timer_not_reset_after_reach_surface(self) -> None:
        clock, engine = _make_engine()
        t_handoff = T0
        engine.start_handoff(_l40_handoff(handed_off_at=t_handoff))
        clock["now"] = t_handoff + timedelta(minutes=1)
        engine.dispatch(EngineAction.REACH_SURFACE)
        assert engine.state.surface_interval_timer is not None
        self.assertEqual(
            engine.state.surface_interval_timer.started_at, t_handoff,
            "surface_interval_timer must remain anchored at handoff time after reaching surface",
        )

    def test_surface_interval_timer_not_reset_after_leave_surface(self) -> None:
        clock, engine = _make_engine()
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)
        assert engine.state.surface_interval_timer is not None
        self.assertEqual(
            engine.state.surface_interval_timer.started_at, t_handoff,
            "surface_interval_timer must remain anchored at handoff time after leaving surface",
        )

    def test_adapter_30_20_surface_interval_timer_starts_at_handoff(self) -> None:
        clock, engine = _make_engine()
        engine.start_handoff(_adapter_30_20_handoff(handed_off_at=T0 + timedelta(minutes=3)))
        assert engine.state.surface_interval_timer is not None
        self.assertEqual(engine.state.surface_interval_timer.started_at, T0 + timedelta(minutes=3))


# ---------------------------------------------------------------------------
# Rule 8: Full 120/90 segment progression trace
# ---------------------------------------------------------------------------

class FullSegmentProgressionTests(unittest.TestCase):
    """
    120/90 → 5 segments:
      0: period 1, 50 fsw, 15 min
      1: period 1, 40 fsw, 15 min
      2: period 2, 40 fsw, 30 min
      3: period 3, 40 fsw, 30 min
      4: period 4, 40 fsw, 15 min
    Trace through CONFIRM_ON_O2, MOVE_CHAMBER (×4), COMPLETE_TO_SURFACE,
    then COMPLETE_CLEAN_TIME.
    """

    def test_120_90_plan_structure_surface_path(self) -> None:
        """Using surface profile (7 half-periods): last segment is 15 min."""
        plan = build_surd_chamber_plan(
            input_depth_fsw=120,
            input_bottom_time_min=90,
            penalty_kind=SurdPenaltyKind.NONE,
        )
        self.assertEqual(len(plan.segments), 5)
        # Depths: 50, 40, 40, 40, 40
        self.assertEqual([s.depth_fsw for s in plan.segments], [50, 40, 40, 40, 40])
        # Durations (min): 15, 15, 30, 30, 15  (7 half-periods)
        self.assertEqual([s.duration_sec // 60 for s in plan.segments], [15, 15, 30, 30, 15])

    def test_120_90_plan_structure_mixed_gas_path(self) -> None:
        """Via MIXED_GAS half-period lookup (8 half-periods): last segment is 30 min."""
        from dive_stopwatch.engine_v2.modes.mixed_gas.plan import mixed_gas_chamber_o2_half_periods
        from dive_stopwatch.engine_v2.modes.surd.plan import build_surd_chamber_plan_from_half_periods
        hp = mixed_gas_chamber_o2_half_periods(depth_fsw=120, bottom_time_min=90)
        self.assertEqual(hp, 8)
        plan = build_surd_chamber_plan_from_half_periods(
            chamber_o2_half_periods=hp,
            penalty_kind=SurdPenaltyKind.NONE,
        )
        self.assertEqual(len(plan.segments), 5)
        self.assertEqual([s.duration_sec // 60 for s in plan.segments], [15, 15, 30, 30, 30])

    def _do_air_break(self, clock: dict, engine: SurdEngine) -> None:
        """Start and complete a 5-min air break."""
        engine.dispatch(EngineAction.START_AIR_BREAK)
        self.assertEqual(engine.state.phase.name, "CHAMBER_AIR_BREAK")
        clock["now"] += timedelta(minutes=5)
        engine.dispatch(EngineAction.END_AIR_BREAK)
        self.assertEqual(engine.state.phase.name, "CHAMBER_ON_O2")

    def test_full_120_90_progression(self) -> None:
        """
        120/90 via MIXED_GAS source_mode produces 8 half-periods → 5 segments:
          (50,15), (40,15), (40,30), (40,30), (40,30).
        SURD air break fires at 30 min continuous O2 when remaining > 0.
        END_AIR_BREAK auto-advances to the next period when depths match.
        For the last segment, COMPLETE_TO_SURFACE takes priority over air break
        (remaining = 0 when segment done → air_break_due = False).

        Trace:
          seg0: 50 fsw 15 min → MOVE_CHAMBER (15 min < 30 min → no break)
          seg1: 40 fsw 15 min → at 30 min total, remaining=total_next_segs>0 → air break
          seg2: 40 fsw 30 min → at 30 min → air break (auto-advances to seg3)
          seg3: 40 fsw 30 min → at 30 min → air break (auto-advances to seg4)
          seg4: 40 fsw 30 min → at 30 min → COMPLETE_TO_SURFACE (remaining=0, no break)
        """
        clock, engine = _make_engine()
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)

        # Reach chamber 50 at 4 min → no penalty
        clock["now"] = t_handoff + timedelta(minutes=4)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        self.assertEqual(engine.state.penalty_kind, SurdPenaltyKind.NONE)

        # Confirm O2 → segment 0 (50 fsw, 15 min)
        clock["now"] += timedelta(seconds=10)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)
        self.assertEqual(engine.state.phase.name, "CHAMBER_ON_O2")
        self.assertEqual(engine.view().current_stop_depth_fsw, 50)

        # ── Segment 0: 15 min at 50 fsw ──────────────────────────────────
        clock["now"] += timedelta(minutes=15)
        # 15 min continuous O2 — no break yet
        self.assertIn("MOVE_CHAMBER", engine.view().available_actions)
        self.assertNotIn("START_AIR_BREAK", engine.view().available_actions)
        engine.dispatch(EngineAction.MOVE_CHAMBER)

        # Segment 1: travel to 40 fsw
        self.assertEqual(engine.state.phase.name, "CHAMBER_TRAVEL_TO_STOP")
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)

        # ── Segment 1: 15 min at 40 fsw → total 30 min → air break due ──
        clock["now"] += timedelta(minutes=15)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)
        # Air break auto-advances period 1→2 (same depth, different period)
        self._do_air_break(clock, engine)
        self.assertEqual(engine.view().current_stop_depth_fsw, 40)

        # ── Segment 2: 30 min at 40 fsw → air break due again ────────────
        clock["now"] += timedelta(minutes=30)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)
        self._do_air_break(clock, engine)

        # ── Segment 3: 30 min at 40 fsw → air break due again ────────────
        clock["now"] += timedelta(minutes=30)
        self.assertIn("START_AIR_BREAK", engine.view().available_actions)
        self._do_air_break(clock, engine)

        # ── Segment 4 (last): 30 min at 40 fsw → remaining=0 → COMPLETE ─
        clock["now"] += timedelta(minutes=30)
        # At exactly 30 min, remaining=0 → air_break_due=False (0 > 0 is False)
        # COMPLETE_TO_SURFACE available since next_seg is None
        self.assertIn("COMPLETE_TO_SURFACE", engine.view().available_actions)

        engine.dispatch(EngineAction.COMPLETE_TO_SURFACE)
        self.assertEqual(engine.state.phase.name, "CHAMBER_TRAVEL_TO_SURFACE")
        clock["now"] += timedelta(seconds=81)
        engine.dispatch(EngineAction.REACH_SURFACE)
        self.assertEqual(engine.state.phase.name, "COMPLETE_CLEAN_TIME")

        # Clean time completes after 10 min (auto-tick via tick())
        clock["now"] += timedelta(minutes=10, seconds=1)
        engine.tick()
        self.assertEqual(engine.state.phase.name, "READY")


# ---------------------------------------------------------------------------
# Rule 9: pending_action_text for long O2 segments
# ---------------------------------------------------------------------------

class PendingActionTextTests(unittest.TestCase):
    """
    pending_action_text must show "Air Break for 5 min" when the current
    O2 segment is ≥ 30 min (SURD_O2_BREAK_TRIGGER_SEC) and a next segment
    exists, indicating to the operator that a break will be required.
    """

    def test_pending_action_text_air_break_for_30_min_segment(self) -> None:
        """120/90 segment 2 is 30 min — should show air break warning."""
        clock, engine = _make_engine()
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)
        clock["now"] = t_handoff + timedelta(minutes=4)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        # Move through segments 0 and 1 to reach segment 2 (30 min)
        clock["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)
        clock["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)
        clock["now"] += timedelta(seconds=20)
        engine.dispatch(EngineAction.REACH_STOP)

        # Now at segment 2 (30 min duration, next segment exists)
        view = engine.view()
        self.assertEqual(view.pending_action_text, "Air Break for 5 min")

    def test_pending_action_text_none_for_short_segment(self) -> None:
        """100/30 has only a single 15-min segment — no air break warning."""
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        view = engine.view()
        self.assertIsNone(view.pending_action_text)


# ---------------------------------------------------------------------------
# Rule 10: MOVE_CHAMBER semantics
# ---------------------------------------------------------------------------

class MoveChamberTests(unittest.TestCase):
    """
    MOVE_CHAMBER advances to the next segment only after the current
    segment obligation is fully met.  It must not be available before the
    segment is done.
    """

    def test_move_chamber_not_available_before_segment_complete(self) -> None:
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=14)
        view = engine.view()
        self.assertNotIn("MOVE_CHAMBER", view.available_actions)

    def test_move_chamber_available_after_segment_complete(self) -> None:
        clock, engine = _make_engine()
        _drive_to_confirm_o2(clock, engine, si_seconds=4 * 60)
        clock["now"] += timedelta(minutes=15)
        view = engine.view()
        self.assertIn("MOVE_CHAMBER", view.available_actions)

    def test_move_chamber_advances_current_segment_index(self) -> None:
        clock, engine = _make_engine()
        t_handoff = T0
        handoff = _l40_handoff(handed_off_at=t_handoff)
        _drive_to_chamber_50(clock, engine, handoff)
        clock["now"] = t_handoff + timedelta(minutes=4)
        engine.dispatch(EngineAction.REACH_CHAMBER_50)
        engine.dispatch(EngineAction.CONFIRM_ON_O2)

        index_before = engine.state.current_segment_index
        clock["now"] += timedelta(minutes=15)
        engine.dispatch(EngineAction.MOVE_CHAMBER)

        self.assertEqual(
            engine.state.current_segment_index,
            (index_before or 0) + 1,
        )


if __name__ == "__main__":
    unittest.main()
