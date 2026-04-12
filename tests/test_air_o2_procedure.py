from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.air_o2_procedure import (
    active_air_break_event,
    active_o2_display_mode,
    air_o2_accrued_credit_to_20_stop_seconds,
    air_o2_credit_to_20_stop_seconds,
    can_start_air_break,
    current_stop_balance_seconds,
    current_air_break_elapsed_seconds,
    ignored_air_seconds_between,
    oxygen_break_due,
    oxygen_elapsed_seconds,
    remaining_oxygen_obligation_seconds,
    should_shift_to_air_for_surface,
)
from dive_stopwatch.v2.dive_controller import AscentStopEvent
from dive_stopwatch.v2.models import AirBreakEventV2 as AirBreakEvent


class AirO2ProcedureTests(unittest.TestCase):
    def test_active_air_break_event_returns_unclosed_break(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)
        events = [
            AirBreakEvent(kind="start", index=1, timestamp=start, depth_fsw=20, stop_number=2),
            AirBreakEvent(kind="end", index=1, timestamp=start + timedelta(minutes=5), depth_fsw=20, stop_number=2),
            AirBreakEvent(kind="start", index=2, timestamp=start + timedelta(minutes=10), depth_fsw=20, stop_number=2),
        ]

        active = active_air_break_event(events)

        self.assertIsNotNone(active)
        self.assertEqual(active.index, 2)

    def test_current_air_break_elapsed_seconds(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)
        active = AirBreakEvent(kind="start", index=1, timestamp=start, depth_fsw=20, stop_number=2)

        elapsed = current_air_break_elapsed_seconds(
            active_break=active,
            now=start + timedelta(minutes=2, seconds=30),
        )

        self.assertEqual(elapsed, 150.0)

    def test_ignored_air_seconds_between_counts_break_overlap(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)
        events = [
            AirBreakEvent(kind="start", index=1, timestamp=start + timedelta(minutes=1), depth_fsw=20, stop_number=2),
            AirBreakEvent(kind="end", index=1, timestamp=start + timedelta(minutes=6), depth_fsw=20, stop_number=2),
        ]

        ignored = ignored_air_seconds_between(
            events=events,
            start_time=start,
            end_time=start + timedelta(minutes=10),
            now=start + timedelta(minutes=10),
        )

        self.assertEqual(ignored, 300.0)

    def test_oxygen_elapsed_seconds_pauses_during_break(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)
        active_break = AirBreakEvent(kind="start", index=1, timestamp=start + timedelta(minutes=30), depth_fsw=20, stop_number=2)

        elapsed = oxygen_elapsed_seconds(
            oxygen_segment_started_at=start,
            active_break=active_break,
            now=start + timedelta(minutes=31),
        )

        self.assertIsNone(elapsed)

    def test_oxygen_break_due_triggers_at_thirty_minutes(self) -> None:
        self.assertFalse(oxygen_break_due(1799.0))
        self.assertTrue(oxygen_break_due(1800.0))

    def test_air_o2_credit_to_20_stop_seconds_credits_extra_thirty_stop_time(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)
        ascent_stop_events = [
            AscentStopEvent(kind="reach", index=3, timestamp=start, depth_fsw=30),
            AscentStopEvent(kind="leave", index=3, timestamp=start + timedelta(minutes=10), depth_fsw=30),
        ]

        credited = air_o2_credit_to_20_stop_seconds(
            stops_fsw={50: 2, 40: 6, 30: 7, 20: 35},
            ascent_stop_events=ascent_stop_events,
            first_oxygen_confirmed_at=start + timedelta(minutes=1),
            air_break_events=[],
            now=start + timedelta(minutes=10),
        )

        self.assertEqual(credited, 120.0)

    def test_air_o2_accrued_credit_to_20_stop_seconds_counts_current_extra_thirty_stop_time(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)

        credited = air_o2_accrued_credit_to_20_stop_seconds(
            stops_fsw={50: 2, 40: 6, 30: 7, 20: 35},
            current_depth=30,
            first_oxygen_confirmed_at=start,
            air_break_events=[],
            now=start + timedelta(minutes=9),
        )

        self.assertEqual(credited, 120.0)

    def test_current_stop_balance_seconds_applies_20_foot_credit(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)

        balance = current_stop_balance_seconds(
            required_stop_time_min=35,
            anchor_time=start,
            now=start + timedelta(minutes=10),
            current_depth=20,
            is_air_o2_mode=True,
            ignored_air_seconds=0.0,
            credit_to_20_seconds=120.0,
        )

        self.assertEqual(balance, 1380.0)

    def test_remaining_oxygen_obligation_seconds_during_30_to_20_travel(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)

        remaining = remaining_oxygen_obligation_seconds(
            stops_fsw={50: 2, 40: 6, 30: 7, 20: 35},
            at_stop=False,
            current_depth=None,
            current_balance_seconds=None,
            latest_departure_timestamp=start,
            departure_depth=30,
            next_depth=20,
            credit_to_20_seconds=120.0,
            accrued_credit_to_20_seconds=0.0,
            ignored_air_seconds_since_departure=0.0,
            now=start + timedelta(minutes=1),
        )

        self.assertEqual(remaining, 1920.0)

    def test_active_o2_display_mode_true_during_30_to_20_travel(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)

        self.assertTrue(
            active_o2_display_mode(
                oxygen_segment_started_at=start,
                active_break=None,
                current_depth=None,
                departure_depth=30,
                next_depth=20,
                at_stop=False,
            )
        )

    def test_can_start_air_break_false_when_twenty_stop_complete(self) -> None:
        start = datetime(2026, 4, 10, 12, 0, 0)

        self.assertFalse(
            can_start_air_break(
                active_break=None,
                awaiting_o2_confirmation=False,
                current_depth=20,
                oxygen_segment_started_at=start,
                oxygen_break_due_now=True,
                current_stop_remaining_text="00:00",
                at_stop=True,
            )
        )

    def test_should_shift_to_air_for_surface_true_when_break_due_and_stop_complete(self) -> None:
        self.assertTrue(
            should_shift_to_air_for_surface(
                current_depth=20,
                oxygen_break_due_now=True,
                current_stop_remaining_text="00:00",
                at_stop=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
