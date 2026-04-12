# Dive Stopwatch Project

Current runtime is **v2-first (V2.1 layout)**.

## Project Layout

- `src/dive_stopwatch/v2/`: active core + shell runtime (`dive_controller`, `dive_session`, `stopwatch_core`)
- `src/dive_stopwatch/legacy/__init__.py`: single legacy compatibility file kept during transition
- `tests/`: automated tests

## How V2.1 Works (Plain English)

1. `v2/main.py` starts Tkinter and creates `V2ShellApp`.
2. `v2/shell.py` maps button clicks to high-level intents:
   - `PRIMARY`: progress action (leave surface/reach bottom/reach stop/etc.)
   - `SECONDARY`: context action (hold/delay/on-o2/off-o2/reset in stopwatch)
   - `MODE`: cycle STOPWATCH -> DIVE AIR -> DIVE AIR/O2
   - `RESET`: reset current mode
3. `v2/core.py` interprets intents and updates runtime state.
4. Every refresh tick, `EngineV2.snapshot()` runs the snapshot pipeline:
   - `facts.py`: collect current runtime facts
   - `profile_resolver.py`: build/cache decompression profile from tables
   - `runtime_context.py`: derive decision flags
   - `decision_resolver.py` + `procedure_engine.py`: choose labels/status/actions
   - `snapshot_composer.py`: build timer/depth/remaining/detail text
   - `presenter.py`: assemble final immutable snapshot for GUI rendering

## Run v2

From project root:

```bash
PYTHONPATH=src python3 -m dive_stopwatch.v2.main
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
