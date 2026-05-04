from __future__ import annotations

import unittest

from .golden_paths import LegacyEngineAdapter, RedesignEngineAdapter, load_golden_fixtures, run_fixture


SUPPORTED_FIXTURE_IDS = {
    "GP-AIR-ND-001",
    "GP-AIR-DECO-001",
    "GP-AIR-O2-DIRECT-001",
    "GP-AIR-O2-MIXED-001",
    "GP-AIR-O2-BREAK30-001",
    "GP-AIR-O2-BREAK20-001",
    "GP-AIR-O2-DELAY-001",
    "GP-SURD-NORMAL-001",
    "GP-SURD-PENALTY-001",
}

PARITY_SNAPSHOT_FIELDS = (
    "mode_text",
    "profile_schedule_text",
    "status_text",
    "status_value_text",
    "primary_text",
    "depth_text",
    "depth_timer_text",
    "remaining_text",
    "summary_text",
    "detail_text",
    "primary_button_label",
    "secondary_button_label",
)

EXPECTED_PARITY_DIFFS = {
    ("GP-SURD-NORMAL-001", 7, "phase"): ("AT_STOP", "SURFACE_ASCENT"),
    ("GP-SURD-NORMAL-001", 8, "phase"): ("AT_STOP", "UNDRESS"),
    ("GP-SURD-NORMAL-001", 8, "primary_text"): ("01:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 9, "phase"): ("AT_STOP", "SURFACE_TO_CHAMBER_50"),
    ("GP-SURD-NORMAL-001", 9, "primary_text"): ("02:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 10, "phase"): ("AT_STOP", "CHAMBER_WAITING_ON_O2"),
    ("GP-SURD-NORMAL-001", 11, "phase"): ("AT_STOP", "CHAMBER_ON_O2"),
    ("GP-SURD-NORMAL-001", 11, "status_value_text"): ("50 fsw O2", "On O2"),
    ("GP-SURD-NORMAL-001", 12, "phase"): ("AT_STOP", "CHAMBER_ON_O2"),
    ("GP-SURD-NORMAL-001", 12, "status_value_text"): ("40 fsw O2", "On O2"),
    ("GP-SURD-NORMAL-001", 12, "primary_text"): ("15:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 13, "phase"): ("AT_STOP", "CHAMBER_ON_O2"),
    ("GP-SURD-NORMAL-001", 13, "status_value_text"): ("40 fsw O2", "On O2"),
    ("GP-SURD-NORMAL-001", 13, "primary_text"): ("15:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 14, "phase"): ("AT_STOP", "CHAMBER_AIR_BREAK"),
    ("GP-SURD-NORMAL-001", 14, "status_value_text"): ("40 fsw Air Break", "Air Break"),
    ("GP-SURD-NORMAL-001", 14, "primary_text"): ("30:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 15, "phase"): ("AT_STOP", "CHAMBER_AIR_BREAK"),
    ("GP-SURD-NORMAL-001", 15, "status_value_text"): ("40 fsw Air Break", "Air Break"),
    ("GP-SURD-NORMAL-001", 15, "primary_text"): ("30:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 16, "phase"): ("AT_STOP", "CHAMBER_ON_O2"),
    ("GP-SURD-NORMAL-001", 16, "status_value_text"): ("40 fsw O2", "On O2"),
    ("GP-SURD-NORMAL-001", 16, "primary_text"): ("35:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 17, "phase"): ("AT_STOP", "CHAMBER_ON_O2"),
    ("GP-SURD-NORMAL-001", 17, "status_value_text"): ("40 fsw O2", "On O2"),
    ("GP-SURD-NORMAL-001", 17, "primary_text"): ("35:00.0", "00:00.0"),
    ("GP-SURD-NORMAL-001", 18, "phase"): ("AT_STOP", "COMPLETE"),
    ("GP-SURD-NORMAL-001", 18, "status_value_text"): ("CLEAN TIME", "Clean Time"),
    ("GP-SURD-NORMAL-001", 19, "phase"): ("AT_STOP", "COMPLETE"),
    ("GP-SURD-NORMAL-001", 19, "status_value_text"): ("CLEAN TIME", "Clean Time"),
    ("GP-SURD-PENALTY-001", 8, "phase"): ("AT_STOP", "SURFACE_ASCENT"),
    ("GP-SURD-PENALTY-001", 8, "detail_text"): ("05:00-07:00 adds 15 min O2 at 50", ""),
    ("GP-SURD-PENALTY-001", 11, "phase"): ("AT_STOP", "CHAMBER_WAITING_ON_O2"),
}


class RedesignLegacyParityTests(unittest.TestCase):
    def test_supported_fixtures_match_legacy_at_locked_checkpoints(self) -> None:
        fixtures = [fixture for fixture in load_golden_fixtures() if fixture.fixture_id in SUPPORTED_FIXTURE_IDS]
        self.assertEqual({fixture.fixture_id for fixture in fixtures}, SUPPORTED_FIXTURE_IDS)
        mismatches: dict[tuple[str, int, str], tuple[object, object]] = {}

        for fixture in fixtures:
            legacy_checkpoints = run_fixture(LegacyEngineAdapter(fixture), fixture)
            redesign_checkpoints = run_fixture(RedesignEngineAdapter(fixture), fixture)

            self.assertEqual(
                [checkpoint.step_index for checkpoint in redesign_checkpoints],
                [checkpoint.step_index for checkpoint in legacy_checkpoints],
                msg=f"{fixture.fixture_id}: checkpoint step indexes",
            )

            for legacy, redesign in zip(legacy_checkpoints, redesign_checkpoints, strict=True):
                if redesign.state_phase != legacy.state_phase:
                    mismatches[(fixture.fixture_id, legacy.step_index, "phase")] = (legacy.state_phase, redesign.state_phase)
                for field in PARITY_SNAPSHOT_FIELDS:
                    if redesign.snapshot[field] != legacy.snapshot[field]:
                        mismatches[(fixture.fixture_id, legacy.step_index, field)] = (legacy.snapshot[field], redesign.snapshot[field])
                legacy_recall_tail = legacy.recall_lines[-1] if legacy.recall_lines else None
                redesign_recall_tail = redesign.recall_lines[-1] if redesign.recall_lines else None
                if redesign_recall_tail != legacy_recall_tail:
                    mismatches[(fixture.fixture_id, legacy.step_index, "recall_tail")] = (legacy_recall_tail, redesign_recall_tail)

        self.assertDictEqual(mismatches, EXPECTED_PARITY_DIFFS)


if __name__ == "__main__":
    unittest.main()
