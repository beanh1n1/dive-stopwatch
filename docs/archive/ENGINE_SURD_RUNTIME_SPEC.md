# SURD Runtime Spec

Status: Proposed  
Parent plan: [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)  
Behavioral reference: `main` at `6d115a9`

## Purpose

Define the replacement SURD runtime as a first-class explicit state machine with:

- a hard handoff boundary from in-water runtime
- explicit surface-interval ownership
- explicit chamber segment ownership
- explicit penalty application rules
- explicit O2, Off-O2, and chamber air-break states
- pure snapshot projection from explicit state

This runtime must not remain an adapter wrapped around the AIR runtime.

## Authority Notes

Current repo authority for SURD is not perfectly clean.

- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md) still establishes manual > rule docs > scenario docs > tests > code.
- [SURFACE_ENGINE_DRAFT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SURFACE_ENGINE_DRAFT.md) documents an implemented SURD slice and its intended architecture.
- [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md) is stale for SURD and still marks `9-8.3` as out of scope.

For redesign work, the effective behavioral contract is:

- manual-backed SURD draft doc
- current SURD tests
- integrated SURD behavior in `archive/legacy_runtime/tests/test_core_engine.py`

The stale traceability row is a documentation defect, not an authority to ignore
the implemented SURD behavior.

## Source References

Primary references:

- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md)
- [SURFACE_ENGINE_DRAFT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SURFACE_ENGINE_DRAFT.md)
- `archive/legacy_runtime/tests/test_surd_engine.py`
- `archive/legacy_runtime/tests/test_core_engine.py`

Secondary references:

- [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)
- [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
- [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md)

## Scope

In scope:

- normal SURD entry from explicit `L40` handoff
- surface interval from `L40` to chamber `50`
- `> 5:00` and `> 7:00` threshold handling
- chamber `50`, `40`, and `30` O2 periods
- chamber air breaks
- chamber Off-O2 toggling
- clean-time completion
- audit and snapshot contracts

Out of scope:

- `30/20` SURD alternate entry adapter
- chamber treatment workflow after surface interval `> 7:00`
- merging SURD semantics into AIR runtime internals

## Runtime Boundary

## Ownership Rule

In-water AIR/AIR-O2 runtime remains authoritative through the `40 fsw` stop.
SURD becomes authoritative only after explicit `L40` handoff.

This seam is hard, not fuzzy.

Preserve:

- at in-water `40 fsw`, SURD mode still presents in-water stop truth
- `Next: 40 fsw -> Surface` is shown before handoff
- the handoff occurs on explicit leave-stop action at `40 fsw`
- handoff writes an explicit audit line: `SurD start from 40 fsw ...`

## Handoff Contract

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

`entry_kind` initially supports only:

- `L40_NORMAL`

Future adapter types may add:

- `DIRECT_ASCENT_NO_40`
- `FROM_30_OR_20`

The handoff is immutable input. SURD must not reach back into live AIR runtime
state after handoff.

## Operator Action Model

```python
class SurdAction(Enum):
    START_FROM_L40 = auto()
    REACH_SURFACE = auto()
    LEAVE_SURFACE = auto()
    REACH_CHAMBER_50 = auto()
    CONFIRM_ON_O2 = auto()
    TOGGLE_OFF_O2 = auto()
    ADVANCE_CHAMBER_TRANSITION = auto()
    START_AIR_BREAK = auto()
    COMPLETE_AIR_BREAK = auto()
    COMPLETE_TO_SURFACE = auto()
    RESET = auto()
```

The UI may still map this onto existing buttons. The runtime should not.

## Runtime State

```python
@dataclass(frozen=True)
class SurdRuntimeState:
    handoff: SurdHandoff | None
    phase: SurdPhase
    surface_interval: SurfaceIntervalState | None
    chamber: ChamberState | None
    penalty: SurfacePenaltyState
    clean_time: CleanTimeState | None
    audit: AuditState
    clock: ClockState
```

### SurfaceIntervalState

```python
@dataclass(frozen=True)
class SurfaceIntervalState:
    left_40_anchor: TimerAnchor
    subphase: SurfaceSubphase
    subphase_anchor: TimerAnchor
```

`SurfaceSubphase`:

- `ASCENT_40_TO_SURFACE`
- `UNDRESS`
- `SURFACE_TO_CHAMBER_50`

### ChamberState

```python
@dataclass(frozen=True)
class ChamberState:
    current_depth_fsw: int
    plan: ChamberPlan
    current_segment_index: int
    gas_mode: ChamberGasMode
    active_o2_anchor: TimerAnchor | None
    active_off_o2_anchor: TimerAnchor | None
    active_air_break_anchor: TimerAnchor | None
    paused_segment_elapsed_sec: float
```

`ChamberGasMode`:

- `WAITING_ON_O2`
- `ON_O2`
- `OFF_O2`
- `AIR_BREAK`

### ChamberPlan

```python
@dataclass(frozen=True)
class ChamberPlan:
    total_half_periods: int
    segments: tuple[ChamberSegment, ...]
    source_penalty: SurfacePenaltyKind
```

### ChamberSegment

```python
@dataclass(frozen=True)
class ChamberSegment:
    segment_index: int
    period_number: int
    depth_fsw: int
    gas: Literal["o2"]
    duration_sec: int
```

The chamber air break is modeled as runtime phase, not a plan segment, because
it is a required boundary action between O2 periods.

### SurfacePenaltyState

```python
@dataclass(frozen=True)
class SurfacePenaltyState:
    kind: SurfacePenaltyKind
    applied_at: datetime | None
```

`SurfacePenaltyKind`:

- `NONE`
- `PLUS_15_AT_50`
- `EXCEEDED_REQUIRES_TREATMENT`

## Explicit SURD Phases

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

This is intentionally flatter and more explicit than the current
`SURFACE_INTERVAL + subphase` split. The runtime phase should already tell you
what the operator is doing.

## Timer Anchor Model

Required anchor kinds:

- `SURFACE_INTERVAL`
- `SURFACE_ASCENT`
- `UNDRESS`
- `SURFACE_TO_CHAMBER`
- `SURD_O2_SEGMENT`
- `SURD_OFF_O2`
- `SURD_AIR_BREAK`
- `CLEAN_TIME`

Required stored anchors:

- `left_40_at`
- `reached_surface_at`
- `left_surface_at`
- `reached_chamber_50_at`
- `current_o2_segment_started_at`
- `off_o2_started_at`
- `current_air_break_started_at`
- `complete_started_at`

The runtime must not discover these by scanning audit text.

## Transition Contracts

## 1. Handoff

### `READY -> SURFACE_ASCENT_FROM_40`

Trigger:

- `START_FROM_L40`
- valid `SurdHandoff`

Effects:

- append audit `SurD start from 40 fsw`
- append audit `Traveling 40 -> Surface`
- create `SURFACE_INTERVAL` anchor at handoff time
- create `SURFACE_ASCENT` anchor at handoff time
- phase = `SURFACE_ASCENT_FROM_40`

## 2. Surface Interval

### `SURFACE_ASCENT_FROM_40 -> SURFACE_UNDRESS`

Trigger:

- `REACH_SURFACE`

Effects:

- append audit `RS`
- append audit `Undress`
- preserve the original surface-interval anchor
- create `UNDRESS` anchor
- phase = `SURFACE_UNDRESS`

### `SURFACE_UNDRESS -> SURFACE_TO_CHAMBER_50`

Trigger:

- `LEAVE_SURFACE`

Effects:

- append audit `LS`
- append audit `Traveling Surface -> Chamber 50`
- preserve original surface-interval anchor
- create `SURFACE_TO_CHAMBER` anchor
- phase = `SURFACE_TO_CHAMBER_50`

### `SURFACE_TO_CHAMBER_50 -> CHAMBER_AT_50_WAITING_O2`

Trigger:

- `REACH_CHAMBER_50`

Effects:

- append audit `RB`
- append audit `Chamber 50`
- evaluate surface-interval penalty
- build chamber plan
- phase = `CHAMBER_AT_50_WAITING_O2`

## Surface-interval timing contract

The primary SURD timer is the surface interval:

- basis: `left_40_at -> reached_chamber_50_at`
- `L40` starts it immediately
- it remains the authoritative basis for penalty evaluation

### Current modeled first-minute contract

Preserve current behavior:

- the first `60` seconds of the interval are treated as planned ascent
  `40 -> Surface`
- after `30` seconds, snapshot can show `20 fsw`
- chamber arrival cannot occur before that first minute elapses

This is already test-backed and should remain explicit in state rather than
being recreated in display code.

## 3. Penalty Application

### Thresholds

- `<= 5:00`: normal path
- `> 5:00` and `<= 7:00`: penalty path
- `> 7:00`: exceeded path

### Normal path

Effects:

- `penalty.kind = NONE`
- chamber plan built from normal surface profile

### Penalty path

Effects:

- `penalty.kind = PLUS_15_AT_50`
- append audit `Surface interval penalty (+15 O2 @ 50)`
- chamber plan is rebuilt with:
  - one extra half-period
  - first `50 fsw` segment increased from `15 min` to `30 min`

This is not a UI-only warning. It changes the authoritative chamber plan.

### Exceeded path

Effects:

- `penalty.kind = EXCEEDED_REQUIRES_TREATMENT`
- snapshot marks normal SURD path as exceeded
- normal chamber-progression workflow must not silently continue as if it were
  the `+15 @ 50` path

The separate chamber-treatment workflow is out of scope for this spec, but the
runtime must represent this state explicitly.

## 4. Chamber Entry and O2 Start

### `CHAMBER_AT_50_WAITING_O2 -> CHAMBER_ON_O2`

Trigger:

- `CONFIRM_ON_O2`

Effects:

- append audit `On O2 50`
- append audit `50 fsw O2`
- create `SURD_O2_SEGMENT` anchor
- chamber gas mode = `ON_O2`
- phase = `CHAMBER_ON_O2`

Forbidden:

- O2 period timing cannot start on chamber arrival alone

## 5. Chamber O2 Progression

### First period split contract

The first O2 period is not one generic block. Preserve current behavior:

- first segment: `15 min @ 50 fsw`
- second segment: `15 min @ 40 fsw`
- movement `50 -> 40` requires explicit operator action after the first segment
  completes

### `CHAMBER_ON_O2` at first `50 fsw` segment completion

Trigger:

- current segment elapsed >= planned duration

Effects:

- snapshot must expose `Next: Move chamber to 40 fsw`
- next action label must be `Chamber 40`
- runtime does not auto-advance

### `CHAMBER_ON_O2` move to `40 fsw`

Trigger:

- `ADVANCE_CHAMBER_TRANSITION`
- next required move is `50 -> 40`

Effects:

- append audit `Chamber 40`
- append audit `40 fsw O2`
- advance current chamber segment
- create new `SURD_O2_SEGMENT` anchor at move time
- phase remains `CHAMBER_ON_O2`

### Period completion with later air break required

At the end of the first `40 fsw` segment and later `40/30` O2 periods that
require a chamber air break:

- snapshot must surface `Next: Start air break`
- next action label must be `Start Air Break`
- runtime must not auto-start the break

## 6. Chamber Air Break

### `CHAMBER_ON_O2 -> CHAMBER_AIR_BREAK`

Trigger:

- `START_AIR_BREAK`

Effects:

- append audit `Air break start`
- append audit `40 fsw Air Break` or `30 fsw Air Break`
- create `SURD_AIR_BREAK` anchor
- chamber gas mode = `AIR_BREAK`
- phase = `CHAMBER_AIR_BREAK`

### Chamber air-break contract

Preserve:

- fixed duration `5 min`
- primary timer shows air-break elapsed
- detail line shows `Air elapsed | remaining left`
- early completion is not allowed

### `CHAMBER_AIR_BREAK -> CHAMBER_ON_O2`

Trigger:

- `COMPLETE_AIR_BREAK`
- at least `5 min` elapsed
- next action is resume on same depth

Effects:

- append audit `On O2 <depth>`
- append audit `<depth> fsw O2`
- create new `SURD_O2_SEGMENT` anchor
- chamber gas mode = `ON_O2`
- phase = `CHAMBER_ON_O2`

### `CHAMBER_AIR_BREAK` move to `30 fsw`

For plans that require periods beyond `4`:

- `40 -> 30` is offered only during an air break
- movement requires explicit `ADVANCE_CHAMBER_TRANSITION`
- after moving to `30`, the runtime remains in `CHAMBER_AIR_BREAK`
- resuming O2 at `30` requires a second explicit action

This two-step contract is already test-backed and should remain explicit.

## 7. Off O2

Off-O2 is not the same as chamber air break.

It is an operator deviation inside a chamber O2 phase and must remain separate.

### `CHAMBER_ON_O2 -> CHAMBER_OFF_O2`

Trigger:

- `TOGGLE_OFF_O2`

Effects:

- append audit `Off O2`
- capture elapsed segment time into `paused_segment_elapsed_sec`
- create `SURD_OFF_O2` anchor
- chamber gas mode = `OFF_O2`
- phase = `CHAMBER_OFF_O2`

### `CHAMBER_OFF_O2 -> CHAMBER_ON_O2`

Trigger:

- `TOGGLE_OFF_O2`

Effects:

- append audit `On O2 <depth>`
- append audit `<depth> fsw O2`
- create new `SURD_O2_SEGMENT` anchor
- preserve paused elapsed time and remaining obligation
- clear off-O2 anchor
- chamber gas mode = `ON_O2`
- phase = `CHAMBER_ON_O2`

Forbidden:

- off-O2 time must not reduce required O2 obligation
- off-O2 must not be represented as a scheduled chamber air break

## 8. Completion

### `CHAMBER_ON_O2 -> COMPLETE_CLEAN_TIME`

Trigger:

- current segment complete
- no later air break or chamber period remains
- operator chooses `COMPLETE_TO_SURFACE`

Effects:

- append audit `RS`
- append audit `Surface`
- create `CLEAN_TIME` anchor
- phase = `COMPLETE_CLEAN_TIME`

### `COMPLETE_CLEAN_TIME -> COMPLETE_DONE`

Trigger:

- clean-time expiry observed

Effects:

- phase = `COMPLETE_DONE`

As with in-water clean time, this is a countdown completion rather than a
procedural milestone that requires operator confirmation.

## Snapshot Projection Contract

Snapshot code must be pure projection from explicit SURD state.

It must not:

- back-project SURD semantics into AIR-style inferred semantics
- discover active segment meaning by parsing audit strings
- mutate chamber plan or penalty state

### Required status contracts

Preserve these status identities:

- `40 -> Surface`
- `Undress`
- `Surface -> 50 fsw`
- `50 fsw`
- `50 fsw O2`
- `40 fsw O2`
- `30 fsw O2`
- `OFF O2`
- `40 fsw Air Break`
- `30 fsw Air Break`
- `CLEAN TIME`

### Required time-display contracts

- surface interval phases:
  - `primary_text` = elapsed surface-interval time
  - `depth_timer_text` = time remaining to `5:00`, or overdue `+mm:ss`
- chamber O2:
  - `detail_text = O2 elapsed | segment remaining`
- chamber Off-O2:
  - `detail_text = Off O2 elapsed | segment remaining`
- chamber air break:
  - `detail_text = Air elapsed | break remaining`
- clean time:
  - `primary_text = 10:00` countdown format

### Required next-action contract

`summary_text` must identify the next required operator obligation, not a vague
state description.

Examples:

- `Next: Undress`
- `Next: Surface -> 50 fsw`
- `Next: 50 fsw for 15 min`
- `Next: Move chamber to 40 fsw`
- `Next: Start air break`
- `Next: Resume O2 period 2`
- `Next: Move chamber to 30 fsw`
- `Next: Surface`
- `Next: Chamber 50 with penalty`
- `Surface interval exceeded`

### Required control-label contract

Button labels are part of the behavioral contract because they encode the next
 state transition:

- `Reach Surface`
- `Leave Surface`
- `Reach Bottom`
- `On O2`
- `Off O2`
- `Chamber 40`
- `Start Air Break`
- `Resume O2`
- `Chamber 30`
- `Reach Surface`

## Audit Contract

Audit output remains append-only secondary evidence. It is not runtime truth.

Minimum required audit lines for explicit transitions:

- `SurD start from 40 fsw`
- `Traveling 40 -> Surface`
- `RS`
- `Undress`
- `LS`
- `Traveling Surface -> Chamber 50`
- `Surface interval penalty (+15 O2 @ 50)`
- `RB`
- `Chamber 50`
- `On O2 50`
- `50 fsw O2`
- `Chamber 40`
- `40 fsw O2`
- `Air break start`
- `40 fsw Air Break`
- `Chamber 30`
- `On O2 30`
- `30 fsw O2`
- `Surface`

Audit output must remain chronological and timestamped. It must not be parsed
back into state during runtime.

## Invariants

- any non-`READY` SURD phase requires a handoff
- exactly one `SurdPhase` is active
- all surface interval phases share the same original surface-interval anchor
- `CHAMBER_AT_50_WAITING_O2` implies no active O2 anchor
- `CHAMBER_ON_O2` implies active O2 anchor and no off-O2/air-break anchor
- `CHAMBER_OFF_O2` implies active off-O2 anchor
- `CHAMBER_AIR_BREAK` implies active air-break anchor
- penalty state becomes immutable once chamber `50` is reached
- first O2 timing at `50` never starts before explicit `On O2`
- chamber air break and Off-O2 remain distinct state categories
- `40 -> 30` movement occurs only during air break on plans that require it
- final completion path does not offer a spurious extra air break

## Current Test-Backed Paths To Lock

Minimum SURD regression set:

- normal `150/45` path:
  - `L40 -> surface interval -> chamber 50 wait -> 50 O2 15 -> chamber 40 ->
    40 O2 15 -> air break 5 -> period 2 40 O2 30 -> surface`
- deeper `170/90` path:
  - includes later `40` periods and `40 -> 30` air-break transition before
    period `5`
- penalty path:
  - `> 5:00` and `<= 7:00` adds `+15 min O2 @ 50`
- exceeded path:
  - `> 7:00` surfaces exceeded state and does not masquerade as normal penalty
- Off-O2 path:
  - preserves remaining chamber O2 obligation exactly

## Deletion Guidance

The replacement SURD runtime should make these current patterns unnecessary:

- `_surface_active` as a runtime mode switch
- adapting surface snapshots back into AIR-flavored snapshot assumptions
- deriving surface-interval semantics from UI text
- treating chamber waiting-for-O2 as merely "chamber oxygen with null timestamp"

If the redesign still needs those patterns, it has preserved the wrong parts of
the current architecture.
