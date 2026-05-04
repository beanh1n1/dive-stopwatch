from __future__ import annotations

import unittest

from .golden_paths import GoldenExpectation, GoldenFixture, LegacyEngineAdapter, load_golden_fixtures


class EngineGoldenPathTests(unittest.TestCase):
    def test_golden_paths(self) -> None:
        for fixture in load_golden_fixtures():
            with self.subTest(fixture=fixture.fixture_id):
                self._run_fixture(fixture)

    def test_fixture_schema(self) -> None:
        fixtures = load_golden_fixtures()
        self.assertEqual(len(fixtures), 9)
        self.assertEqual({fixture.fixture_id for fixture in fixtures}, {
            "GP-AIR-ND-001",
            "GP-AIR-DECO-001",
            "GP-AIR-O2-MIXED-001",
            "GP-AIR-O2-DIRECT-001",
            "GP-AIR-O2-BREAK30-001",
            "GP-AIR-O2-BREAK20-001",
            "GP-AIR-O2-DELAY-001",
            "GP-SURD-NORMAL-001",
            "GP-SURD-PENALTY-001",
        })

    def _run_fixture(self, fixture: GoldenFixture) -> None:
        adapter = LegacyEngineAdapter(fixture)

        for step_index, step in enumerate(fixture.steps, start=1):
            adapter.advance_time(step.advance_sec)

            if step.intent is not None:
                adapter.dispatch(step.intent)

            if step.expect is not None:
                self._assert_expectation(fixture.fixture_id, step_index, adapter, step.expect)

    def _assert_expectation(self, fixture_id: str, step_index: int, adapter: LegacyEngineAdapter, expect: GoldenExpectation) -> None:
        for field, expected_value in expect.snapshot.items():
            actual_value = adapter.snapshot_field(field)
            self.assertEqual(
                actual_value,
                expected_value,
                msg=f"{fixture_id} step {step_index}: snapshot.{field}",
            )

        state_phase = expect.state_phase
        if state_phase is not None:
            self.assertEqual(
                adapter.state_phase_name(),
                state_phase,
                msg=f"{fixture_id} step {step_index}: state phase",
            )

        recall_lines = adapter.recall_lines()
        for needle in expect.recall_contains:
            self.assertTrue(
                any(needle in line for line in recall_lines),
                msg=f"{fixture_id} step {step_index}: recall missing {needle!r}",
            )


if __name__ == "__main__":
    unittest.main()
