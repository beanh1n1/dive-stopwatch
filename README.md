# Dive Stopwatch Project

Current focus is the stopwatch prototype in Python.

## Project Layout

- `src/dive_stopwatch/`: reusable stopwatch package
- `src/dive_stopwatch/cli.py`: command-line interface
- `src/dive_stopwatch/gui.py`: tkinter prototype GUI
- `tests/`: automated tests
- `docs/notes_dive_model.py`: rough outline for later dive-mode work

## Recommended Workflow

1. Keep reusable logic in `src/dive_stopwatch/`.
2. Keep command-line behavior in `src/dive_stopwatch/cli.py`.
3. Add tests in `tests/` as stopwatch behavior expands.
4. Leave dive-mode planning in `docs/notes_dive_model.py` until the stopwatch is stable.

## Run The Stopwatch

From the project root:

```bash
PYTHONPATH=src python3 -m dive_stopwatch
```

Or, after installing the project in editable mode:

```bash
python3 -m pip install -e .
dive-stopwatch
```

## Run The GUI

From the project root:

```bash
python3 -m dive_stopwatch.gui
```

The GUI is intentionally a thin prototype over the stopwatch and dive-mode logic.

## Run Tests

Without extra dependencies:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

If you install dev dependencies:

```bash
python3 -m pip install -e .[dev]
pytest
```

## Naming Conventions

- Package name: `dive_stopwatch`
- Main stopwatch model: `Stopwatch`
- Multiple timers: `StopwatchManager`
- CLI entrypoint: `dive_stopwatch.cli:main`
