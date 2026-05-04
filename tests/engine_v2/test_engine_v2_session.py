from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.engine_v2.contracts.events import AuditEventKind
from dive_stopwatch.engine_v2.runtime.session import EngineV2Session


class EngineV2SessionTests(unittest.TestCase):
    def test_session_launch_new_api_tracks_diving_mode_and_deco_profile(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0),
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.O2,
        )

        self.assertEqual(session.diving_mode, DivingMode.AIR)
        self.assertEqual(session.deco_profile, DecoProfile.O2)
        self.assertEqual(session.presentation_model().mode_name, "AIR_O2")

    def test_session_launches_modes_explicitly(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0),
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.AIR,
        )
        self.assertEqual(session.presentation_model().mode_name, "AIR")
        self.assertEqual(session.presentation_model().mode_name, "AIR")

        session.launch(DivingMode.CHAMBER, DecoProfile.AIR)
        self.assertEqual(session.presentation_model().mode_name, "CHAMBER")
        self.assertEqual(session.presentation_model().mode_name, "CHAMBER")
        self.assertEqual(session.presentation_model().title, "CAISSON Chamber")

    def test_session_tracks_test_time_and_dispatches_string_actions(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.CHAMBER, deco_profile=DecoProfile.AIR)

        self.assertEqual(session.test_time_label(), "Test Time: LIVE")
        session.advance_test_time(300)
        self.assertEqual(session.test_time_label(), "Test Time: +05:00")

        session.dispatch("LEAVE_SURFACE")
        session.advance_test_time(180)
        session.dispatch("REACH_BOTTOM")
        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.phase_label, "At Stop")
        assert presentation_model.secondary_action is not None
        self.assertEqual(presentation_model.primary_action.label, "Leave Stop")
        self.assertEqual(presentation_model.secondary_action.action_name, "CONFIRM_ON_O2")

    def test_session_fast_forward_keeps_time_running_with_live_clock(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.AIR, deco_profile=DecoProfile.AIR)

        session.set_depth_text("78")
        session.dispatch("LEAVE_SURFACE")
        session.advance_test_time(60)
        self.assertEqual(session.presentation_model().primary_value, "01:00.0")

        current["now"] += timedelta(seconds=30)
        self.assertEqual(session.presentation_model().primary_value, "01:30.0")

    def test_session_surfaces_chamber_selected_table(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.CHAMBER, deco_profile=DecoProfile.AIR)

        session.dispatch("LEAVE_SURFACE")
        session.advance_test_time(180)
        session.dispatch("REACH_BOTTOM")
        session.dispatch("CONFIRM_ON_O2")
        session.advance_test_time(20 * 60)
        session.dispatch("TOGGLE_OFF_O2")
        session.advance_test_time(5 * 60)
        session.dispatch("CONFIRM_ON_O2")
        session.advance_test_time(20 * 60)
        session.dispatch("TOGGLE_OFF_O2")
        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.selected_table_label, "TT6")

    def test_session_runtime_log_captures_mode_input_actions_and_time_changes(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.AIR, deco_profile=DecoProfile.AIR)

        session.set_depth_text("78")
        session.dispatch("LEAVE_SURFACE")
        session.advance_test_time(60)
        session.reset_test_time()

        self.assertEqual(
            [event.kind for event in session.raw_audit_events()[:5]],
            [
                AuditEventKind.MODE_LAUNCHED,
                AuditEventKind.INPUT_UPDATED,
                AuditEventKind.ACTION_DISPATCHED,
                AuditEventKind.LEFT_SURFACE,
                AuditEventKind.TEST_TIME_ADVANCED,
            ],
        )
        self.assertEqual(session.raw_audit_events()[1].payload["field"], "depth_fsw")
        self.assertEqual(session.raw_audit_events()[2].payload["action"], "LEAVE_SURFACE")
        self.assertEqual(session.raw_audit_events()[-1].kind, AuditEventKind.TEST_TIME_RESET)

    def test_session_presentation_model_uses_derived_log_rows(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.AIR, deco_profile=DecoProfile.AIR)

        session.set_depth_text("78")
        session.dispatch("LEAVE_SURFACE")

        presentation_model = session.presentation_model()
        self.assertEqual([row.summary for row in presentation_model.log_rows], ["LS"])

    def test_launch_mode_resets_in_flight_state_and_runtime_log(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        session = EngineV2Session(now_provider=lambda: current["now"], diving_mode=DivingMode.AIR, deco_profile=DecoProfile.AIR)

        session.set_depth_text("78")
        session.dispatch("LEAVE_SURFACE")
        session.advance_test_time(90)
        self.assertEqual(session.presentation_model().primary_value, "01:30.0")

        session.launch(DivingMode.AIR, DecoProfile.O2)

        presentation_model = session.presentation_model()
        self.assertEqual(presentation_model.mode_name, "AIR_O2")
        self.assertEqual(presentation_model.phase_label, "Ready")
        self.assertEqual(presentation_model.primary_value, "00:00.0")
        self.assertEqual(presentation_model.log_rows, ())
        self.assertEqual([event.kind for event in session.raw_audit_events()], [AuditEventKind.MODE_LAUNCHED])
        self.assertEqual(session.raw_audit_events()[0].payload["diving_mode"], "AIR")
        self.assertEqual(session.raw_audit_events()[0].payload["deco_profile"], "O2")

    def test_set_deco_profile_relaunches_engine_with_new_profile(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0),
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.AIR,
        )

        session.set_deco_profile(DecoProfile.SURD)

        self.assertEqual(session.diving_mode, DivingMode.AIR)
        self.assertEqual(session.deco_profile, DecoProfile.SURD)
        self.assertEqual(session.presentation_model().mode_name, "AIR")
        self.assertEqual(session.raw_audit_events()[0].payload["deco_profile"], "SURD")

    def test_preselected_air_surd_reports_active_runtime_mode_until_handoff(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 25, 12, 0, 0),
            diving_mode=DivingMode.AIR,
            deco_profile=DecoProfile.SURD,
        )

        self.assertEqual(session.deco_profile, DecoProfile.SURD)
        self.assertEqual(session.presentation_model().mode_name, "AIR")

    def test_preselected_mixed_gas_surd_reports_active_runtime_mode_until_handoff(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0),
            diving_mode=DivingMode.MIXED_GAS,
            deco_profile=DecoProfile.SURD,
        )

        self.assertEqual(session.deco_profile, DecoProfile.SURD)
        self.assertEqual(session.presentation_model().mode_name, "MIXED_GAS")

    def test_mixed_gas_reset_clears_depth_and_bottom_mix_input_texts(self) -> None:
        session = EngineV2Session(
            now_provider=lambda: datetime(2026, 4, 29, 12, 0, 0),
            diving_mode=DivingMode.MIXED_GAS,
            deco_profile=DecoProfile.MIXED_GAS,
        )

        session.set_depth_text("220")
        session.set_bottom_mix_text("14.0")
        self.assertEqual(session.depth_input_text(), "220")
        self.assertEqual(session.bottom_mix_input_text(), "14.0")

        session.dispatch("RESET")

        self.assertEqual(session.depth_input_text(), "")
        self.assertEqual(session.bottom_mix_input_text(), "")


if __name__ == "__main__":
    unittest.main()
