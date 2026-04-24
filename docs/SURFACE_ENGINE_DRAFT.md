# Surface Decompression Engine Draft

Status: Draft

Primary authority:
- `9-8.3`, pp. 9-15 to 9-16
- `9-8.3.1`, pp. 9-15 to 9-16
- `9-8.3.2`, p. 9-19
- `9-12.6` for the >5 min surface interval penalty path

## Purpose

This document defines the first clean architecture for a Surface Decompression
(`SurD`) runtime without destabilizing the existing in-water AIR/AIR-O2 core.

The current in-water runtime is now explicitly represented by:

- `src/dive_stopwatch/core/air_o2_engine.py`
- `src/dive_stopwatch/core/air_o2_snapshot.py`
- `src/dive_stopwatch/core/air_o2_profiles.py`

Surface decompression should be added as a sibling runtime, not as another layer
of branching inside the current AIR/AIR-O2 engine.

## Design Goals

- preserve the current AIR/AIR-O2 core contract
- keep `SurD` workflow state separate from in-water workflow state
- share only pure data and table helpers where the rules are genuinely common
- make the in-water -> surface handoff explicit and auditable
- keep future chamber-mode expansion possible without rewriting the handoff

## Non-Goals

- do not merge `SurD` state into `air_o2_engine.py`
- do not overload current `Intent.PRIMARY` / `Intent.SECONDARY` semantics to mean
  both in-water and surface actions
- do not duplicate AIR/AIR-O2 table parsing unless SurD-specific math proves it
  necessary

## Proposed Files

- `src/dive_stopwatch/core/surd_engine.py`
- `src/dive_stopwatch/core/surd_snapshot.py`

Possible later additions:

- `src/dive_stopwatch/core/surface_profiles.py`
- `src/dive_stopwatch/core/chamber_engine.py`
- `src/dive_stopwatch/core/recovery.py`

## Shared vs Separate Responsibilities

### Shared

Keep these shared with the current runtime unless SurD rules force divergence:

- CSV loading
- base table row types
- profile stop types if still semantically correct
- formatting helpers that are display-neutral

Current shared candidate:

- `src/dive_stopwatch/core/air_o2_profiles.py`

### Separate

These should be SurD-specific from the start:

- state machine phases
- operator actions / intents
- event codes and event-log wording
- snapshot composition
- handoff processing
- chamber / deck / mask / interval workflow timing

## Manual-Backed Pivot

The manual suggests a better core than my first draft:

- normal SurDO2 does **not** begin at generic "surface arrival"
- the primary SurDO2 timing seam is the **surface interval**
- the surface interval is defined as:
  - from leaving the `40 fsw` water stop
  - to arriving at `50 fsw` in the chamber

Manual basis:
- `9-8.3`: "start timing the surface interval when the diver leaves 40 fsw"
- `9-8.3.1(4)`: "The surface interval is the elapsed time from the time the diver leaves the 40 fsw water stop to the time the diver arrives at 50 fsw in the chamber"

This leads to a cleaner architecture:

- keep `L40` as the normal SurDO2 handoff trigger
- treat `30/20 fsw` surface decompression as a separate entry adapter, not as the
  primary phase model
- center the SurD runtime on:
  - surface interval
  - chamber oxygen periods
  - chamber air breaks

## Proposed Runtime Boundary

### In-Water Runtime

The current runtime remains authoritative for:

- bottom timing
- in-water stop timing
- O2 shifts
- air breaks
- `Off O2`
- `Convert to Air`
- delay corrections
- surface arrival

### Surface Runtime

The new runtime becomes authoritative only after an explicit handoff from the
in-water engine.

That handoff should be represented as immutable input data, not by sharing
mutable state objects.

## Proposed Handoff Object

```python
@dataclass(frozen=True)
class SurfaceHandoff:
    entry_kind: str
    source_mode: str
    source_profile_schedule_text: str
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int | None
    table_bottom_time_min: int | None
    current_stop_depth_fsw: int | None
    remaining_stop_sec: float | None
    event_log: tuple[str, ...]
    handed_off_at: datetime
```

This keeps the seam explicit:

- whether entry was:
  - normal `L40` handoff
  - no-`40` direct ascent handoff
  - contingency `30/20` handoff
- what schedule we came from
- what stop/depth we left
- how much obligation remained
- when the surface workflow started
- what event history supports later diagnosis

## Proposed Surface Phases

These should be shaped around the manual’s timing anchors, not copied from the
in-water runtime.

```python
class SurfacePhase(Enum):
    READY = auto()
    SURFACE_INTERVAL = auto()
    CHAMBER_DESCENT = auto()
    CHAMBER_OXYGEN = auto()
    CHAMBER_AIR_BREAK = auto()
    COMPLETE = auto()
```

Notes:

- `SURFACE_INTERVAL` is the key manual-defined timer:
  - `L40 -> arrive 50 fsw chamber`
- `CHAMBER_DESCENT` may be a very short explicit subphase or may later fold into
  `SURFACE_INTERVAL`; keep it separate only if the implementation benefits.
- `CHAMBER_OXYGEN` maps to the manual oxygen periods at `50`, `40`, and later
  `30 fsw`.
- `CHAMBER_AIR_BREAK` is separate because chamber air breaks are first-class
  schedule elements.

## Entry Modes

The manual strongly implies two different entry patterns:

1. Normal SurDO2 entry
   - complete in-water air schedule through `40 fsw`
   - handoff starts at `L40`

2. Surface decompression from `30/20`
   - `9-8.3.2`
   - contingency / supervisor-elected conversion during later in-water stops

Recommendation:

- build the first SurD runtime around **normal `L40` entry**
- treat `30/20` entry as a later adapter that computes chamber periods and then
  hands off into the same chamber-period engine

## Proposed Surface Intents

```python
class SurfaceIntent(Enum):
    PRIMARY = auto()
    SECONDARY = auto()
    MODE = auto()
    RESET = auto()
    HANDOFF = auto()
```

The button mapping can stay abstract for now. What matters is that surface
semantics are not forced through the in-water action names.

Expected concrete actions later:

- start SurD from `L40`
- confirm chamber arrival at `50`
- start O2 period
- start air break
- resume O2
- complete chamber schedule

## Proposed Engine State

```python
@dataclass(frozen=True)
class SurfaceEvent:
    code: str
    timestamp: datetime


@dataclass(frozen=True)
class SurfaceState:
    phase: SurfacePhase = SurfacePhase.READY
    handoff: SurfaceHandoff | None = None
    events: tuple[SurfaceEvent, ...] = ()
    ui_log: tuple[str, ...] = ()
    test_time_offset_sec: float = 0.0
```

This should remain intentionally smaller than the in-water state until SurD
timing rules are nailed down from the manual.

Additional likely fields:

- `surface_interval_started_at`
- `chamber_arrived_at`
- `current_period_index`
- `current_period_depth_fsw`
- `remaining_period_sec`

## Proposed Snapshot Contract

The snapshot can mirror the broad shape of the current runtime without copying
all AIR/AIR-O2 semantics:

```python
@dataclass(frozen=True)
class SurfaceSnapshot:
    mode_text: str
    status_text: str
    primary_text: str
    depth_text: str
    summary_text: str
    detail_text: str
    primary_button_label: str
    secondary_button_label: str
    primary_button_enabled: bool
    secondary_button_enabled: bool
```

Why keep it smaller first:

- the in-water snapshot earned its complexity over many protocol branches
- SurD should start with only the fields it clearly needs
- we can expand later if the real workflow demands it

## Integration Strategy

### Step 1

Add the new files only:

- `surd_engine.py`
- `surd_snapshot.py`

No GUI wiring yet.

### Step 2

Define the first explicit handoff trigger from the in-water runtime:

- normal path:
  - `L40`
- special path:
  - no-`40` air schedule, where the manual says to surface without stops and
    begin surface decompression
- later path:
  - `30/20` supervisor-elected SurD under `9-8.3.2`

### Step 3

Build a minimal fake-free SurD happy path:

- handoff accepted
- surface phase changes
- event log updates
- snapshot updates

### Step 4

Only after that, wire a new mode/router path in the UI.

## Why This Is The Right Seam

This split keeps the existing AIR/AIR-O2 runtime safe:

- no new SurD-specific branches in `air_o2_engine.py`
- no new chamber/display semantics in `air_o2_snapshot.py`
- no forced duplication of current logic until it proves necessary

It also creates a natural expansion path:

- current in-water runtime
- future surface runtime
- future chamber runtime

without making one engine pretend to be all three at once.

The most important manual-aligned design decision is this:

- **normal SurDO2 entry is an `L40` handoff**
- **the primary SurDO2 timer is the surface interval from `L40` to chamber `50`**
- **`30/20` SurD is an alternate entry adapter, not the default state machine**

## Current Implemented Slice

The current SurD runtime intentionally implements only the first bounded
workflow:

- `L40` starts the surface interval timer
- the first `60 seconds` of that interval are treated as the planned
  `40 fsw -> surface` ascent at `40 fsw/min`
- the surface interval now explicitly tracks three distinct subphases:
  - `40 fsw -> surface`
  - `undress`
  - `surface -> chamber 50`
- chamber arrival at `50 fsw` is not allowed before that first minute elapses
- the `5:00` surface interval maximum is surfaced explicitly in snapshot/logging
- if chamber arrival is confirmed after `5:00`, the runtime flags the penalty
  path without yet applying the `>5 min` recompute logic

This is the current architectural pivot:

- keep the whole `L40 -> chamber 50` path inside a single `SURFACE_INTERVAL`
  phase for now
- model the three distinct manual-relevant surface subphases as deterministic
  sub-timers inside `SURFACE_INTERVAL`, not as separate top-level runtime phases
- defer real chamber-period progression until this seam is fully stable

## Chamber O2 Pivot

The next manual-backed pivot is the same pattern:

- keep top-level phases coarse
  - `CHAMBER_OXYGEN`
  - `CHAMBER_AIR_BREAK`
- model oxygen-period structure as internal chamber state, not as extra top-level
  phases

Current implemented chamber slice:

- chamber arrival starts `CHAMBER_OXYGEN`
- the first oxygen period is modeled as two explicit internal segments:
  - `15 min at 50 fsw`
  - `15 min at 40 fsw`
- `50 -> 40` is treated as an internal transition within the first O2 period
  but it still requires explicit operator input once the `50 fsw` segment is
  complete
- later periods at `40 fsw` and `30 fsw` are intentionally deferred
- `40 -> 30` descent is intentionally deferred to `CHAMBER_AIR_BREAK`, because
  the manual places that movement during an air break

Current implemented air-break slice:

- after the first `40 fsw` O2 segment completes, the runtime does not
  auto-advance
- snapshot surfaces `Start Air Break` as the next required action
- starting the air break requires explicit operator input
- the chamber air break is currently modeled as `5 min on air`
- after `5 min`, snapshot surfaces `Resume O2 period 2`
- resuming O2 again requires explicit operator input
- period `2` then begins at `40 fsw`

Current implemented `40 -> 30` slice:

- the runtime only offers `40 -> 30` during a chamber air break
- it is offered only when the table requires periods beyond `4`
- the move to `30 fsw` requires explicit operator input
- after the move, the runtime remains in `CHAMBER_AIR_BREAK`
- resuming O2 at `30 fsw` is a second explicit operator action
- the transition is therefore modeled as:
  - complete period `4` at `40`
  - start air break
  - complete air break
  - `Chamber 30`
  - `Resume O2 period 5`

Current implemented `9-12.6(1)` slice:

- if the surface interval exceeds `5:00` but is `<= 7:00`, chamber arrival
  applies the normal penalty path
- that penalty is modeled by rebuilding the `SURD chamber plan` with:
  - one extra half period
  - the first `50 fsw` segment increased from `15 min` to `30 min`
- snapshot surfaces the pending penalty before chamber arrival
- event log records the applied penalty at chamber arrival
- ascent to `40 fsw` still occurs during the subsequent air break, because the
  penalized chamber plan keeps the extra time inside the `50 fsw` segment

Important deferred branch:

- if the surface interval exceeds `7:00`, the runtime should not continue on the
  normal SurD penalty path
- that branch should initiate the chamber treatment protocol instead
- this is intentionally deferred and should be built as a separate, explicit
  workflow later

## Advancement Rule

The runtime should preserve the same core discipline as the in-water engine:

- no phase or chamber segment advances without explicit user input
- timers may indicate that a segment is complete
- snapshot may expose the next required action
- but state advancement still requires an operator action
