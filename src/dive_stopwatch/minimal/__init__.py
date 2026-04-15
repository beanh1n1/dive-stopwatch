"""Greenfield minimal runtime package."""

from .engine import Engine, Intent
from .profiles import DecoMode, DiveProfile, ProfileStop, build_profile
from .snapshot import Snapshot


def main() -> None:
    from .gui import main as gui_main
    gui_main()


__all__ = ["Engine", "Intent", "Snapshot", "DecoMode", "DiveProfile", "ProfileStop", "build_profile", "main"]
