from datetime import datetime
import unittest

from dive_stopwatch.v2.decision_resolver import DecisionResolver
from dive_stopwatch.v2.models import StateV2
from dive_stopwatch.v2.procedure_engine import ProcedureDecision
from dive_stopwatch.v2.models import StatusV2


class _StubProcedureEngine:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, **kwargs) -> ProcedureDecision:
        self.calls += 1
        return ProcedureDecision(
            status=StatusV2.READY,
            timer_kind="READY_ZERO",
            summary_text="Next: --",
            summary_targets_oxygen_stop=False,
            start_label="x",
            secondary_label="y",
            start_enabled=True,
            secondary_enabled=False,
        )


class DecisionResolverTests(unittest.TestCase):
    def test_resolve_uses_cache_for_same_inputs(self) -> None:
        stub = _StubProcedureEngine()
        resolver = DecisionResolver(procedure_engine=stub)  # type: ignore[arg-type]
        state = StateV2()
        now = datetime(2026, 4, 12, 10, 0, 0)

        first = resolver.resolve(
            state=state,
            now=now,
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )
        second = resolver.resolve(
            state=state,
            now=now,
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )

        self.assertIs(first, second)
        self.assertEqual(stub.calls, 1)

    def test_invalidate_forces_recompute(self) -> None:
        stub = _StubProcedureEngine()
        resolver = DecisionResolver(procedure_engine=stub)  # type: ignore[arg-type]
        state = StateV2()
        now = datetime(2026, 4, 12, 10, 0, 0)

        resolver.resolve(
            state=state,
            now=now,
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )
        resolver.invalidate()
        resolver.resolve(
            state=state,
            now=now,
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )

        self.assertEqual(stub.calls, 2)

    def test_second_boundary_changes_key(self) -> None:
        stub = _StubProcedureEngine()
        resolver = DecisionResolver(procedure_engine=stub)  # type: ignore[arg-type]
        state = StateV2()

        resolver.resolve(
            state=state,
            now=datetime(2026, 4, 12, 10, 0, 0),
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )
        resolver.resolve(
            state=state,
            now=datetime(2026, 4, 12, 10, 0, 1),
            profile=None,
            at_o2_stop=False,
            active_air_break=None,
            active_air_break_elapsed_seconds=0.0,
            can_start_air_break=False,
            awaiting_first_o2_confirmation=False,
            active_o2_display_mode=False,
            air_break_due_in_seconds=None,
            show_tsv=False,
            start_reaches_surface=False,
        )

        self.assertEqual(stub.calls, 2)


if __name__ == "__main__":
    unittest.main()
