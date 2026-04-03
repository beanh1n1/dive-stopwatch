from datetime import datetime, timedelta
import unittest

from dive_stopwatch.dive_mode import DiveController, DivePhase


class DiveControllerTests(unittest.TestCase):
    def test_button_flow_for_no_decompression_dive(self) -> None:
        controller = DiveController()

        start_response = controller.start(datetime(2026, 3, 30, 9, 0, 0))
        rb_response = controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        lb_response = controller.lap(datetime(2026, 3, 30, 9, 25, 1))
        rs_response = controller.stop(datetime(2026, 3, 30, 9, 33, 5))

        self.assertEqual(start_response["event"], "LS")
        self.assertEqual(rb_response["DT"], 4)
        self.assertEqual(lb_response["BT"], 26)
        self.assertEqual(rs_response["AT"], "08:04")
        self.assertEqual(rs_response["TDT"], 9)
        self.assertEqual(rs_response["TTD"], 34)
        self.assertEqual(rs_response["CT"], "10:00")
        self.assertEqual(controller.phase, DivePhase.CLEAN_TIME)

    def test_reset_is_blocked_during_active_dive(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))

        with self.assertRaises(RuntimeError):
            controller.reset()

    def test_reset_is_allowed_after_clean_time_starts(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))
        controller.stop(datetime(2026, 3, 30, 9, 33, 5))

        controller.reset()

        self.assertEqual(controller.phase, DivePhase.READY)
        self.assertEqual(controller.session.summary(), {})

    def test_clean_time_countdown_advances(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))
        controller.stop(datetime(2026, 3, 30, 9, 33, 5))

        status = controller.clean_time_status(datetime(2026, 3, 30, 9, 38, 6))
        done = controller.clean_time_status(datetime(2026, 3, 30, 9, 43, 5))

        self.assertEqual(status["CT"], "04:59")
        self.assertFalse(status["complete"])
        self.assertEqual(done["CT"], "00:00")
        self.assertTrue(done["complete"])

    def test_lap_after_lb_toggles_r_then_l(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))

        reach_stop = controller.lap(datetime(2026, 3, 30, 9, 28, 0))
        leave_stop = controller.lap(datetime(2026, 3, 30, 9, 31, 0))

        self.assertEqual(reach_stop["event"], "R")
        self.assertEqual(leave_stop["event"], "L")
        self.assertEqual(reach_stop["stop_number"], 1)
        self.assertEqual(leave_stop["stop_number"], 1)

        second_reach = controller.lap(datetime(2026, 3, 30, 9, 34, 0))
        second_leave = controller.lap(datetime(2026, 3, 30, 9, 36, 0))
        self.assertEqual(second_reach["stop_number"], 2)
        self.assertEqual(second_leave["stop_number"], 2)

    def test_stop_is_blocked_while_still_at_stop(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))
        controller.lap(datetime(2026, 3, 30, 9, 28, 0))

        with self.assertRaises(RuntimeError):
            controller.stop(datetime(2026, 3, 30, 9, 33, 5))

    def test_delay_to_first_stop_prompt_uses_start_for_deeper_than_50(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))

        controller.flag_delay_to_first_stop()
        result = controller.start(datetime(2026, 3, 30, 9, 27, 0))

        self.assertEqual(result["event"], "DELAY_ZONE")
        self.assertEqual(controller.delay_to_first_stop_zone, "deeper_than_50")
        self.assertFalse(controller.delay_zone_prompt_active)

    def test_delay_to_first_stop_prompt_uses_lap_for_shallower_than_50(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 3, 1))
        controller.lap(datetime(2026, 3, 30, 9, 25, 1))

        controller.flag_delay_to_first_stop()
        result = controller.lap(datetime(2026, 3, 30, 9, 27, 0))

        self.assertEqual(result["event"], "DELAY_ZONE")
        self.assertEqual(controller.delay_to_first_stop_zone, "shallower_than_50")
        self.assertFalse(controller.delay_zone_prompt_active)
