"""Structured dive tables used by the application."""

from .air_decompression import (
    AirDecoRow,
    available_air_decompression_depths,
    lookup_air_decompression_row,
)
from .no_decompression import (
    NoDecompressionRow,
    lookup_no_decompression_limit,
    lookup_repetitive_group,
)

__all__ = [
    "AirDecoRow",
    "NoDecompressionRow",
    "available_air_decompression_depths",
    "lookup_air_decompression_row",
    "lookup_no_decompression_limit",
    "lookup_repetitive_group",
]
