import unittest

from dive_stopwatch.tables.air_decompression import (
    available_air_decompression_depths,
    lookup_air_decompression_row,
)
from dive_stopwatch.tables.no_decompression import (
    lookup_no_decompression_limit,
    lookup_repetitive_group,
)


class NoDecompressionTableTests(unittest.TestCase):
    def test_lookup_no_stop_limit(self) -> None:
        self.assertEqual(lookup_no_decompression_limit(50), 92)
        self.assertIsNone(lookup_no_decompression_limit(10))

    def test_lookup_repetitive_group_for_exact_threshold(self) -> None:
        self.assertEqual(lookup_repetitive_group(30, 145), "J")
        self.assertEqual(lookup_repetitive_group(55, 74), "Z")

    def test_lookup_repetitive_group_uses_max_group_for_unlimited_rows(self) -> None:
        self.assertEqual(lookup_repetitive_group(15, 500), "I")
        self.assertEqual(lookup_repetitive_group(20, 999), "L")


class AirDecompressionTableTests(unittest.TestCase):
    def test_supported_depths_are_exposed(self) -> None:
        self.assertEqual(available_air_decompression_depths(), [30, 35, 45, 50, 55, 60])

    def test_lookup_standard_air_row(self) -> None:
        row = lookup_air_decompression_row(30, 371)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {})
        self.assertEqual(row.total_ascent_time, "1:00")
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "standard")

    def test_lookup_recommended_row(self) -> None:
        row = lookup_air_decompression_row(50, 120)
        self.assertEqual(row.time_to_first_stop, "1:00")
        self.assertEqual(row.stops_fsw, {20: 21})
        self.assertEqual(row.total_ascent_time, "22:40")
        self.assertEqual(row.chamber_o2_periods, 0.5)
        self.assertEqual(row.repeat_group, "O")
        self.assertEqual(row.section, "recommended")

    def test_lookup_required_row(self) -> None:
        row = lookup_air_decompression_row(45, 200)
        self.assertEqual(row.stops_fsw, {20: 89})
        self.assertEqual(row.total_ascent_time, "90:30")
        self.assertEqual(row.chamber_o2_periods, 1.0)
        self.assertEqual(row.repeat_group, "Z")
        self.assertEqual(row.section, "required")

    def test_lookup_surd_o2_row(self) -> None:
        row = lookup_air_decompression_row(60, 300)
        self.assertEqual(row.stops_fsw, {20: 456})
        self.assertEqual(row.total_ascent_time, "458:00")
        self.assertEqual(row.chamber_o2_periods, 4.5)
        self.assertEqual(row.section, "surd_o2")


if __name__ == "__main__":
    unittest.main()
