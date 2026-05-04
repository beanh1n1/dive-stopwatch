from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2.contracts.timers import TimerState, elapsed, pause, remaining, resume, shift


class EngineV2TimersTests(unittest.TestCase):
    def test_elapsed_pause_resume_and_remaining_share_one_timer_model(self) -> None:
        start = datetime(2026, 4, 25, 12, 0, 0)
        timer = TimerState(started_at=start)

        running_now = start + timedelta(minutes=7)
        self.assertEqual(elapsed(timer, running_now), 7 * 60)
        self.assertEqual(remaining(timer, running_now, target_sec=15 * 60), 8 * 60)

        paused = pause(timer, running_now)
        paused_later = running_now + timedelta(minutes=4)
        self.assertEqual(elapsed(paused, paused_later), 7 * 60)

        resumed = resume(paused, paused_later)
        resumed_later = paused_later + timedelta(minutes=3)
        self.assertEqual(elapsed(resumed, resumed_later), 10 * 60)

    def test_shift_moves_anchor_without_changing_elapsed_at_shift_point(self) -> None:
        start = datetime(2026, 4, 25, 12, 0, 0)
        timer = TimerState(started_at=start)
        now = start + timedelta(minutes=5)

        shifted = shift(timer, seconds=120)

        self.assertEqual(elapsed(timer, now), 5 * 60)
        self.assertEqual(elapsed(shifted, now), 3 * 60)


if __name__ == "__main__":
    unittest.main()
