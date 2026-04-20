# Scenario: first O2 stop after an air stop

Status: Draft

Rule IDs:
- `9-6.4`
- `9-8.2.1`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-8.2.1` procedures for shifting to 100% oxygen / TSV
- worked AIR/O2 example on pp. `9-14` to `9-15`

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Capture the AIR/O2 branch where the first oxygen stop follows a prior air stop, so
procedural `TSV` runs from `L40 -> On O2 @ 30 fsw`.

## Setup

- Mode: `AIR/O2`
- Use a schedule whose first O2 stop is `30 fsw` after a `40 fsw` air stop
- Starting assumptions:
  - later air-stop timing already uses previous leave-stop anchoring
  - first O2 stop timing still begins only on confirmation

## Event Sequence

1. `LS`
2. `RB`
3. `LB`
4. `R1` air stop
5. `L1`
6. `R2` air stop at `40 fsw`
7. `L2`
8. `R3` at `30 fsw`
9. `On O2`

## Expected State By Step

### Step 7: `L2`

- Status: `TRAVELING`
- Main timer meaning: travel elapsed from `L2`
- Next row: `30 fsw` O2 stop obligation

### Step 8: `R3` at `30 fsw`

- Status: display status `TSV`
- Main timer meaning: procedural `TSV`, explicitly `L40 -> On O2 @ 30 fsw`
- Depth row: `30 fsw` with the planned O2 stop obligation shown
- Allowed buttons: `Leave Stop`, `On O2`

### Step 9: `On O2`

- Status: `On O2`
- Main timer meaning: O2 elapsed time from confirmation
- Depth row: same stop obligation, now actively counting as O2

## Critical Assertions

- `TSV` includes the `40 -> 30` ascent when the first O2 stop follows a `40 fsw`
  air stop
- `TSV` does not start before `R3`
- O2 stop timing does not start before `On O2`

## Forbidden Outcomes

- Failure: anchoring `TSV` from `R3` in this branch
- Failure: starting the O2 stop timer before `On O2`
- Failure: showing ordinary `AT STOP` instead of `TSV` while awaiting O2

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
- Related code paths:
  - `src/dive_stopwatch/core/snapshot.py`
  - `src/dive_stopwatch/core/engine.py`
- Related tests:
  - `tests/test_core_engine.py`
