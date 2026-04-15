# Dive Stopwatch Project

Current runtime is the self-contained `minimal` package.

## Project Layout

- `src/dive_stopwatch/minimal/`: live runtime implementation
- `src/dive_stopwatch/minimal/snapshot.py`: presentation snapshot compilation for the live runtime
- `src/dive_stopwatch/active/main.py`: stable launch entrypoint
- `src/dive_stopwatch/mobile/`: parallel Flet-based mobile GUI
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

## Install From GitHub

These steps assume you are using a Mac and have little or no coding experience.

### 1. Open Terminal

Open the `Terminal` app on your Mac.

### 2. Check whether Git and Python are already installed

Copy and paste these commands one at a time:

```bash
git --version
python3 --version
```

If both commands print version numbers, continue to step 3.

If `git` is missing, install Apple’s command line tools:

```bash
xcode-select --install
```

If `python3` is missing, install Python 3 from [python.org](https://www.python.org/downloads/).

### 3. Download the project from GitHub

Move to a location where you want the project folder to live. This example uses your Desktop:

```bash
cd ~/Desktop
```

Then download the project:

```bash
git clone https://github.com/beanh1n1/dive-stopwatch.git
```

This will create a folder named `dive-stopwatch`.

### 4. Enter the project folder

```bash
cd dive-stopwatch
```

### 5. Create a virtual environment

This creates a private Python environment just for this project:

```bash
python3 -m venv .venv
```

### 6. Activate the virtual environment

```bash
source .venv/bin/activate
```

After this, your Terminal prompt should begin with `(.venv)`.

### 7. Install the app

For the main app:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

### 8. Run the main app

```bash
dive-stopwatch
```

## Run Mobile GUI

Install the optional mobile GUI dependency and launch the parallel Flet interface:

```bash
python3 -m pip install -e ".[mobile]"
dive-stopwatch-mobile
```

If you prefer the mobile GUI, the full install command is:

```bash
python3 -m pip install -e ".[mobile]"
```

### Each time you want to run the app later

Open Terminal and run:

```bash
cd ~/Desktop/dive-stopwatch
source .venv/bin/activate
dive-stopwatch
```

Or for the mobile GUI:

```bash
cd ~/Desktop/dive-stopwatch
source .venv/bin/activate
dive-stopwatch-mobile
```

### To update the project later

```bash
cd ~/Desktop/dive-stopwatch
git pull
source .venv/bin/activate
python3 -m pip install -e .
```

If you use the mobile GUI, update with:

```bash
python3 -m pip install -e ".[mobile]"
```

## Run Tests

```bash
python3 -m pytest -q
```
