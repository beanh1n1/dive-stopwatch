# Engine Validation Protocol

Status: Active

Authority:
- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/Source%20Truth/SOURCE_OF_TRUTH.md)
- [ENGINE_GOLDEN_PATHS.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_GOLDEN_PATHS.md)

## Purpose

This document defines the active validation loop for `engine_v2`.

The goal is not to build tests in the abstract. The goal is to:

1. validate the live operator flow
2. identify real behavioral mismatches
3. patch the runtime or presentation seam
4. add the smallest durable test that prevents recurrence
5. promote stable rules into parity coverage only when the contract is settled

This is the finish-line workflow.

## Scope

Primary validation families:
- `AIR`
- `AIR/O2`
- `AIR/SURD`
- `Mixed Gas`
- `Mixed/SURD`

Secondary validation family:
- `CHAMBER`

`CHAMBER` should stay lighter until the operator contract is frozen. It does not
need parity expansion at the same rate as the other families.

## Authority Order

When validating or patching:

1. manual source truth
2. rule docs
3. scenario docs
4. parity tests
5. seam/regression tests
6. code

If live behavior disagrees with a higher authority, the higher authority wins.

## Test Layers

There are three active test layers.

### 1. Live validation

Use the app to run realistic operator sequences and capture:
- action sequence
- timestamps
- visible status
- primary timer meaning
- depth row
- next row
- control layout
- audit/log lines

This is the main truth-finding step.

### 2. Parity tests

Use parity tests only for contracts that are already explicit and stable.

Current parity anchors:
- [test_engine_v2_air_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_air_parity.py)
- [test_engine_v2_mixed_gas_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_mixed_gas_parity.py)
- [test_engine_v2_surd_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_surd_parity.py)

Parity tests should lock:
- timer anchors
- table authority
- stable next-action text
- stable phase/gas-state chains
- stable handoff-family behavior

Parity tests should not lock unresolved UI wording or branch details still being
discovered in live use.

### 3. Seam/regression tests

Use narrow tests when:
- the bug is highly local
- the operator contract is not fully settled yet
- the failure is not broad enough to deserve parity promotion

Examples:
- logging row formatting
- one specific button-order regression
- one specific chamber branch edge case

## Validation Run Order

Run validation in this order:

1. `AIR`
2. `AIR/O2`
3. `AIR/SURD`
4. `Mixed Gas`
5. `Mixed/SURD`
6. `CHAMBER`

Reason:
- `AIR` and `AIR/O2` are the oldest and best-understood baseline
- `AIR/SURD` validates the handoff seam from the AIR family
- `Mixed Gas` and `Mixed/SURD` validate the newer table-driven path
- `CHAMBER` is last because it is still intentionally thinner

## Scenario Execution Format

For each live validation run, record:

### Setup

- mode/profile
- depth
- bottom time
- bottom mix if applicable
- expected authoritative table row

### Action sequence

Record each explicit operator action in order:
- `LS`
- `RB`
- `LB`
- `R40`
- `On O2`
- etc.

### Checkpoints

At each meaningful checkpoint, record:
- `Status`
- primary timer meaning
- depth row
- `Next`
- visible controls
- relevant log lines

### Outcome

Mark one of:
- `Pass`
- `Mismatch`
- `Ambiguous manual interpretation`

## Promotion Rules

When a live validation mismatch is found:

### Promote to parity when

- the manual rule is explicit
- the operator contract is stable
- the behavior spans a whole flow or seam

Examples:
- timer anchor rules
- depth/table snapping
- SURD handoff family behavior
- stable `Next:` semantics

### Promote to seam/regression only when

- the bug is narrow
- the wording or control contract is still moving
- the failure is local to one branch or renderer

Examples:
- one malformed log row
- one control-order bug
- one color mapping bug

## Required Patch Loop

Every confirmed bug should follow this order:

1. reproduce the mismatch
2. identify the authority
3. patch the smallest correct seam
4. add the narrowest durable test
5. rerun:
   - targeted tests
   - full `tests/engine_v2`
6. decide whether parity promotion is justified

Do not start by expanding parity if the rule is still unsettled.

## Minimum Acceptance Set

Before calling the system validation-ready, we should have:

### AIR
- no-decompression path
- simple AIR stop path
- AIR/O2 first-stop-from-bottom path
- AIR/O2 mixed-stop path
- AIR/O2 30-minute air-break path

### AIR/SURD
- normal `40 fsw` handoff
- surface-direct shallow path
- chamber-entry path with correct log/order

### Mixed Gas
- canonical `150/10` path
- `<16%` air-to-20 path
- recompute path
- `50/50` confirm path
- `30 fsw` O2 confirm path

### Mixed/SURD
- real `40 fsw` SURD handoff
- SURD collapse only at valid seam
- no AIR-family leakage into mixed-gas chamber planning

### CHAMBER
- ready -> `LS`
- `RB` wait timer
- explicit `On O2` / `Off O2`
- air-break timer
- clean time

## Current Best Fit Between Docs And Tests

Use these as the active acceptance anchor:

- [ENGINE_GOLDEN_PATHS.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_GOLDEN_PATHS.md)
- [test_engine_v2_air_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_air_parity.py)
- [test_engine_v2_mixed_gas_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_mixed_gas_parity.py)
- [test_engine_v2_surd_parity.py](/Users/iananderson/projects/DiveStopwatchProject/tests/engine_v2/test_engine_v2_surd_parity.py)

## Protocol For The Next Bug

When the next live mismatch appears, classify it immediately:

- `Parity candidate`
  - stable rule
  - broad operator behavior
  - add/extend parity after patch

- `Regression candidate`
  - local bug
  - branch-specific
  - add narrow test only

- `Manual clarification needed`
  - pause test-building
  - resolve interpretation first

That classification should happen before writing new tests.
