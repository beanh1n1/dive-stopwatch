# Dive Stopwatch Project

Current runtime is the self-contained `minimal` package.

## Project Layout

- `src/dive_stopwatch/minimal/`: live runtime implementation
- `src/dive_stopwatch/active/main.py`: stable launch entrypoint
- `docs/AIR.csv` and `docs/AIR_O2.csv`: source-of-truth dive tables
- `tests/`: automated tests for the live runtime and source data

## Run App

From project root:

```bash
PYTHONPATH=src python3 -m dive_stopwatch.active.main
```

Or after editable install:

```bash
python3 -m pip install -e .
dive-stopwatch
```

## Run Tests

```bash
python3 -m pytest -q
```
