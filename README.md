# Dive Stopwatch Project

This repo contains the live `dive-stopwatch` runtime and a parallel Flet mobile UI for supervising decompression procedures.

## What Is Live

- `src/dive_stopwatch/core/`
  - current runtime
  - stopwatch runtime
  - desktop GUI
- `src/dive_stopwatch/mobile/`
  - Flet mobile GUI
- `docs/AIR.csv` and `docs/AIR_O2.csv`
  - source table data used by the runtime
- `tests/`
  - active regression, parity, and table-validation suites

## Source Of Truth

The governing authority for decompression behavior is:

1. [docs/US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)
2. [docs/SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md)
3. [docs/RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
4. rule and scenario docs in `docs/`
5. tests
6. code

If docs, tests, or code disagree with the manual chapter, the manual wins.

## Run The Desktop App

From project root:

```bash
PYTHONPATH=src python3 -m dive_stopwatch.core
```

Or after editable install:

```bash
python3 -m pip install -e .
dive-stopwatch
```

## Run The Mobile GUI

```bash
python3 -m pip install -e ".[mobile]"
dive-stopwatch-mobile
```

## Install From GitHub

These steps assume you are using a Mac and have little or no coding experience.

### 1. Open Terminal

Open the `Terminal` app on your Mac.

### 2. Check whether Git and Python are already installed

```bash
git --version
python3 --version
```

If `git` is missing:

```bash
xcode-select --install
```

If `python3` is missing, install Python 3 from [python.org](https://www.python.org/downloads/).

### 3. Download the project

```bash
cd ~/Desktop
git clone https://github.com/beanh1n1/dive-stopwatch.git
cd dive-stopwatch
```

### 4. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Install the app

Desktop app only:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Desktop + mobile GUI:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[mobile]"
```

### 6. Run the app

Desktop:

```bash
dive-stopwatch
```

Mobile GUI:

```bash
dive-stopwatch-mobile
```

## Run Tests

```bash
python3 -m pytest -q
```
