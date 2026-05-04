# AIR / AIR-O2 Runtime Spec

Status: Proposed  
Parent plan: [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)  
Behavioral reference: `main` at `6d115a9`

## Purpose

Define the replacement in-water runtime for `AIR` and `AIR/O2` as an explicit
state machine with:

- explicit runtime phases
- explicit timer anchors
- explicit stop and gas semantics
- explicit delay application contracts
- explicit snapshot projection inputs

This spec is not constrained by current internal structure. It is constrained by
manual-backed rules, current product behavior on `main`, and the redesign goal
of making runtime truth explicit.

## Source References

Primary references:

- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md)
- [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md)
- [RULE_display_and_timer_semantics.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_display_and_timer_semantics.md)
- [RULE_delay_corrections.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_delay_corrections.md)
- [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
- [SCENARIO_air_o2_150_40.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_air_o2_150_40.md)
- [SCENARIO_first_o2_stop_after_air_stop.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_first_o2_stop_after_air_stop.md)
- [SCENARIO_first_o2_stop_from_bottom.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_first_o2_stop_from_bottom.md)
- [SCENARIO_terminal_20fsw_air_break.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_terminal_20fsw_air_break.md)
- [SCENARIO_delay_boundaries.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_delay_boundaries.md)
- [SCENARIO_mixed_stop_anchor_chain.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_mixed_stop_anchor_chain.md)
- `archive/legacy_runtime/tests/test_core_engine.py`
- `tests/test_v2_parity_p0.py`
- `tests/test_v2_parity_p1.py`
- `tests/test_v2_parity_p2.py`
- `tests/test_v2_smoke.py`

## Scope

In scope:

- `AIR` in-water runtime
- `AIR/O2` in-water runtime
- depth input and table lookup
- bottom timing
- decompression stop progression
- first-O2 and continuous-O2 semantics
- air-break semantics
- off-O2 semantics
- delay detection and schedule adjustment
- clean-time transition
- audit event output
- snapshot projection contract

Out of scope:

- stopwatch runtime
- SURD runtime after handoff
- omitted-stop recovery workflows
- repetitive-dive / residual-nitrogen workflows
- autonomous sensor detection of milestones

## Runtime Ownership

One engine owns both `AIR` and `AIR/O2`. Mode is configuration, not an engine
boundary.

The runtime owns:

- resolved dive plan
- active procedural phase
- active timer anchors
- stop progression
- gas exposure state
- delay state
- audit trail

The runtime does not delegate its truth to snapshot builders or audit logs.

## Operator Action Model

The redesign should replace button-oriented ambiguity with explicit operator
actions.

```python
class DiveAction(Enum):
    LEAVE_SURFACE = auto()          # LS
    REACH_BOTTOM = auto()           # RB
    LEAVE_BOTTOM = auto()           # LB
    REACH_STOP = auto()             # Rn / Surface
    LEAVE_STOP = auto()             # Ln
    TOGGLE_DESCENT_HOLD = auto()
    TOGGLE_DELAY = auto()
    CONFIRM_ON_O2 = auto()
    TOGGLE_OFF_O2 = auto()
    START_AIR_BREAK = auto()
    END_AIR_BREAK = auto()
    CONVERT_CURRENT_O2_STOP_TO_AIR = auto()
    RESET = auto()
```

The UI may still map these onto `PRIMARY` and `SECONDARY`, but the runtime
should not internally depend on "primary means whatever is next."

## Runtime State

```python
@dataclass(frozen=True)
class DiveRuntimeState:
    mode: DecoMode                  # AIR or AIR/O2
    depth_input: DepthInputState
    plan: DivePlanState | None
    phase: DivePhase
    stop_state: StopState | None
    travel_state: TravelState | None
    gas_state: GasExposureState
    delay_state: DelayState | None
    delay_result: DelayResultState | None
    clean_time: CleanTimeState | None
    holds: HoldState | None
    audit: AuditState
    clock: ClockState
```

### DepthInputState

```python
@dataclass(frozen=True)
class DepthInputState:
    raw_text: str
    parsed_depth_fsw: int | None
    supported_depth_fsw: int | None
```

### DivePlanState

```python
@dataclass(frozen=True)
class DivePlanState:
    input_depth_fsw: int
    input_bottom_time_min: int
    table_depth_fsw: int
    table_bottom_time_min: int | None
    stops: tuple[PlannedStop, ...]
    is_no_decompression: bool
    repeat_group: str | None
    time_to_first_stop_sec: int | None
    total_ascent_time_sec: int | None
    source: PlanSource
    original_plan: DivePlanState | None
```

`source` should distinguish:

- `TABLE`
- `DELAY_RECOMPUTE`
- `O2_TO_AIR_CONVERSION`

### PlannedStop

```python
@dataclass(frozen=True)
class PlannedStop:
    plan_stop_index: int
    depth_fsw: int
    gas: Literal["air", "o2"]
    duration_min: int
```

### StopState

```python
@dataclass(frozen=True)
class StopState:
    current_stop_index: int
    stop_anchor: TimerAnchor
    required_duration_sec: int
    carried_elapsed_sec: float
```

`carried_elapsed_sec` exists because later-stop timing includes prior travel by
rule. The current runtime hides that through inference. The new runtime should
store it directly.

### TravelState

```python
@dataclass(frozen=True)
class TravelState:
    travel_kind: TravelKind
    from_stop_index: int | None
    to_stop_index: int | None
    anchor: TimerAnchor
```

`TravelKind`:

- `DESCENT_TO_BOTTOM`
- `BOTTOM_TO_FIRST_STOP`
- `BETWEEN_STOPS`
- `FINAL_ASCENT_TO_SURFACE`

### GasExposureState

```python
@dataclass(frozen=True)
class GasExposureState:
    breathing_gas: Literal["air", "o2", "surface", "none"]
    o2_mode: O2Mode
    first_o2_stop_index: int | None
    current_o2_stop_index: int | None
    tsv_anchor: TimerAnchor | None
    o2_anchor: TimerAnchor | None
    off_o2_anchor: TimerAnchor | None
    air_break_anchor: TimerAnchor | None
    paused_required_o2_sec: float
```

`O2Mode`:

- `NOT_APPLICABLE`
- `AWAITING_FIRST_O2`
- `ON_O2`
- `OFF_O2`
- `AIR_BREAK`

### DelayState

```python
@dataclass(frozen=True)
class DelayState:
    delay_index: int
    delay_depth_fsw: int
    from_stop_index: int | None
    anchor: TimerAnchor
```

### DelayResultState

```python
@dataclass(frozen=True)
class DelayResultState:
    outcome: DelayOutcome
    delay_min: int
    schedule_changed: bool
    credited_o2_min: int
    air_interruption_min: int
    previous_plan_summary: str
    updated_plan_summary: str
```

## Explicit Runtime Phases

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

This is intentionally more explicit than the current phase model. The runtime
must not need to reconstruct "which kind of stop" from side state.

## Timer Anchor Model

Every timer that matters must exist as data.

```python
@dataclass(frozen=True)
class TimerAnchor:
    kind: AnchorKind
    started_at: datetime
    paused_elapsed_sec: float = 0.0
```

Required anchor kinds:

- `BOTTOM_TIME`
- `DESCENT_HOLD`
- `TRAVEL_TO_FIRST_STOP`
- `TRAVEL_BETWEEN_STOPS`
- `AIR_STOP`
- `TSV_WAIT`
- `O2_SEGMENT`
- `OFF_O2_DEVIATION`
- `AIR_BREAK`
- `DELAY`
- `CLEAN_TIME`

## Transition Contracts

## 1. Ready / Descent / Bottom

### `READY -> DESCENT`

Trigger:

- `LEAVE_SURFACE`

Effects:

- append audit `LS`
- create `BOTTOM_TIME` anchor at `LS`
- clear prior plan-specific transient state
- phase = `DESCENT`

### `DESCENT -> BOTTOM`

Trigger:

- `REACH_BOTTOM`

Effects:

- append audit `RB`
- preserve `BOTTOM_TIME` anchor from `LS`
- resolve bottom-time lookup only later, on `LEAVE_BOTTOM`
- phase = `BOTTOM`

### `BOTTOM -> TRAVEL_TO_FIRST_STOP`

Trigger:

- `LEAVE_BOTTOM`
- decompression required

Effects:

- append audit `LB`
- compute bottom elapsed from `LS`
- round bottom time up for table lookup
- resolve plan from depth and rounded bottom time
- create `TRAVEL_TO_FIRST_STOP` anchor
- phase = `TRAVEL_TO_FIRST_STOP`

### `BOTTOM -> TRAVEL_TO_SURFACE`

Trigger:

- `LEAVE_BOTTOM`
- no-decompression plan

Effects:

- append audit `LB`
- resolve no-decompression plan
- create `FINAL_ASCENT_TO_SURFACE` anchor
- phase = `TRAVEL_TO_SURFACE`

## 2. Travel to First Stop

### `TRAVEL_TO_FIRST_STOP -> AT_AIR_STOP`

Trigger:

- `REACH_STOP`
- first stop gas = `air`

Effects:

- append audit `R1`
- create `AIR_STOP` anchor at arrival
- current stop = first stop
- phase = `AT_AIR_STOP`

Why:

- first air stop timing begins on arrival per [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md)

### `TRAVEL_TO_FIRST_STOP -> AT_O2_STOP_WAITING`

Trigger:

- `REACH_STOP`
- first stop gas = `o2`

Effects:

- append audit `R1`
- create `TSV_WAIT` anchor at arrival
- current stop = first stop
- gas_state.o2_mode = `AWAITING_FIRST_O2`
- phase = `AT_O2_STOP_WAITING`

Why:

- direct-to-first-O2 branch uses `R30 -> On O2` or `R20 -> On O2`

## 3. Air Stop Chain

### `AT_AIR_STOP -> TRAVEL_BETWEEN_STOPS`

Trigger:

- `LEAVE_STOP`
- next stop exists

Effects:

- append audit `Ln`
- create `TRAVEL_BETWEEN_STOPS` anchor at leave
- clear active stop anchor
- phase = `TRAVEL_BETWEEN_STOPS`

### `AT_AIR_STOP -> TRAVEL_TO_SURFACE`

Trigger:

- `LEAVE_STOP`
- no next stop

Effects:

- append audit `Ln`
- create `FINAL_ASCENT_TO_SURFACE` anchor
- phase = `TRAVEL_TO_SURFACE`

### `TRAVEL_BETWEEN_STOPS -> AT_AIR_STOP`

Trigger:

- `REACH_STOP`
- next stop gas = `air`

Effects:

- append audit `Rn`
- create stop state with:
  - `stop_anchor = previous leave-stop anchor`
  - `carried_elapsed_sec = elapsed travel since leave`
- phase = `AT_AIR_STOP`

Why:

- later air-stop timing includes travel from prior stop by rule

## 4. First O2 Stop After Air Stop

### `TRAVEL_BETWEEN_STOPS -> AT_O2_STOP_WAITING`

Trigger:

- `REACH_STOP`
- next stop is the first O2 stop after a prior air stop

Effects:

- append audit `Rn`
- create `TSV_WAIT` anchor from prior `LEAVE_STOP` at the last air stop, not from
  arrival
- set current stop to the O2 stop
- gas_state.o2_mode = `AWAITING_FIRST_O2`
- phase = `AT_O2_STOP_WAITING`

Why:

- per [SCENARIO_first_o2_stop_after_air_stop.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_first_o2_stop_after_air_stop.md), procedural TSV is `L40 -> On O2 @ 30`

## 5. O2 Stop Progression

### `AT_O2_STOP_WAITING -> AT_O2_STOP_ON_O2`

Trigger:

- `CONFIRM_ON_O2`

Effects:

- append audit `On O2`
- create `O2_SEGMENT` anchor at confirmation time
- clear `TSV_WAIT` as active timer source
- set breathing gas = `o2`
- phase = `AT_O2_STOP_ON_O2`

Forbidden:

- no O2 elapsed time may be counted before confirmation
- display `TSV` applies only while the diver is at the first O2 stop and waiting
  for confirmation, not during earlier travel

### `AT_O2_STOP_ON_O2 -> TRAVEL_BETWEEN_STOPS`

Trigger:

- `LEAVE_STOP`
- next stop exists

Effects:

- append audit `Ln`
- create `TRAVEL_BETWEEN_STOPS` anchor
- preserve continuous O2 state when rule requires continuity
- phase = `TRAVEL_BETWEEN_STOPS`

### `TRAVEL_BETWEEN_STOPS -> AT_O2_STOP_ON_O2`

Trigger:

- `REACH_STOP`
- previous and next obligations are continuous O2 obligations

Effects:

- append audit `Rn`
- current stop = next stop
- preserve original active `O2_SEGMENT` anchor
- compute remaining obligation from carried O2 time, not from arrival time
- phase = `AT_O2_STOP_ON_O2`

Why:

- `30 -> 20` travel remains inside continuous O2 obligation

## 6. Off O2

### `AT_O2_STOP_ON_O2 -> AT_O2_STOP_OFF_O2`

Trigger:

- `TOGGLE_OFF_O2`

Effects:

- append audit `Off O2`
- capture elapsed O2 time into `paused_required_o2_sec`
- create `OFF_O2_DEVIATION` anchor
- clear active O2 timer as the visible primary timer
- phase = `AT_O2_STOP_OFF_O2`

### `AT_O2_STOP_OFF_O2 -> AT_O2_STOP_ON_O2`

Trigger:

- `TOGGLE_OFF_O2`

Effects:

- append audit `Back on O2`
- create new `O2_SEGMENT` anchor at resume time
- preserve remaining required O2 from paused state
- clear off-O2 anchor
- phase = `AT_O2_STOP_ON_O2`

Forbidden:

- off-O2 elapsed time must not reduce required O2 obligation

## 7. Air Breaks

### Break eligibility

Air-break eligibility is explicit state, not snapshot inference.

The runtime must compute:

- whether a break is required now
- whether the break is suppressed by the final `<= 35 min` rule
- whether the secondary action should be `START_AIR_BREAK`

Boundary rules:

- break becomes due at exactly `30:00` continuous O2 exposure
- if `30:00` is reached while still at `30 fsw`, the break is due there
- if remaining continuous O2 obligation to surface or final O2 period is
  `<= 35 min`, a new final break is suppressed

### `AT_O2_STOP_ON_O2 -> AT_O2_STOP_AIR_BREAK`

Trigger:

- `START_AIR_BREAK`
- break currently required

Effects:

- append audit `Air break start`
- capture remaining O2 obligation
- create `AIR_BREAK` anchor
- breathing gas = `air`
- phase = `AT_O2_STOP_AIR_BREAK`

### `AT_O2_STOP_AIR_BREAK -> AT_O2_STOP_ON_O2`

Trigger:

- `END_AIR_BREAK`
- at least 5 minutes elapsed

Effects:

- append audit `Air break end`
- create new `O2_SEGMENT` anchor
- preserve O2 remaining from pre-break state
- clear air-break anchor
- phase = `AT_O2_STOP_ON_O2`

Forbidden:

- early air-break termination
- counting air-break time against required O2 time

## 8. Delay Handling

Delay state must be explicit while active and explicit after resolution.

### Start delay

Trigger:

- `TOGGLE_DELAY`
- currently in travel phase

Effects:

- append audit `Delay n start`
- create `DELAY` anchor
- phase unchanged
- `delay_state` populated

### End delay

Trigger:

- `TOGGLE_DELAY`
- delay active

Effects:

- append audit `Delay n end`
- evaluate delay result against current branch
- clear `delay_state`
- store `delay_result`
- update plan if required

### Delay branch rules

Required branches from [RULE_delay_corrections.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_delay_corrections.md):

- exact `<= 1:00`: ignore
- first-stop delay `> 1:00` and `> 50 fsw`: add to bottom time and recompute
- first-stop delay `> 1:00` and `<= 50 fsw`: add to first stop only
- later-stop delay `> 1:00` and `> 50 fsw`: recompute
- later-stop delay `> 1:00` and `<= 50 fsw`: ignore
- O2 `30 -> 20` delay: credit qualifying O2 time to subsequent `20 fsw`
- terminal `20 fsw` departure delay: may require shift to air and preserve
  remaining obligation rules

### Explicit recompute contract

If a delay changes the authoritative schedule:

- the new plan replaces the prior plan for all future obligations
- the original plan remains retained in `plan.original_plan`
- `delay_result.schedule_changed = True`
- audit output records both prior and updated schedule summaries

## 9. Surface / Clean Time

### `TRAVEL_TO_SURFACE -> SURFACE_CLEAN_TIME`

Trigger:

- `REACH_STOP` or equivalent surface-arrival action mapped as `RS`

Effects:

- append audit `RS`
- create `CLEAN_TIME` anchor
- breathing gas = `surface`
- phase = `SURFACE_CLEAN_TIME`

### `SURFACE_CLEAN_TIME -> SURFACE_COMPLETE`

Trigger:

- snapshot or tick observes clean-time expiry

Effects:

- no new operational action required
- phase = `SURFACE_COMPLETE`

This is one of the few allowable time-driven phase transitions because clean time
is a post-procedure countdown, not a procedural milestone the operator must
confirm.

## Snapshot Projection Contract

Snapshot code is pure projection from explicit runtime state.

The snapshot layer must not:

- search audit history to find anchors
- infer whether O2 continuity exists
- infer whether the runtime is really in TSV vs air-stop semantics
- mutate plan state

### Required snapshot inputs

- explicit `phase`
- explicit `next required action`
- explicit active timer anchor
- explicit current depth / current stop
- explicit remaining stop obligation
- explicit detail metadata for hold/delay

### Status mapping

- `READY` -> `READY`
- `DESCENT` -> `DESCENT`
- `BOTTOM` -> `BOTTOM`
- travel phases -> `TRAVELING`
- `AT_AIR_STOP` -> `AT STOP`
- `AT_O2_STOP_WAITING` -> `AT O2 STOP`
- `AT_O2_STOP_ON_O2` -> `On O2`
- `AT_O2_STOP_OFF_O2` -> `Off O2`
- `AT_O2_STOP_AIR_BREAK` -> `Air Break`
- `SURFACE_CLEAN_TIME` -> `CLEAN TIME`
- `SURFACE_COMPLETE` -> `SURFACE`

### Timer basis mapping

- `DESCENT` and `BOTTOM`: elapsed since `LS`
- `AT_AIR_STOP` first stop: elapsed since arrival
- `AT_AIR_STOP` later stops: elapsed since prior leave-stop
- `AT_O2_STOP_WAITING`: elapsed procedural TSV
- `AT_O2_STOP_ON_O2`: elapsed O2 since confirmation/resume
- `AT_O2_STOP_OFF_O2`: elapsed off-O2 deviation
- `AT_O2_STOP_AIR_BREAK`: elapsed air break
- travel phases: elapsed travel since travel anchor
- `SURFACE_CLEAN_TIME`: countdown from 10 minutes

### `Next:` basis

`Next:` must come from explicit obligation state. It must not be guessed from
snapshot context.

Priority order:

1. required operator recovery action already due now
2. immediate procedural obligation on current phase
3. next stop / surface progression
4. clean-time monitor message

## Audit Contract

Audit output is append-only and secondary to runtime truth.

Recommended event schema:

```python
@dataclass(frozen=True)
class AuditEvent:
    code: str
    at: datetime
    payload: Mapping[str, str | int | float | None]
    message: str
```

Minimum required codes:

- `LS`
- `RB`
- `LB`
- `Rn`
- `Ln`
- `On O2`
- `Off O2`
- `Back on O2`
- `Air break start`
- `Air break end`
- `Delay n start`
- `Delay n end`
- `Schedule recompute`
- `RS`

The runtime must not read these back to know what phase it is in.

## Invariants

- exactly one `DivePhase` is active
- `READY` implies no active travel, stop, O2, air-break, or clean-time anchor
- travel phases imply `travel_state is not None`
- stop phases imply `stop_state is not None`
- `AT_O2_STOP_WAITING` implies `gas_state.o2_mode == AWAITING_FIRST_O2`
- `AT_O2_STOP_ON_O2` implies active O2 anchor and no off-O2/air-break anchor
- `AT_O2_STOP_OFF_O2` implies active off-O2 anchor
- `AT_O2_STOP_AIR_BREAK` implies active air-break anchor
- first O2 stop timing never begins before `CONFIRM_ON_O2`
- later air-stop timing never restarts on arrival
- continuous O2 travel to `20 fsw` does not break O2 obligation
- air-break time never reduces required O2 obligation
- exact `1:00` delay stays on ignore branch
- exact `50 fsw` delay stays on shallow branch

## Deletion Guidance

The replacement runtime should make the following current patterns unnecessary:

- `_dive_view(...)`-style inference helpers
- snapshot-side discovery of timer anchors
- reconstructing active timing from latest audit event with code X
- mixing stop-phase meaning with O2 state combinations

If a proposed implementation still needs those patterns, it is not following
this spec closely enough.
