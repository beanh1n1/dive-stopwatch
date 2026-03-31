"""Dive stopwatch package."""

from .cli import main
from .dive_mode import CleanTimeTimer, DiveController, DivePhase
from .dive_session import DiveEvent, DiveMetrics, DiveSession
from .gui import DiveStopwatchApp
from .stopwatch import DeviceMode, Mark, Stopwatch, StopwatchManager, format_hhmmss
from .tables import (
    AirDecoRow,
    NoDecompressionRow,
    available_air_decompression_depths,
    lookup_air_decompression_row,
    lookup_no_decompression_limit,
    lookup_repetitive_group,
)

__all__ = [
    "CleanTimeTimer",
    "DeviceMode",
    "DiveController",
    "DiveEvent",
    "DiveMetrics",
    "DivePhase",
    "DiveSession",
    "DiveStopwatchApp",
    "Mark",
    "NoDecompressionRow",
    "Stopwatch",
    "StopwatchManager",
    "AirDecoRow",
    "available_air_decompression_depths",
    "format_hhmmss",
    "lookup_air_decompression_row",
    "lookup_no_decompression_limit",
    "lookup_repetitive_group",
    "main",
]
