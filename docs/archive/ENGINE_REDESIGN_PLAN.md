# Engine Redesign Plan

Status: Proposed  
Branch: `codex/engine-redesign`  
Behavioral reference: `main` at `6d115a9` (`Stabilize SURD flow and bank runtime checkpoint`)

## Intent

This redesign is not a cleanup pass. The goal is to replace the current
runtime architecture with a smaller, more explicit engine whose truth lives in
structured state, not in inferred view logic or audit logs.

Behavior should be preserved where it is already correct on `main`, but that
preservation must come from explicit contracts and regression tests, not from
copying current code shape.

## Executive Position

The current engine architecture is serviceable as a prototype and weak as a
runtime model.

Bluntly:

- too much runtime truth is implicit instead of represented
- too much UI meaning is computed by reverse-engineering event history
- AIR/AIR-O2 and SURD do not share a clean engine abstraction
- SURD is currently a wrapper around another engine, not a first-class runtime
- snapshots are doing runtime interpretation work they should never have owned
- event logs are mixed between audit output and operational state

This is the wrong shape for a system that needs reliability, traceability, and
manual-backed timing semantics.

## Current Architectural Problems

### 1. Runtime truth is smeared across too many places

Current truth is split across:

- `EngineState.dive.phase`
- event codes like `LS`, `RB`, `R1`, `ON_O2`, `OFF_O2`
- helper inference in `_dive_view(...)`
- snapshot builders
- profile recomputation side effects
- UI log strings

This means the runtime is not truly explicit. You often have to infer what the
system "means" from a combination of fields rather than reading one concrete
state object.

### 2. Snapshot generation is compensating for an under-modeled engine

`archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_o2_snapshot.py` is not just formatting. It is
effectively recovering procedural truth from a partially implicit state model.

That is backwards.

Snapshots should render already-resolved runtime truth. They should not decide:

- which timer is authoritative
- which stop anchor applies
- whether the diver is in TSV semantics
- whether O2 continuity carries across travel
- whether "next" means air break, stop completion, or surface

If snapshot code decides that, the engine is under-specified.

### 3. Event log semantics are overloaded

The event log is currently doing at least three jobs:

- audit history
- anchor source for timer inference
- partial state reconstruction mechanism

That is a design error.

Audit logs are append-only historical records. Runtime truth should live in
state fields such as explicit phase, active timer basis, current obligation,
and current gas exposure segment.

### 4. AIR/AIR-O2 state is too phase-light and inference-heavy

`READY`, `DESCENT`, `BOTTOM`, `TRAVEL`, `AT_STOP`, `SURFACE` is too coarse for
the actual behavior being modeled.

Important distinctions are being recovered indirectly:

- travel to first stop vs travel between stops vs travel to surface
- air stop vs first O2 stop waiting state vs active O2 stop
- active air break vs off-O2 deviation vs normal O2 segment
- no-decompression ascent vs decompression ascent
- converted-air terminal stop vs standard air stop

Those distinctions are operationally real and should be explicit runtime state,
not view-level interpretation.

### 5. SURD is not modeled as a true engine

`archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime.py` currently coordinates one engine by
wrapping another, adapts one snapshot model into another, and toggles between
internal runtimes with a boolean.

That is not a clean engine boundary. It is a transitional patch.

Specific problems:

- `_surface_active` is a mode switch, not a state model
- SURD snapshot adaptation rewrites surface snapshot meaning into AIR-style
  fields after the fact
- the handoff boundary exists, but the surrounding runtime ownership is muddy
- test-time and clock semantics are duplicated across sub-engines

### 6. Top-level mode ownership is shallow and reset-heavy

`archive/legacy_runtime/src/dive_stopwatch/legacy/core/runtime.py` swaps entire engine instances on mode
change and mirrors depth/test-time state manually.

This is acceptable for a prototype UI shell and poor as a long-term runtime
boundary. It treats engines as disposable widgets instead of consistent state
machines with defined contracts.

### 7. The code encourages accidental preservation of structure

Because the current behavior mostly works, there is a natural temptation to
"keep the engine, move some helpers, add more enums." That would be a mistake.

The problem is not file placement. The problem is that runtime truth is modeled
too indirectly.

## Redesign Principles

- state must describe procedure directly
- every active timer must have an explicit anchor and purpose
- event logs are audit output only
- snapshots are projections of state, not interpreters of it
- AIR/AIR-O2 and SURD are separate state machines with a shared engine protocol
- table/profile logic remains pure data logic
- behavioral preservation comes from contracts and golden-path tests
- deletion is a feature when architecture is wrong

## Target Architecture

## High-Level Shape

Replace the current runtime with four layers:

1. `engine_protocol.py`
   Defines common engine interfaces and clock/snapshot contracts.
2. `air_runtime/`
   Explicit AIR and AIR/O2 runtime state machine.
3. `surd_runtime/`
   Explicit SURD runtime state machine.
4. `presentation/`
   Pure snapshot projection from already-explicit runtime state.

Suggested file structure:

- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/engine_protocol.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/clock.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/session_log.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_runtime/state.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_runtime/transitions.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_runtime/contracts.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_runtime/snapshot.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime/state.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime/transitions.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime/contracts.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime/snapshot.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/profiles.py`

Names can change. Separation of responsibilities should not.

## Shared Engine Protocol

Every runtime should implement the same conceptual contract:

```python
class RuntimeEngine(Protocol):
    def dispatch(self, action: OperatorAction) -> None: ...
    def snapshot(self) -> DisplaySnapshot: ...
    def recall_lines(self) -> tuple[str, ...]: ...
    def set_depth_text(self, raw: str) -> None: ...
    def advance_test_time(self, delta_seconds: float) -> None: ...
    def reset_test_time(self) -> None: ...
```

Internally, each runtime owns:

- immutable runtime state
- a monotonic clock adapter
- pure transition functions
- append-only audit events
- a snapshot projector that reads explicit state only

## Shared Concepts

The redesign should introduce explicit shared concepts instead of reusing
generic event history:

- `TimerAnchor`
- `ActiveObligation`
- `TravelSegment`
- `GasState`
- `AuditEvent`
- `DisplaySnapshot`
- `SnapshotContractVersion`

### TimerAnchor

Every visible or procedural timer must identify:

- `anchor_kind`
- `started_at`
- `paused_elapsed_sec`
- `source_action`
- `source_phase`

Examples of anchor kinds:

- `BOTTOM_TIME`
- `TRAVEL_TO_FIRST_STOP`
- `TRAVEL_BETWEEN_STOPS`
- `AIR_STOP`
- `TSV_WAIT`
- `O2_SEGMENT`
- `AIR_BREAK`
- `OFF_O2_DEVIATION`
- `CLEAN_TIME`
- `SURFACE_INTERVAL`
- `SURD_O2_SEGMENT`
- `SURD_AIR_BREAK`

If a timer matters, it must exist as data.

### ActiveObligation

Explicit runtime obligation should replace view inference.

Examples:

- `REACH_BOTTOM`
- `LEAVE_BOTTOM_FOR_ASCENT`
- `REACH_STOP(index=1)`
- `COMPLETE_STOP(index=1)`
- `CONFIRM_ON_O2(stop_index=3)`
- `START_AIR_BREAK`
- `COMPLETE_AIR_BREAK`
- `RESUME_O2`
- `CONVERT_CURRENT_O2_STOP_TO_AIR`
- `REACH_SURFACE`
- `REACH_CHAMBER_50`
- `MOVE_CHAMBER_TO_40`
- `MOVE_CHAMBER_TO_30`

The snapshot `Next:` line should be derived from `ActiveObligation`, not from
ad hoc branching.

## AIR/AIR-O2 Runtime Model

## Runtime Ownership

One engine should own both AIR and AIR/O2 behavior. The selected table mode is
configuration, not a separate architecture.

## Proposed AIR/AIR-O2 State

```python
@dataclass(frozen=True)
class DiveRuntimeState:
    mode: DecoMode  # AIR or AIR/O2
    depth_input: DepthInputState
    plan: DivePlanState | None
    phase: DivePhaseState
    timing: DiveTimingState
    gas: DiveGasState
    delays: DelayTrackingState
    audit: AuditTrail
    clock: ClockState
```

Suggested sub-objects:

- `DepthInputState`
  - raw text
  - parsed depth
  - supported depth
- `DivePlanState`
  - input depth/bottom time
  - resolved table row
  - resolved stop list
  - no-decompression flag
  - delay-adjusted plan version
  - original-plan reference
- `DiveTimingState`
  - bottom anchor
  - active travel anchor
  - active stop anchor
  - clean-time anchor
- `DiveGasState`
  - breathing gas now
  - O2 continuity state
  - active O2 segment anchor
  - active off-O2 deviation anchor
  - active air-break anchor
  - paused stop elapsed
- `DelayTrackingState`
  - active delay
  - last applied delay result
  - delay counter

## Proposed AIR/AIR-O2 Phases

Replace the coarse current phase enum with procedure-specific states.

```python
class DivePhase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    TRAVEL_BETWEEN_STOPS = auto()
    TRAVEL_TO_SURFACE = auto()
    AT_AIR_STOP = auto()
    AT_O2_STOP_WAITING = auto()
    AT_O2_STOP_ON_O2 = auto()
    AT_O2_STOP_OFF_O2 = auto()
    AT_O2_STOP_AIR_BREAK = auto()
    SURFACE_CLEAN_TIME = auto()
    SURFACE_COMPLETE = auto()
```

This is intentionally more explicit. The runtime should not need to ask
"at_stop plus oxygen flags plus next_stop equals what?"

It should already know.

## AIR/AIR-O2 Transitions

Core transition types:

- `READY -> DESCENT` on `LS`
- `DESCENT -> BOTTOM` on `RB`
- `BOTTOM -> TRAVEL_TO_FIRST_STOP` on `LB` when decompression required
- `BOTTOM -> TRAVEL_TO_SURFACE` on `LB` when no-decompression
- `TRAVEL_TO_* -> AT_*` on explicit arrival
- `AT_AIR_STOP -> TRAVEL_*` on stop completion/departure
- `AT_O2_STOP_WAITING -> AT_O2_STOP_ON_O2` on O2 confirmation
- `AT_O2_STOP_ON_O2 -> AT_O2_STOP_OFF_O2` on Off O2
- `AT_O2_STOP_OFF_O2 -> AT_O2_STOP_ON_O2` on On O2 resume
- `AT_O2_STOP_ON_O2 -> AT_O2_STOP_AIR_BREAK` on air-break start
- `AT_O2_STOP_AIR_BREAK -> AT_O2_STOP_ON_O2` on air-break completion
- terminal travel -> `SURFACE_CLEAN_TIME`
- `SURFACE_CLEAN_TIME -> SURFACE_COMPLETE` after clean-time expiry

Delay application must be an explicit state transition, not a hidden profile
repair step attached to generic dispatch.

## Explicit AIR/AIR-O2 Timer Anchors

The AIR/AIR-O2 runtime must carry these anchors explicitly when active:

- `ls_at`
  Basis for descent and bottom elapsed time.
- `bottom_departed_at`
  Basis for travel-to-first-stop timing.
- `travel_started_at`
  Basis for travel between obligations.
- `stop_started_at`
  Basis for current stop timing.
- `tsv_started_at`
  Basis for first O2 waiting display/semantics.
- `o2_segment_started_at`
  Basis for active O2 elapsed time.
- `air_break_started_at`
  Basis for active air-break elapsed time.
- `off_o2_started_at`
  Basis for deviation elapsed time.
- `surface_reached_at`
  Basis for clean time.

No visible timer should be reconstructed from "latest event with code X" once
the redesign is complete.

## AIR/AIR-O2 Explicit O2 Model

Current `OxygenState` is too small and too ambiguous.

Replace it with a stronger state model:

```python
@dataclass(frozen=True)
class O2ExposureState:
    mode: Literal["not_applicable", "awaiting_first_o2", "on_o2", "off_o2", "air_break"]
    current_stop_index: int | None
    current_stop_depth_fsw: int | None
    first_o2_confirmed_at: datetime | None
    continuous_o2_anchor_at: datetime | None
    current_segment_started_at: datetime | None
    off_o2_started_at: datetime | None
    air_break_started_at: datetime | None
    paused_stop_elapsed_sec: float
```

Key rule:

- O2 continuity is state, not inference.

The engine must explicitly know whether O2 continuity carries through travel,
whether the diver is in a pause/deviation state, and whether the current
obligation is an air break or resumed O2 segment.

## SURD Runtime Model

## Runtime Ownership

SURD must become a first-class state machine. It should not be an AIR engine
plus a surface engine plus an adapter layer pretending they are one runtime.

## Proposed SURD Boundary

The in-water runtime should produce a single immutable handoff object. After
handoff, SURD owns the session completely.

```python
@dataclass(frozen=True)
class SurdHandoff:
    entry_kind: SurdEntryKind
    source_mode: DecoMode
    source_plan_summary: str
    source_depth_fsw: int
    source_bottom_time_min: int
    source_table_depth_fsw: int | None
    source_table_bottom_time_min: int | None
    left_water_stop_depth_fsw: int | None
    remaining_in_water_obligation_sec: float | None
    handed_off_at: datetime
    audit_tail: tuple[AuditEvent, ...]
```

That handoff is an input contract, not shared mutable state.

## Proposed SURD State

```python
@dataclass(frozen=True)
class SurdRuntimeState:
    handoff: SurdHandoff | None
    phase: SurdPhase
    surface_interval: SurfaceIntervalState | None
    chamber: ChamberState | None
    penalty: SurfacePenaltyState
    audit: AuditTrail
    clock: ClockState
```

Suggested chamber state:

- chamber depth now
- chamber plan segments
- current segment index
- current segment gas mode
- active O2 anchor
- active Off O2 anchor
- active air-break anchor

## Proposed SURD Phases

```python
class SurdPhase(Enum):
    READY = auto()
    SURFACE_ASCENT_FROM_40 = auto()
    SURFACE_UNDRESS = auto()
    SURFACE_TO_CHAMBER_50 = auto()
    CHAMBER_AT_50_WAITING_O2 = auto()
    CHAMBER_ON_O2 = auto()
    CHAMBER_OFF_O2 = auto()
    CHAMBER_AIR_BREAK = auto()
    COMPLETE_CLEAN_TIME = auto()
    COMPLETE_DONE = auto()
```

This is better than nesting a generic `SURFACE_INTERVAL` phase with a subphase,
because the phase itself should tell you what the operator is actually doing.

The existing `SurfacePhase + SurfaceIntervalSubphase` split is not terrible, but
it still hides direct procedure state behind combinations.

## Explicit SURD Timer Anchors

SURD must make these anchors first-class:

- `left_40_at`
- `reached_surface_at`
- `left_surface_at`
- `reached_chamber_50_at`
- `current_o2_segment_started_at`
- `off_o2_started_at`
- `current_air_break_started_at`
- `complete_started_at`

The surface interval must be represented as a named timer contract:

- basis: `left_40_at -> reached_chamber_50_at`
- warning threshold: `> 5:00`
- penalty threshold: `> 7:00`
- penalty application result: explicit field, not snapshot branch logic

## Explicit SURD Chamber Model

The chamber plan should be data, not prose hidden in snapshot helpers.

```python
@dataclass(frozen=True)
class ChamberSegment:
    segment_index: int
    period_number: int
    depth_fsw: int
    gas: Literal["o2", "air_break"]
    planned_duration_sec: int
```

The active chamber state should include:

- current segment identity
- gas mode now
- elapsed-in-segment
- remaining-in-segment
- whether user confirmation is required before advancing

SURD "waiting for On O2 at 50" must be its own explicit phase, not a chamber
oxygen phase with a missing timestamp.

## Invariants

The redesign should encode invariants in transition functions and tests.

### Cross-Cutting Invariants

- exactly one runtime phase is active at a time
- active phase implies at most one primary authoritative timer
- every visible timer must map to a concrete timer anchor
- `Next:` must come from explicit obligation state
- audit log append order must be chronological
- audit events never determine phase by themselves

### AIR/AIR-O2 Invariants

- `DESCENT` and `BOTTOM` require `ls_at`
- `BOTTOM` cannot exist without resolved bottom-time context
- `AT_AIR_STOP` requires current stop = air stop
- `AT_O2_STOP_WAITING` requires current stop = first O2 stop and no O2 active
- `AT_O2_STOP_ON_O2` requires active O2 anchor and no off-O2/air-break anchor
- `AT_O2_STOP_OFF_O2` requires off-O2 anchor and paused stop elapsed state
- `AT_O2_STOP_AIR_BREAK` requires air-break anchor and no active off-O2 anchor
- if phase is travel, current stop anchor is absent
- if phase is stop, travel anchor is absent
- delay recompute results must be stored explicitly when they alter the plan

### SURD Invariants

- any non-`READY` SURD phase requires a handoff
- surface interval phases require `left_40_at`
- `CHAMBER_AT_50_WAITING_O2` requires chamber depth 50 and no O2 anchor
- `CHAMBER_ON_O2` requires active chamber O2 segment
- `CHAMBER_OFF_O2` requires active off-O2 anchor and retained segment remaining
- `CHAMBER_AIR_BREAK` requires active air-break segment
- penalty state is immutable once chamber 50 is reached

## Event Log Role

The event log should be demoted to what it ought to be:

- append-only audit output
- operator trace
- diagnosis aid
- regression artifact

The event log should not be:

- the source of active timer anchors
- the source of current phase truth
- the source of O2 continuity truth
- the source of "next action" truth

Recommended event model:

```python
@dataclass(frozen=True)
class AuditEvent:
    code: str
    at: datetime
    payload: Mapping[str, str | int | float | None]
    message: str
```

Store structured payloads first. Render text lines second.

## Snapshot / Display Contract Role

Snapshots should become strict projection contracts from runtime state to UI.

## Snapshot Rules

- snapshot code is pure
- snapshot code does not mutate runtime
- snapshot code does not rebuild plans
- snapshot code does not search event history to discover anchors
- snapshot code does not decide what phase the runtime is "really in"

## Snapshot Contract Shape

The current `Snapshot` type can survive conceptually, but it should be backed by
more explicit runtime data and probably tightened.

Suggested conceptual contract:

```python
@dataclass(frozen=True)
class DisplaySnapshot:
    mode_text: str
    status: DisplayField
    primary_timer: DisplayTimer
    depth: DisplayField
    depth_timer: DisplayTimer | None
    next_action: DisplayField
    detail: DisplayField | None
    controls: ControlSnapshot
    schedule_text: str
```

This is not mainly about type beauty. It is about making display roles explicit
and reducing stringly-typed meaning.

## What To Keep

These parts are probably worth keeping, though not necessarily in current file
form:

- decompression table CSVs in `docs/`
- pure table parsing and profile construction logic from
  `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_o2_profiles.py`
- scenario and rule docs as authority/traceability references
- parity and smoke tests as behavioral references
- test-time clock idea

Keep the data and the behavioral reference. Do not keep the current runtime
shape just because those references exist.

## What To Rewrite

These should be rewritten, not incrementally massaged:

- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_o2_engine.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/air_o2_snapshot.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_runtime.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_engine.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/surd_snapshot.py`
- `archive/legacy_runtime/src/dive_stopwatch/legacy/core/runtime.py`

Why:

- they encode too much meaning through combinations of fields and event lookup
- they mix runtime, audit, and presentation concerns
- they will fight every attempt at simplification if treated as a base

## What To Throw Away

Likely delete outright once the replacement is ready:

- `_dive_view(...)` style inference helpers
- snapshot logic that derives active timer meaning from event searches
- the boolean `_surface_active` split runtime pattern
- SURD snapshot adaptation that back-projects chamber/surface state into AIR-like
  snapshot assumptions
- any logic that treats `ui_log` strings as meaningful runtime evidence

If a helper exists only to recover meaning that a proper state machine could
store directly, that helper is a symptom and should be removed.

## Migration Phases

## Phase 0: Freeze Behavioral Reference

- treat `6d115a9` on `main` as the behavioral reference
- catalog core golden paths for AIR, AIR/O2, and SURD
- identify known intentional mismatches vs manual authority
- do not start engine rewrites until behavior locks exist

Deliverable:

- golden-path regression inventory document/tests

## Phase 1: Define Contracts Before Code

- define `DisplaySnapshot` contract
- define audit event schema
- define AIR/AIR-O2 phase enums and transition table
- define SURD phase enums and transition table
- define timer-anchor schema
- define handoff schema

Deliverable:

- contract docs and transition diagrams or tables

## Phase 2: Build New AIR/AIR-O2 Engine Beside Old One

- create new explicit AIR/AIR-O2 runtime in parallel
- keep old engine untouched as comparison oracle
- write transition-level tests against the new runtime
- project snapshots from explicit state only

Deliverable:

- new AIR/AIR-O2 engine passing golden-path regression suite

## Phase 3: Build New SURD Engine Beside Old One

- implement immutable handoff from new AIR runtime
- implement explicit SURD surface/chamber state machine
- replace subphase/inference patterns with direct phases
- lock penalty and chamber-period behavior via golden-path tests

Deliverable:

- new SURD engine passing regression suite

## Phase 4: Switch Top-Level Runtime Shell

- replace mode-cycling shell with new engine protocol
- preserve UI-facing controls and snapshot contract
- keep stopwatch isolated as a separate trivial runtime

Deliverable:

- one top-level coordinator with uniform runtime ownership

## Phase 5: Delete Legacy Engine

- remove legacy runtime modules
- remove adapter shims
- remove dead inference helpers
- simplify tests to target contracts instead of legacy structure

Deliverable:

- no legacy runtime code on the main execution path

## Golden-Path Regression Lock Strategy

Behavior preservation should be contract-driven and scenario-driven.

## Lock Categories

1. Phase progression
   - ready -> descent -> bottom -> travel -> stop -> surface
2. Timer basis
   - each screen timer uses the correct anchor
3. Next-action semantics
   - `Next:` always reflects the immediate obligation
4. O2 semantics
   - first O2 wait, On O2, Off O2, air break, continuity through travel
5. Delay semantics
   - delay start/end, recompute outcomes, first-stop and O2-specific rules
6. SURD handoff and chamber flow
   - L40 handoff, surface interval, penalties, chamber segment progression
7. Audit output
   - key event codes/messages remain traceable and chronological

## Regression Method

- keep current parity tests as initial protection
- add scenario fixtures that record a sequence of operator actions and expected
  snapshots/events at each checkpoint
- for critical flows, compare new-engine snapshots against banked reference
  outputs from `6d115a9`
- prefer explicit scenario fixtures over giant ad hoc tests

## Recommended Golden Paths

- AIR no-decompression dive to clean time
- AIR decompression dive with first stop delay
- AIR/O2 dive with first O2 stop after a 40 fsw air stop
- AIR/O2 dive whose first stop is already O2
- AIR/O2 terminal 20 fsw air-break boundary case
- AIR/O2 Off O2 and resume on same stop
- SURD normal L40 -> surface -> chamber -> complete path
- SURD surface interval penalty path

## Non-Goals During Redesign

- no casual new features
- no UI redesign bundled into engine work
- no expansion of manual scope unless needed to preserve current behavior
- no attempt to keep old helper structure "for familiarity"

## Risks

### Risk: preserving text while changing meaning

Mitigation:

- assert timer basis and obligation identity, not just labels

### Risk: under-specifying transition contracts

Mitigation:

- write transition tables before implementation

### Risk: partial migration leaves two truth systems

Mitigation:

- run old and new engines in parallel only during migration; delete old code as
  soon as replacement is verified

### Risk: SURD remains an adapter because it is "working enough"

Mitigation:

- explicitly forbid keeping `_surface_active`-style architecture

## Immediate Next Steps

1. Define explicit AIR/AIR-O2 transition table and state schema in a follow-up
   design doc.
2. Define explicit SURD transition table and handoff contract in a follow-up
   design doc.
3. Build golden-path scenario fixtures from `main` behavior before rewriting the
   engine.
4. Start the new AIR/AIR-O2 runtime beside the old one, not inside it.

## Final Recommendation

Do not evolve the current engine by accretion.

Keep:

- tables
- docs
- tests
- behavior

Replace:

- runtime state model
- transition architecture
- snapshot architecture
- SURD ownership model

The current codebase has enough correct behavior to serve as a reference and not
enough architectural clarity to serve as a foundation.
