# Scenario: first O2 stop directly from bottom

Status: Draft

## Purpose

Capture the branch where the first decompression stop is itself an O2 stop, so
`TSV` is anchored from reaching that stop rather than from leaving a prior air stop.

## Setup

- Mode: `AIR/O2`
- Max Depth: choose a depth/bottom-time pair whose first stop is `30 fsw` or
  `20 fsw`
- Bottom Time: table-rounded as required
- Starting assumptions:
  - the first decompression stop is an O2 stop
  - there is no earlier air stop
  - O2 timing still begins only on confirmation

## Event Sequence

1. `LS`
2. `RB`
3. `LB`
4. `R1` at first O2 stop
5. `On O2`
6. `L1`
7. `R2` if applicable
8. `RS`

## Expected State By Step

### Step 4: `R1` at first O2 stop

- Status: display status `TSV`
- Main timer meaning: `TSV`, anchored from `R1`
- Depth row: current O2 stop depth with planned stop obligation shown
- Next row: next required stop or surface, depending on schedule
- Detail row: blank
- Allowed buttons: `Leave Stop`, `On O2`

### Step 5: `On O2`

- Status: `On O2`
- Main timer meaning: O2 elapsed time from confirmation
- Depth row: same stop obligation, now actively counting as O2
- Next row: next required action
- Detail row: blank
- Allowed buttons: phase-appropriate primary action, O2/air-break action if eligible

## Critical Assertions

- `TSV` is anchored from `R1 -> On O2`
- No prior travel segment is included in this `TSV`
- First O2 stop timer does not begin before `On O2`
- Display status is `TRAVELING` before `R1`, not `TSV`

## Forbidden Outcomes

- Failure: anchoring `TSV` from `LB` when the first stop itself is O2
- Failure: starting O2 obligation on arrival before confirmation
- Failure: showing `TSV` before the first O2 stop is actually reached

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
- Related code paths:
  - `src/dive_stopwatch/minimal/engine.py`
  - `src/dive_stopwatch/minimal/snapshot.py`
