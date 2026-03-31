"""Dive stopwatch package."""

from .cli import main
from .dive_mode import CleanTimeTimer, DiveController, DivePhase
from .dive_session import DiveEvent, DiveMetrics, DiveSession
from .gui import DiveStopwatchApp
from .stopwatch import DeviceMode, Mark, Stopwatch, StopwatchManager, format_hhmmss

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
    "Stopwatch",
    "StopwatchManager",
    "format_hhmmss",
    "main",
]
