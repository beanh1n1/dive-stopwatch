import unittest

from dive_stopwatch.v2.stopwatch_core import Stopwatch, StopwatchManager, format_hhmmss


class StopwatchTests(unittest.TestCase):
    def test_reset_clears_marks_and_time(self) -> None:
        stopwatch = Stopwatch()
        stopwatch.marks.append(object())
        stopwatch._elapsed_before_start = 12.5
        stopwatch._lap_base_total = 12.5
        stopwatch._frozen_display_total = 12.5

        stopwatch.reset()

        self.assertEqual(stopwatch.total_elapsed(), 0.0)
        self.assertEqual(stopwatch.display_time(), 0.0)
        self.assertEqual(stopwatch.marks, [])

    def test_split_freezes_then_releases_display(self) -> None:
        stopwatch = Stopwatch()
        stopwatch._elapsed_before_start = 15.0

        first_mark = stopwatch.split()
        second_mark = stopwatch.split()

        self.assertEqual(first_mark.kind, "SPLIT")
        self.assertEqual(second_mark.kind, "SPLIT_RELEASE")
        self.assertEqual(stopwatch.display_time(), 15.0)

    def test_manager_reuses_named_stopwatch(self) -> None:
        manager = StopwatchManager()

        first = manager.get("main")
        second = manager.get("main")

        self.assertIs(first, second)

    def test_format_hhmmss_rounds_to_milliseconds(self) -> None:
        self.assertEqual(format_hhmmss(3661.2396), "01:01:01.240")


if __name__ == "__main__":
    unittest.main()
