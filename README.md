# Dive Stopwatch Project

This repo contains the active `engine_v2` runtime and its Flet mobile GUI. Preserved pre-`engine_v2` runtime/UI code lives under `archive/` for reference only and is not part of the active app path.

## What Is Live

- `src/dive_stopwatch/engine_v2/`
  - current runtime under active development
- `src/dive_stopwatch/mobile/gui_v2.py`
  - current Flet mobile GUI for `engine_v2`
- `src/dive_stopwatch/engine_v2/domain/air_o2_profiles.py`
  - active AIR/AIR_O2 profile and table logic
- `docs/Tables/`
  - source table data used by the runtime
- `tests/`
  - active regression, parity, and table-validation suites
- `archive/legacy_runtime/`
  - preserved legacy runtime/UI package and legacy-only tests

## Source Of Truth

The governing authority for decompression behavior is:

1. [docs/Source Truth/AIR_Decompression_Operations_US DIVING MANUAL_REV7_ChangeA-6.6.18.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/Source%20Truth/AIR_Decompression_Operations_US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18.pdf)
2. [docs/Source Truth/SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/Source%20Truth/SOURCE_OF_TRUTH.md)
3. [docs/Rules/RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/Rules/RULE_TRACEABILITY_MATRIX.md)
4. rule and scenario docs under `docs/Rules/` and `docs/Scenerios/`
5. tests
6. code

If docs, tests, or code disagree with the manual chapter, the manual wins.

## Run The App

```bash
python3 -m pip install -e ".[mobile]"
dive-stopwatch
dive-stopwatch-mobile
```

Both commands launch the active `engine_v2` Flet shell with dedicated tiles for:

- `AIR`
- `AIR/O2`
- `AIR/SURD`
- `Mixed Gas`
- `Mixed/SURD`
- `CHAMBER`

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

Install the app:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[mobile]"
```

### 6. Run the app

```bash
dive-stopwatch-mobile
```

## Run Tests

```bash
python3 -m pytest -q
```

The highest-signal active suites are:

- `tests/engine_v2/`
- `tests/test_tables.py`
- `tests/test_core_profiles.py`

## Font Assets

The standard cockpit font is:

- `/Users/iananderson/projects/DiveStopwatchProject/assets/fonts/CaissonCockpit.ttf`

Its packaged distribution is:

- `/Users/iananderson/projects/DiveStopwatchProject/assets/fonts/CaissonCockpit-package`

The editable FontForge source for that font is:

- `/Users/iananderson/projects/DiveStopwatchProject/assets/fonts/CaissonCockpit-Regular.sfd`
