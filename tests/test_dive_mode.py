from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.dive_controller import DiveController, DivePhase


class DiveControllerTests(unittest.TestCase):
    def test_button_flow_for_no_decompression_dive(self) -> None:
        controller = DiveController()

        start_response = controller.start(datetime(2026, 3, 30, 9, 0, 0))
        rb_response = controller.start(datetime(2026, 3, 30, 9, 3, 1))
        lb_response = controller.start(datetime(2026, 3, 30, 9, 25, 1))
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
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))
        controller.stop(datetime(2026, 3, 30, 9, 33, 5))

        controller.reset()

        self.assertEqual(controller.phase, DivePhase.READY)
        self.assertEqual(controller.session.summary(), {})

    def test_clean_time_countdown_advances(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))
        controller.stop(datetime(2026, 3, 30, 9, 33, 5))

        status = controller.clean_time_status(datetime(2026, 3, 30, 9, 38, 6))
        done = controller.clean_time_status(datetime(2026, 3, 30, 9, 43, 5))

        self.assertEqual(status["CT"], "04:59")
        self.assertFalse(status["complete"])
        self.assertEqual(done["CT"], "00:00")
        self.assertTrue(done["complete"])

    def test_lap_toggles_descent_hold_before_reaching_bottom(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))

        hold_start = controller.lap(datetime(2026, 3, 30, 9, 1, 0))
        hold_end = controller.lap(datetime(2026, 3, 30, 9, 1, 30))
        rb_response = controller.start(datetime(2026, 3, 30, 9, 3, 1))

        self.assertEqual(hold_start["event"], "R")
        self.assertEqual(hold_end["event"], "L")
        self.assertEqual(hold_start["stop_number"], 1)
        self.assertEqual(hold_end["stop_number"], 1)
        self.assertEqual(rb_response["event"], "RB")

    def test_reaching_bottom_is_blocked_while_descent_hold_is_active(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.lap(datetime(2026, 3, 30, 9, 1, 0))

        with self.assertRaises(RuntimeError):
            controller.start(datetime(2026, 3, 30, 9, 3, 1))

    def test_start_reaches_stop_and_lap_leaves_stop(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        reach_stop = controller.start(datetime(2026, 3, 30, 9, 28, 0))
        leave_stop = controller.lap(datetime(2026, 3, 30, 9, 31, 0))

        self.assertEqual(reach_stop["event"], "R")
        self.assertEqual(leave_stop["event"], "L")
        self.assertEqual(reach_stop["stop_number"], 1)
        self.assertEqual(leave_stop["stop_number"], 1)

        second_reach = controller.start(datetime(2026, 3, 30, 9, 34, 0))
        second_leave = controller.lap(datetime(2026, 3, 30, 9, 36, 0))
        self.assertEqual(second_reach["stop_number"], 2)
        self.assertEqual(second_leave["stop_number"], 2)

    def test_stop_is_blocked_while_still_at_stop(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))
        controller.start(datetime(2026, 3, 30, 9, 28, 0))

        with self.assertRaises(RuntimeError):
            controller.stop(datetime(2026, 3, 30, 9, 33, 5))

    def test_decompression_ascent_can_progress_to_multiple_stop_arrivals(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        first_arrival = controller.start(datetime(2026, 3, 30, 9, 28, 0))
        first_leave = controller.lap(datetime(2026, 3, 30, 9, 31, 0))
        second_arrival = controller.start(datetime(2026, 3, 30, 9, 34, 0))

        self.assertEqual(first_arrival["event"], "R")
        self.assertEqual(first_arrival["stop_number"], 1)
        self.assertEqual(first_leave["stop_number"], 1)
        self.assertEqual(second_arrival["event"], "R")
        self.assertEqual(second_arrival["stop_number"], 2)
        self.assertEqual(controller.latest_arrival_event().stop_number, 2)

    def test_lap_is_blocked_during_ascent_until_stop_is_reached(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        with self.assertRaises(RuntimeError):
            controller.lap(datetime(2026, 3, 30, 9, 26, 0))

    def test_flag_delay_to_first_stop_marks_controller_state(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        result = controller.flag_delay_to_first_stop()

        self.assertEqual(result["event"], "DELAY_PROMPT")
        self.assertTrue(controller.delay_to_first_stop_flagged)

    def test_ascent_delay_events_are_recorded_and_closed(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        delay_start = controller.mark_ascent_delay_start(72, datetime(2026, 3, 30, 9, 26, 0))
        arrival = controller.start(datetime(2026, 3, 30, 9, 28, 0))

        self.assertEqual(delay_start.kind, "start")
        self.assertEqual(delay_start.index, 1)
        self.assertEqual(delay_start.depth_fsw, 72)
        self.assertEqual(arrival["event"], "R")
        self.assertEqual(len(controller.ascent_delay_events), 2)
        self.assertEqual(controller.ascent_delay_events[1].kind, "end")
        self.assertEqual(controller.ascent_delay_events[1].index, 1)

    def test_ascent_delay_can_be_ended_before_reaching_stop(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 1))
        controller.start(datetime(2026, 3, 30, 9, 25, 1))

        delay_start = controller.mark_ascent_delay_start(72, datetime(2026, 3, 30, 9, 26, 0))
        delay_end = controller.end_ascent_delay(datetime(2026, 3, 30, 9, 26, 45))

        self.assertEqual(delay_start.kind, "start")
        self.assertIsNotNone(delay_end)
        self.assertEqual(delay_end.kind, "end")
        self.assertEqual(delay_end.index, 1)
        self.assertEqual(delay_end.depth_fsw, 72)

    def test_manual_example_stop_sequence_records_reach_and_leave_events(self) -> None:
        controller = DiveController()
        controller.start(datetime(2026, 3, 30, 9, 0, 0))
        controller.start(datetime(2026, 3, 30, 9, 3, 0))
        controller.start(datetime(2026, 3, 30, 9, 42, 0))

        reach_50 = controller.start(datetime(2026, 3, 30, 9, 45, 20))
        leave_50 = controller.lap(datetime(2026, 3, 30, 9, 47, 20))
        reach_40 = controller.start(datetime(2026, 3, 30, 9, 47, 40))
        leave_40 = controller.lap(datetime(2026, 3, 30, 9, 53, 40))
        reach_30 = controller.start(datetime(2026, 3, 30, 9, 54, 0))

        self.assertEqual(reach_50["stop_number"], 1)
        self.assertEqual(leave_50["stop_number"], 1)
        self.assertEqual(reach_40["stop_number"], 2)
        self.assertEqual(leave_40["stop_number"], 2)
        self.assertEqual(reach_30["stop_number"], 3)
        self.assertEqual(controller.latest_arrival_event().stop_number, 3)
        self.assertEqual(controller.latest_stop_departure_event().stop_number, 2)
