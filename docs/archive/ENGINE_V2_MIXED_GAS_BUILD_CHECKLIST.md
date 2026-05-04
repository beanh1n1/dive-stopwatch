# Engine V2 Mixed Gas Build Checklist

Status: Draft  
Parent parity doc: [ENGINE_V2_MIXED_GAS_PARITY.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_V2_MIXED_GAS_PARITY.md)

## Purpose

Turn the mixed-gas parity document into an implementation sequence that fits the
current `engine_v2` layout with minimal churn.

This checklist is ordered for delivery, not for theoretical cleanliness.

## Phase 0: Contract Entry Points

Goal:

- make mixed gas a first-class active mode without implementing behavior yet

Checklist:

- add `MIXED_GAS` to [view.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/contracts/view.py)
- export the new mode cleanly through [__init__.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/__init__.py) if needed
- define the initial mixed-gas action contract up front:
  - `EngineAction`
  - `ObligationKind`
  - presentation action labels
  - mixed-gas action priority/order rules in the presentation layer
- decide which mixed-gas-specific actions are part of the first contract slice and which can wait

Acceptance:

- code can reference `EngineMode.MIXED_GAS`
- mixed-gas actions and obligations have an explicit home before GUI wiring begins
- no existing AIR/AIR-O2, SURD, or CHAMBER tests regress

## Phase 1: Package Scaffold

Goal:

- create the mixed-gas runtime package with the same shape as the active mode packages

Target package:

- `src/dive_stopwatch/engine_v2/modes/mixed_gas/`

Initial file set:

- `engine.py`
- `state.py`
- `reducer.py`
- `queries.py`
- `rules.py`
- `plan.py`
- `invariants.py`
- `transitions/descent.py`
- `transitions/gas_shift.py`
- `transitions/travel_stop.py`
- `transitions/delay.py`

Checklist:

- create the package and file skeletons
- keep imports local and explicit
- avoid adding shared base classes or cross-mode abstractions

Acceptance:

- files import cleanly
- no runtime wiring uses them yet

## Phase 2: State and Query Contract

Goal:

- lock in the minimum runtime truth before wiring actions

Checklist:

- define `MixedGasPhase`
- define explicit breathing-gas identity
- define explicit gas-shift/confirmation state
- decide the mixed-gas projection contract into `EngineView`
- define timer holders needed for descent, bottom, travel, stop, shift, air break, and clean time
- define mixed-gas plan state with required stop gas identity
- define mixed-gas delay state separate from AIR delay rules
- implement `queries.py` to project an `EngineView`

Required early query outputs:

- `phase_name`
- `gas_state_name`
- `display_depth_fsw`
- `active_timer`
- `current_stop_depth_fsw`
- `current_stop_remaining_sec`
- `available_actions`
- `warnings`
- any new mixed-gas-neutral `EngineView` fields needed to avoid overloading AIR-specific fields

Acceptance:

- a manually constructed `MixedGasState` can be projected to `EngineView`
- mixed-gas shift truth has an explicit projection contract before reducer work starts
- projection does not depend on GUI logic

## Phase 3: Coordinator and Session Wiring

Goal:

- make the active app capable of launching mixed-gas mode

Checklist:

- add `MixedGasEngine` to the public namespace if appropriate
- extend [coordinator.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/runtime/coordinator.py) to own a mixed-gas engine path
- extend [session.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/runtime/session.py) title/mode launch handling
- extend [presentation_builder.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/engine_v2/projection/presentation_builder.py) only where mixed-gas labels require it
- extend [gui_v2.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/mobile/gui_v2.py) mode cycling and any mode-specific label handling

Acceptance:

- GUI can cycle into `MIXED_GAS`
- ready-state projection renders without crashing
- existing mode behavior remains unchanged

## Phase 4: Normal Descent and Bottom Timing

Goal:

- implement the non-emergency path from ready to bottom and bottom exit

Checklist:

- implement normal `>=16% O2` descent
- implement special `<16% O2` descent through `20 fsw`
- model the `5 minute` grace-window rule before bottom timing starts
- implement `LEAVE_BOTTOM` plan construction

Explicitly out of scope here:

- abort/restart from `20 fsw`
- descent emergency branches

Acceptance scenarios:

- normal descent starts bottom timing at the expected anchor
- `<16% O2` path starts bottom timing per the grace-window rule
- `LEAVE_BOTTOM` produces either no-decompression ascent or a stop plan

## Phase 5: In-Water Decompression Stop Chain and Gas-Shift Semantics

Goal:

- implement normal stop progression together with the gas-shift/confirmation semantics that change stop truth

Checklist:

- implement first-stop anchor-on-arrival
- implement later-stop anchor-on-previous-leave
- implement `90 fsw` shift to `50/50`
- support both cases:
- `90 fsw` is a stop
  - `90 fsw` is only a travel-through shift point
- implement `30 fsw` shift to O2 with explicit confirmation anchor
- implement `30 -> 20` carry semantics
- implement final ascent from `20 fsw` on O2

Acceptance scenarios:

- first decompression stop times correctly
- later stops include inter-stop ascent time
- `90 fsw` shift confirmation happens at the correct point
- `30 fsw` oxygen stop starts on O2 confirmation, not arrival

## Phase 6: Water-Stop Oxygen and Air-Break Semantics

Goal:

- implement continuous O2 timing and required air breaks across `30` and `20`

Checklist:

- carry continuous O2 exposure across `30 -> 20`
- trigger air break at `30 minutes` of O2 exposure
- implement `5 minute` air-break dead time
- suppress a final air break when remaining O2 exposure is `<=35 minutes`

Acceptance scenarios:

- no false air break when total/final remaining O2 is `<=35 minutes`
- air-break trigger is based on continuous O2 exposure, not local stop elapsed alone

## Phase 7: Mixed-Gas Delay Rules

Goal:

- implement bounded delay behavior from `12-4.12` that affects normal runtime parity

Checklist:

- delay to first stop:
  - ignore `<1 minute`
  - `>1 minute` rounds up and adds to bottom time
- delay deeper than `90 fsw`:
  - recompute and resume at present/subsequent stop without going deeper
- delay `90 fsw` and shallower:
  - ignore `<1 minute`
  - resume normally except special high-O2 rule
- special high-O2 case between `90` and `70 fsw`:
  - if delay `>5 minutes`, shift to air and recompute per parity doc
- delay leaving `30 fsw`:
  - subtract delay from `20 fsw` stop time

Acceptance scenarios:

- recompute paths are explicit in event payloads
- query/presentation state reflects adjusted stop truth

## Phase 8: Mixed-Gas Surface-Decompression Handoff

Goal:

- create the hard seam after the `40 fsw` water stop without implementing the full chamber runtime yet

Checklist:

- define a dedicated mixed-gas handoff contract
- make eligibility explicit only after completing the `40 fsw` water stop
- add a coordinator path or mode-specific action for explicit handoff creation
- add audit event payloads for handoff creation

Acceptance scenarios:

- eligibility does not appear before the completed `40 fsw` stop
- handoff is immutable input and does not reach back into live in-water state

## Initial Test File Plan

Add new tests under:

- `tests/engine_v2/test_engine_v2_mixed_gas_architecture.py`
- `tests/engine_v2/test_engine_v2_mixed_gas_semantics.py`
- `tests/engine_v2/test_engine_v2_mixed_gas_timers.py`
- `tests/engine_v2/test_engine_v2_mixed_gas_presentation.py`

Recommended first test order:

1. architecture smoke for new mode launch and projection
2. normal `>=16% O2` descent and no-decompression flow
3. `<16% O2` grace-window bottom-time anchor behavior
4. first-stop and later-stop anchor behavior
5. `90 fsw` `50/50` shift timing
6. `30 fsw` O2 confirmation timing
7. continuous O2 / air-break chain across `30 -> 20`
8. bounded delay rule coverage
9. `40 fsw` mixed-gas handoff eligibility

## Recommended First Code PR Scope

Keep the first implementation PR smaller than the full parity doc.

Recommended first PR:

- `EngineMode.MIXED_GAS`
- `modes/mixed_gas/` package scaffold
- state/query contract
- coordinator/session/gui ready-state wiring
- architecture tests for mode launch and presentation

Do not include in the first PR:

- full stop-chain behavior
- full delay logic
- surface-decompression chamber runtime

## Completion Standard for the First Scaffold

The scaffold is good enough when:

- the codebase has an explicit mixed-gas mode family
- the mixed-gas package structure exists and matches active mode conventions
- runtime state and projection seams are concrete enough to build against
- tests can begin landing scenario behavior incrementally without revisiting the architecture
