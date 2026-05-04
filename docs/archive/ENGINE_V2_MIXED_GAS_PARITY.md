# Engine V2 Mixed Gas Parity

Status: Draft  
Parent architecture: [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)  
Active product target: `src/dive_stopwatch/engine_v2/` and `src/dive_stopwatch/mobile/gui_v2.py`

## Purpose

Define the parity target for the first `engine_v2` mixed-gas buildout using the
uploaded mixed-gas chapter material and the current `engine_v2` architecture.

This document is intended to scaffold implementation, not to justify a broad
redesign. The goal is to add a mixed-gas runtime slice with explicit state,
actions, timing, and projection seams while preserving the existing
`engine_v2` working style:

- explicit runtime truth
- thin coordinator seam
- pure projection from runtime state
- no speculative adapter layers

## Source References

Primary mixed-gas references:

- [Caisson_engine_V2_Mixed_Gas_notes.txt](/Users/iananderson/projects/DiveStopwatchProject/docs/Caisson_engine_V2_Mixed_Gas_notes.txt)
- [Mixed_Gas_Diving_Operations_US DIVING MANUAL_REV7_ChangeA-6.6.18.pdf  2.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/Mixed_Gas_Diving_Operations_US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18.pdf%20%202.pdf)

Active architecture references:

- [ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md)
- [ENGINE_SURD_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_SURD_RUNTIME_SPEC.md)
- [SCENARIO_mixed_stop_anchor_chain.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_mixed_stop_anchor_chain.md)
- [src/dive_stopwatch/engine_v2/runtime/coordinator.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/runtime/coordinator.py)
- [src/dive_stopwatch/engine_v2/modes/air/](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/modes/air)
- [src/dive_stopwatch/engine_v2/modes/surd/](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/modes/surd)

## Scope

In scope for the first mixed-gas parity scaffold:

- surface-supplied helium-oxygen in-water runtime
- bottom-mix identity as runtime input
- bottom-time semantics including the `<16% O2` descent case
- decompression gas shifts at `90 fsw` and `30 fsw`
- mixed-gas stop timing semantics
- mixed-gas water-stop air-break semantics
- mixed-gas delay handling rules from `12-4.12`
- eligibility seam for mixed-gas surface decompression after `40 fsw`
- projection/UI parity targets for the active `gui_v2`
- test/scenario scaffolding targets

Out of scope for the first slice:

- full chamber treatment behavior after mixed-gas surface interval exceeds allowed limits
- repetitive mixed-gas planning
- abort, rescue, and other emergency procedures
- generalized multi-diver synchronization logic
- unifying all gas families behind a new shared super-engine

## Working Assumption

Mixed gas should be added as a new active mode family in `engine_v2`, not
forced into the current AIR/AIR-O2 runtime by widening string enums until the
runtime becomes ambiguous.

That means:

- reuse the current contracts and presentation seam where they still fit
- add a dedicated mixed-gas mode runtime under `engine_v2/modes/`
- preserve the hard handoff pattern for any later surface-decompression seam

## Manual-Backed Parity Truths

These are the behaviors that matter most for runtime parity.

### Gas families

Mixed gas uses four gas families across the dive:

- bottom mix
- `50/50` helium-oxygen
- `100% O2`
- air for procedural oxygen air breaks

Runtime implication:

- AIR/AIR-O2 `gas_state` is too narrow for mixed gas parity
- the mixed-gas runtime needs explicit breathing-gas identity, not just `AIR`,
  `ON_O2`, `WAITING_ON_O2`, `INTERRUPTED_O2`, `AIR_BREAK`

### Bottom-mix selection matters operationally

The chapter makes the bottom-mix oxygen fraction operationally significant,
especially around the `<16% O2` descent procedure.

Runtime implication:

- mixed-gas mode needs bottom-mix metadata as first-class input
- at minimum: selected bottom-mix O2 percent, and whether it is `<16%`
- this is not just a display label; it changes timing semantics

### Descent procedure changes when bottom mix is below `16% O2`

For bottom mixes below `16% O2`, the diver starts on air, descends to `20 fsw`,
shifts to bottom mix, ventilates, performs checks, and gets a `5 minute` grace
window before bottom timing begins.

Runtime implication:

- mixed gas needs an explicit pre-bottom subflow the AIR runtime does not have
- bottom-time anchor cannot always mean "leave surface"
- a simple AIR-style `LEAVE_SURFACE -> REACH_BOTTOM` path is not enough

The abort/restart branches in the same chapter section are intentionally out of
scope for this first parity target.

### Stop timing mostly matches AIR/AIR-O2, with one important O2 exception

The chapter keeps the same broad stop-anchor rule as AIR:

- first stop times on arrival
- later stop times start when leaving the previous stop

But mixed gas adds a specific exception:

- the first `30 fsw` oxygen stop starts only when divers are confirmed on oxygen

Runtime implication:

- the existing stop-anchor pattern in `modes/air` is reusable
- the existing first-O2 confirmation model is also reusable
- mixed gas still needs its own gas-shift semantics at `90` and `30`

### Gas shifts are part of the runtime, not presentation-only labels

The manual requires:

- shift from bottom mix to `50/50` at `90 fsw`
- shift from `50/50` to `100% O2` at `30 fsw`
- if there is no `90 fsw` stop, delay ventilation/confirmation until the next
  shallower stop

Runtime implication:

- mixed gas needs explicit shift state and confirmation logic
- a plain "stop gas from table row" model is not enough, because the gas in use
  can lag behind the gas required by the schedule until confirmation occurs

### Water-stop air breaks are continuous-oxygen driven

At `30` and `20 fsw`, the diver breathes O2 in `30 minute` periods separated by
`5 minute` air breaks. The chapter’s example makes clear that:

- continuous oxygen exposure carries across the `30 -> 20` transition
- the travel time from `30 -> 20` counts toward the `20 fsw` oxygen stop
- air-break timing is driven by total O2 exposure, not just local stop elapsed

Runtime implication:

- the current AIR/O2 continuous-O2 model is directionally reusable
- mixed gas needs this behavior without assuming all shallow decompression is
  already O2-only from the first O2 stop onward

### Surface decompression eligibility starts after the `40 fsw` water stop

The chapter says mixed-gas surface decompression can begin after completing the
`40 fsw` water stop. Surface interval is measured from leaving `40 fsw` in the
water to arriving at `50 fsw` in the chamber, with a `5 minute` penalty
threshold.

Runtime implication:

- the existing SURD seam is not parity for mixed gas
- mixed gas needs a separate handoff contract and later a separate chamber path
- do not reuse AIR SURD semantics directly just because both involve "surface
  decompression"

### Delay logic is not the same as AIR/AIR-O2

The chapter distinguishes:

- delay to first stop
- delays deeper than `90 fsw`
- delays `90 fsw` and shallower
- a special `>5 minute` high-oxygen delay case between `90` and `70 fsw`
- delay leaving `30 fsw` subtracting from `20 fsw` stop time

Runtime implication:

- current AIR delay logic is not parity-safe for mixed gas
- mixed gas needs a dedicated delay rule set even if the UI actions are reused

## Reuse Map Against Current Engine V2

### Reuse directly

- `EngineAction` shape as the operator-facing action seam
- `AuditEvent` / `AuditEventKind` structure
- `presentation_builder.py` as the active presentation seam
- `EngineV2Session` audit-log split
- explicit `tick()` behavior for autonomous completion

### Reuse with extension

- `EngineAction`
- `EngineMode`
- `EngineView`
- `ObligationKind`
- `EngineCoordinator`
- action prioritization and GUI button mapping
- dive-log summarization
- warning-label projection
- test-time controls

### Do not reuse as-is

- `modes/air` gas taxonomy
- AIR/AIR-O2 delay rules
- AIR SURD handoff builder
- SURD chamber period plan

## Recommended Runtime Slice

The first implementation slice should be in-water mixed gas only, plus the
eligibility seam for mixed-gas surface decompression.

Deliver in this order:

1. mixed-gas in-water runtime to normal in-water completion
2. explicit mixed-gas handoff contract after `40 fsw`
3. mixed-gas surface-decompression runtime
4. exceptional procedures beyond the happy-path and bounded delay rules

This keeps the first slice parity-focused and avoids prematurely entangling mixed
gas with the existing SURD chamber model.

## Proposed Mixed-Gas Runtime Model

This is the minimum model needed to scaffold implementation without pretending
the current AIR state already covers mixed gas.

### Proposed mode

Add a new active mode:

```python
class EngineMode(Enum):
    AIR = auto()
    AIR_O2 = auto()
    MIXED_GAS = auto()
    SURD = auto()
    CHAMBER = auto()
```

Do not overload `AIR_O2` to mean mixed gas.

### Proposed runtime package

Recommended package:

- `src/dive_stopwatch/engine_v2/modes/mixed_gas/`

Recommended initial files:

- `state.py`
- `engine.py`
- `reducer.py`
- `queries.py`
- `rules.py`
- `plan.py`
- `invariants.py`
- `transitions/descent.py`
- `transitions/gas_shift.py`
- `transitions/travel_stop.py`
- `transitions/delay.py`

### Proposed phase model

Initial explicit phases:

```python
class MixedGasPhase(Enum):
    READY = auto()
    DESCENT_TO_20_ON_AIR = auto()
    AT_20_PREBOTTOM_SHIFT = auto()
    DESCENT_TO_BOTTOM = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    AT_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    COMPLETE = auto()
```

Notes:

- `DESCENT_TO_20_ON_AIR` and `AT_20_PREBOTTOM_SHIFT` are only used when the
  bottom mix is `<16% O2`
- the normal `>=16% O2` case can go from `READY -> DESCENT_TO_BOTTOM`
- keep the phase model flat and explicit, consistent with current `engine_v2`

### Proposed gas identity model

Mixed gas needs explicit breathing-gas identity and shift/confirmation state.

```python
class MixedGasBreathingGas(Enum):
    AIR = auto()
    BOTTOM_MIX = auto()
    HELIOX_50_50 = auto()
    OXYGEN = auto()


class MixedGasShiftState(Enum):
    NONE = auto()
    AWAITING_BOTTOM_MIX_CONFIRM = auto()
    AWAITING_50_50_CONFIRM = auto()
    AWAITING_O2_CONFIRM = auto()
    OFF_O2 = auto()
    AIR_BREAK = auto()
```

This separates:

- what gas should be in use
- what gas is actually confirmed in use

That distinction is required for parity at `20`, `90`, and `30 fsw`.

### Proposed runtime state

```python
@dataclass(frozen=True)
class MixedGasState:
    phase: MixedGasPhase
    depth_text: str
    depth_fsw: int | None
    bottom_mix_o2_percent: float | None
    breathing_gas: MixedGasBreathingGas
    shift_state: MixedGasShiftState
    surface_timer: MixedGasTimer | None
    bottom_timer: MixedGasTimer | None
    travel_timer: MixedGasTimer | None
    stop_timer: MixedGasTimer | None
    shift_timer: MixedGasTimer | None
    air_break_timer: MixedGasTimer | None
    clean_time_timer: MixedGasTimer | None
    plan: MixedGasPlan | None
    oxygen: MixedGasOxygenState
    delay: MixedGasDelayState
```

Minimum supporting state:

- `bottom_mix_o2_percent`
- `requires_20fsw_air_descent` derived from bottom-mix percentage
- stop plan with per-stop required gas
- continuous O2 exposure state across `30 -> 20`
- delay state specific to mixed-gas chapter rules

### EngineView contract decision

Mixed gas should not overload AIR-specific `EngineView` fields just to avoid a
small contract extension.

Before implementation starts in earnest, choose one of these explicitly:

- extend `EngineView` with mixed-gas-neutral fields for gas-shift truth and gas
  identity display, or
- document a strict mapping from mixed-gas runtime state into the current
  `EngineView` shape

The minimum unresolved projection truths are:

- selected bottom-mix identity for display/detail
- pending gas-shift confirmation target
- mixed-gas-specific `Next:` obligation when the next operator step is gas
  confirmation rather than stop progression

Do not bury those semantics in GUI-only conditionals or overload unrelated AIR
fields such as `traveling_on_o2`.

## Operator Actions

The existing action seam is mostly reusable, but mixed gas needs at least one
new confirmation path beyond current AIR/AIR-O2 semantics.

### Reusable actions

- `LEAVE_SURFACE`
- `REACH_BOTTOM`
- `LEAVE_BOTTOM`
- `REACH_STOP`
- `LEAVE_STOP`
- `CONFIRM_ON_O2`
- `TOGGLE_OFF_O2`
- `START_AIR_BREAK`
- `END_AIR_BREAK`
- `START_DELAY`
- `END_DELAY`
- `REACH_SURFACE`
- `RESET`

### Mixed-gas-specific actions likely required

- `CONFIRM_BOTTOM_MIX`
- `CONFIRM_50_50`
- `SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION`

Recommendation:

- add the minimum new actions needed for explicit gas-confirmation seams
- do not hide bottom-mix or `50/50` confirmation behind implicit arrival logic

## Audit/Event Parity

The current audit event enum can carry much of the flow, but mixed gas needs
payload conventions that make the gas shifts observable.

At minimum, mixed-gas events should record:

- selected bottom mix
- whether `<16% O2` descent mode was active
- gas in use on `LEFT_SURFACE`, `REACHED_STOP`, and `LEFT_STOP`
- gas-shift target and confirmation point
- whether a delay forced recompute, resume, air fallback, or stop-time subtraction
- whether the diver became eligible for mixed-gas surface decompression

Recommendation:

- prefer extending event payloads before adding many new event kinds
- add new event kinds only where the action is materially distinct, such as a
  mixed-gas handoff creation

## Presentation / GUI Parity Targets

The active GUI can stay centered on the existing presentation model if mixed gas
feeds it clearly enough.

The mixed-gas runtime must surface:

- active breathing gas label
- pending gas confirmation state
- current stop depth and remaining time
- continuous O2 / air-break timing state
- whether the current `Next:` obligation is a gas confirmation, stop leave, or
  handoff to surface decompression

Minimum presentation additions likely needed:

- mixed-gas mode chip label
- gas labels for `Bottom Mix` and `50/50`
- summary text for `Next: Confirm Bottom Mix`, `Next: Confirm 50/50`, and
  mixed-gas surface-decompression handoff

Avoid:

- putting mixed-gas procedural truth into GUI-only conditionals
- encoding the `<16% O2` descent exception only as display text

## Handoff Boundary for Later Surface Decompression

Mixed-gas surface decompression should get its own contract, not reuse the AIR
SURD contract.

Recommended future contract:

```python
@dataclass(frozen=True)
class MixedGasSurfaceHandoff:
    source_table_depth_fsw: int | None
    source_table_bottom_time_min: int | None
    input_depth_fsw: int
    input_bottom_time_min: int
    bottom_mix_o2_percent: float
    left_water_stop_depth_fsw: int
    completed_water_stop_depth_fsw: int
    handed_off_at: datetime
    audit_tail: tuple[AuditEvent, ...]
```

Why separate it:

- mixed-gas chamber periods differ from current SURD chamber semantics
- the chapter uses a `40 -> surface -> chamber 50` eligibility rule, not the AIR
  `30/20` or `L40` semantics already implemented
- mixed-gas surface decompression explicitly uses chamber compression on air,
  then O2 periods at `50`, `40`, and `30`

## Test Scaffold

The first mixed-gas test set should prove parity on the highest-risk semantic
boundaries, not just happy-path completion.

### Core acceptance scenarios

1. no-decompression mixed-gas dive with bottom mix `>=16% O2`
2. decompression dive with first required `90 fsw` stop
3. decompression dive where `90 fsw` is a shift point but not a stop
4. first `30 fsw` O2 stop begins on explicit O2 confirmation
5. continuous O2 carries from `30 -> 20`
6. `30 minute` O2 threshold triggers a `5 minute` air break across the stop chain
7. final remaining O2 period `<=35 minutes` does not require an extra air break
8. `<16% O2` descent uses the `20 fsw` grace-window timing rule
9. delay to first stop `>1 minute` recomputes by adding to bottom time
10. delay deeper than `90 fsw` recomputes at present/subsequent stop without going deeper
11. delay between `90` and `70 fsw` longer than `5 minutes` forces air fallback behavior
12. delay leaving `30 fsw` subtracts from the `20 fsw` stop time
13. mixed-gas surface-decompression eligibility appears only after completing the `40 fsw` water stop

### Architecture tests

- mixed-gas runtime owns its own phase truth
- presentation stays pure and derived
- coordinator switches among active mode families without reaching into private state
- mixed-gas handoff creation is explicit and immutable

## Recommended Build Sequence

1. Add `EngineMode.MIXED_GAS` and refine the early action/obligation contract.
2. Add a new `modes/mixed_gas` package and lock the mixed-gas `EngineView` projection contract.
3. Implement in-water mixed-gas no-decompression flow and decompression stop progression together with explicit gas-shift confirmations for bottom mix, `50/50`, and O2.
4. Add water-stop O2/air-break timing semantics across `30 -> 20`.
5. Add mixed-gas-specific delay handling.
6. Add the mixed-gas surface-decompression eligibility seam and handoff contract.
7. Only then build the separate chamber runtime for mixed-gas surface decompression.

## Open Decisions

These need to be decided before coding goes far, but they should not block the
parity scaffold itself.

- whether bottom-mix percentage is free numeric input or selected from a bounded list
- where Table `12-4` planning data will live and how it will be represented
- whether mixed-gas surface decompression lives as a second mixed-gas runtime or a
  dedicated sibling mode analogous to, but separate from, current SURD
- whether gas-confirmation actions should remain generic (`CONFIRM_ON_O2`) plus
  new confirmation actions, or whether mixed gas should use a more generic
  `CONFIRM_GAS_SHIFT(target)` model later

## Bottom Line

Mixed gas is close enough to AIR/AIR-O2 to reuse the active `engine_v2` seams,
but not close enough to collapse into the current AIR runtime without making gas,
timing, and delay truth less explicit.

The parity-safe path is:

- new mixed-gas runtime package
- explicit gas identity and confirmation state
- explicit `<16% O2` descent handling
- mixed-gas-specific delay rules
- separate mixed-gas surface-decompression handoff and later chamber runtime
