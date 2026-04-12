from __future__ import annotations

import tkinter as tk

from .core import EngineV2
from .shell import V2ShellApp


def main() -> None:
    root = tk.Tk()
    V2ShellApp(root, EngineV2())
    root.mainloop()


if __name__ == "__main__":
    main()
