from __future__ import annotations

import flet as ft

try:
    from .gui_v2 import main as gui_main
except ImportError:
    from dive_stopwatch.mobile.gui_v2 import main as gui_main


def main() -> None:
    ft.app(target=gui_main)


if __name__ == "__main__":
    main()
