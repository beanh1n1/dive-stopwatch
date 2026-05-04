from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest

from dive_stopwatch.core.air_o2_profiles import DecoMode
from dive_stopwatch.core import Intent
from dive_stopwatch.core.redesign import OperatorAction, RedesignRuntime, intent_to_operator_action


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "redesign_handoff_contracts.json"


class RedesignHandoffContractTests(unittest.TestCase):
    def test_handoff_contract_fixtures(self) -> None:
        fixtures = json.loads(FIXTURES_PATH.read_text())

        for fixture in fixtures:
            with self.subTest(fixture=fixture["id"]):
                current = {"now": datetime.fromisoformat(fixture["start_time"])}
                runtime = RedesignRuntime(mode=DecoMode[fixture["mode"].replace("/", "_")], now_provider=lambda: current["now"])
                if fixture.get("depth_text"):
                    runtime.set_depth_text(fixture["depth_text"])

                for step in fixture["steps"]:
                    current["now"] += timedelta(seconds=step.get("advance_sec", 0))
                    intent_name = step.get("intent")
                    if intent_name is not None:
                        action = intent_to_operator_action(getattr(Intent, intent_name), runtime.state_view)
                        self.assertIsNotNone(action)
                        runtime.dispatch(action)
                    expected = step.get("expect_handoff")
                    if expected is not None:
                        handoff = runtime.active_handoff
                        self.assertIsNotNone(handoff)
                        self.assertTrue(runtime.state_view.surface_active)
                        self.assertEqual(runtime.state_view.phase_name, expected["phase_name"])
                        self.assertEqual(handoff.entry_kind.name, expected["entry_kind"])
                        self.assertEqual(handoff.source_mode_text, expected["source_mode_text"])
                        self.assertEqual(handoff.input_depth_fsw, expected["input_depth_fsw"])
                        self.assertEqual(handoff.input_bottom_time_min, expected["input_bottom_time_min"])
                        self.assertEqual(handoff.source_profile_schedule_text, expected["source_profile_schedule_text"])
                        self.assertEqual(handoff.source_table_depth_fsw, expected["source_table_depth_fsw"])
                        self.assertEqual(handoff.source_table_bottom_time_min, expected["source_table_bottom_time_min"])
                        self.assertEqual(handoff.left_water_stop_depth_fsw, expected["left_water_stop_depth_fsw"])
                        self.assertEqual(handoff.remaining_in_water_obligation_sec, expected["remaining_in_water_obligation_sec"])
                        self.assertTrue(any(line.startswith("L2 ") for line in handoff.audit_lines))
                        self.assertEqual(handoff.handed_off_at, current["now"])


if __name__ == "__main__":
    unittest.main()
