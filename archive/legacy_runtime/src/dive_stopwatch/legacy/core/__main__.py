from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dive_stopwatch.legacy.core import main
else:
    from . import main


if __name__ == "__main__":
    main()
