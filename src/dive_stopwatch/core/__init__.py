"""Core runtime package for the dive stopwatch application."""

from .air_o2_engine import Intent
from .air_o2_profiles import DecoMode, DiveProfile, ProfileStop, build_profile
from .air_o2_snapshot import Snapshot
from .runtime import Engine


def main() -> None:
    from .gui import main as gui_main
    gui_main()


__all__ = ["Engine", "Intent", "Snapshot", "DecoMode", "DiveProfile", "ProfileStop", "build_profile", "main"]
