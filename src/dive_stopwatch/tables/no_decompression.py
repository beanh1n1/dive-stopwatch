"""No-decompression limits and repetitive group lookups.

This first pass intentionally supports the 10-60 fsw slice that has been
cross-checked against the user's screenshots. It is table-driven and exact:
depths must match a supported table row.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "NoDecompressionRow",
    "lookup_no_decompression_limit",
    "lookup_repetitive_group",
]


@dataclass(frozen=True)
class NoDecompressionRow:
    depth_fsw: int
    no_stop_limit_min: int | None
    thresholds_min: tuple[tuple[str, int], ...]
    max_group: str


NO_DECOMPRESSION_TABLE: dict[int, NoDecompressionRow] = {
    10: NoDecompressionRow(10, None, (("A", 57), ("B", 101), ("C", 158), ("D", 245), ("E", 426)), "F"),
    15: NoDecompressionRow(
        15,
        None,
        (("A", 36), ("B", 60), ("C", 88), ("D", 121), ("E", 163), ("F", 217), ("G", 297), ("H", 449)),
        "I",
    ),
    20: NoDecompressionRow(
        20,
        None,
        (
            ("A", 26),
            ("B", 43),
            ("C", 61),
            ("D", 82),
            ("E", 106),
            ("F", 133),
            ("G", 165),
            ("H", 205),
            ("I", 256),
            ("J", 330),
            ("K", 461),
        ),
        "L",
    ),
    25: NoDecompressionRow(
        25,
        1102,
        (
            ("A", 20),
            ("B", 33),
            ("C", 47),
            ("D", 62),
            ("E", 78),
            ("F", 97),
            ("G", 117),
            ("H", 140),
            ("I", 166),
            ("J", 198),
            ("K", 236),
            ("L", 285),
            ("M", 354),
            ("N", 469),
            ("O", 992),
            ("Z", 1102),
        ),
        "Z",
    ),
    30: NoDecompressionRow(
        30,
        371,
        (
            ("A", 17),
            ("B", 27),
            ("C", 38),
            ("D", 50),
            ("E", 62),
            ("F", 76),
            ("G", 91),
            ("H", 107),
            ("I", 125),
            ("J", 145),
            ("K", 167),
            ("L", 193),
            ("M", 223),
            ("N", 260),
            ("O", 307),
            ("Z", 371),
        ),
        "Z",
    ),
    35: NoDecompressionRow(
        35,
        232,
        (
            ("A", 14),
            ("B", 23),
            ("C", 32),
            ("D", 42),
            ("E", 52),
            ("F", 63),
            ("G", 74),
            ("H", 87),
            ("I", 100),
            ("J", 115),
            ("K", 131),
            ("L", 148),
            ("M", 168),
            ("N", 190),
            ("O", 215),
            ("Z", 232),
        ),
        "Z",
    ),
    40: NoDecompressionRow(
        40,
        163,
        (
            ("A", 12),
            ("B", 20),
            ("C", 27),
            ("D", 36),
            ("E", 44),
            ("F", 53),
            ("G", 63),
            ("H", 73),
            ("I", 84),
            ("J", 95),
            ("K", 108),
            ("L", 121),
            ("M", 135),
            ("N", 151),
            ("Z", 163),
        ),
        "Z",
    ),
    45: NoDecompressionRow(
        45,
        125,
        (
            ("A", 11),
            ("B", 17),
            ("C", 24),
            ("D", 31),
            ("E", 39),
            ("F", 46),
            ("G", 55),
            ("H", 63),
            ("I", 72),
            ("J", 82),
            ("K", 92),
            ("L", 102),
            ("M", 114),
            ("Z", 125),
        ),
        "Z",
    ),
    50: NoDecompressionRow(
        50,
        92,
        (
            ("A", 9),
            ("B", 15),
            ("C", 21),
            ("D", 28),
            ("E", 34),
            ("F", 41),
            ("G", 48),
            ("H", 56),
            ("I", 63),
            ("J", 71),
            ("K", 80),
            ("L", 89),
            ("Z", 92),
        ),
        "Z",
    ),
    55: NoDecompressionRow(
        55,
        74,
        (
            ("A", 8),
            ("B", 14),
            ("C", 19),
            ("D", 25),
            ("E", 31),
            ("F", 37),
            ("G", 43),
            ("H", 50),
            ("I", 56),
            ("J", 63),
            ("K", 71),
            ("Z", 74),
        ),
        "Z",
    ),
    60: NoDecompressionRow(
        60,
        63,
        (("A", 7), ("B", 12), ("C", 17), ("D", 22), ("E", 28), ("F", 33), ("G", 39), ("H", 45), ("I", 51), ("J", 57), ("Z", 63)),
        "Z",
    ),
}


def lookup_no_decompression_limit(depth_fsw: int) -> int | None:
    row = NO_DECOMPRESSION_TABLE.get(depth_fsw)
    if row is None:
        raise KeyError(f"Unsupported no-decompression depth: {depth_fsw} fsw")
    return row.no_stop_limit_min


def lookup_repetitive_group(depth_fsw: int, bottom_time_min: int) -> str:
    row = NO_DECOMPRESSION_TABLE.get(depth_fsw)
    if row is None:
        raise KeyError(f"Unsupported no-decompression depth: {depth_fsw} fsw")
    if bottom_time_min < 0:
        raise ValueError("Bottom time cannot be negative.")

    for group, threshold in row.thresholds_min:
        if bottom_time_min <= threshold:
            return group
    return row.max_group
