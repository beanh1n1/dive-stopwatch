# Dive Stopwatch Project

Current runtime is **v2-first**.

## Project Layout

- `src/dive_stopwatch/v2/`: active core + shell runtime (`dive_controller`, `dive_session`, `stopwatch_core`)
- `src/dive_stopwatch/legacy/__init__.py`: minimal legacy compatibility file
- `tests/`: automated tests

## Run v2

From project root:

```bash
PYTHONPATH=src python3 -m dive_stopwatch
```

Or after editable install:

```bash
python3 -m pip install -e .
dive-stopwatch
```

## Run Tests

```bash
python3 -m pip install -e .[dev]
pytest
```
