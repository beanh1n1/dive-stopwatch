"""Structured dive tables used by the application."""

from .air_decompression import (
    AirDecoRow,
    BasicAirDecompressionProfile,
    FirstStopArrivalEvaluation,
    available_air_decompression_depths,
    build_basic_air_decompression_profile,
    build_basic_air_decompression_profile_for_session,
    evaluate_first_stop_arrival,
    lookup_air_decompression_row,
    planned_travel_time_to_first_stop_seconds,
)
from .no_decompression import (
    NoDecompressionRow,
    lookup_no_decompression_limit,
    lookup_no_decompression_limit_for_depth,
    lookup_repetitive_group,
)

__all__ = [
    "AirDecoRow",
    "BasicAirDecompressionProfile",
    "FirstStopArrivalEvaluation",
    "NoDecompressionRow",
    "available_air_decompression_depths",
    "build_basic_air_decompression_profile",
    "build_basic_air_decompression_profile_for_session",
    "evaluate_first_stop_arrival",
    "lookup_air_decompression_row",
    "lookup_no_decompression_limit",
    "lookup_no_decompression_limit_for_depth",
    "lookup_repetitive_group",
    "planned_travel_time_to_first_stop_seconds",
]
