# Scenario: no-decompression boundary crossover

Status: Draft

## Purpose

Capture the user-visible transition from a no-decompression dive with `Next:
Surface` to a decompression-bearing schedule once the no-D boundary is exceeded.

## Setup

- Mode: `AIR`
- Choose a depth with a known no-D boundary and a gap to the next listed table row
- Starting assumptions:
  - bottom countdown while `Next: Surface` remains true reflects time remaining to
    the final no-D limit for that depth

## Event Sequence

1. `LS`
2. `RB`
3. remain at bottom just below the no-D limit
4. observe bottom countdown / next row
5. cross the no-D boundary
6. observe updated bottom countdown / next row
7. `LB`

## Expected State By Step

### Before no-D expiry

- Status: `BOTTOM`
- Main timer meaning: elapsed time since `LS`
- Depth row: committed depth with bottom remaining countdown
- Next row: `Surface`

### After no-D expiry

- Status: `BOTTOM`
- Main timer meaning: still elapsed time since `LS`
- Depth row: bottom schedule/countdown now reflects the rounded next table row
- Next row: first required decompression stop, not `Surface`

## Critical Assertions

- The displayed bottom countdown while `Next: Surface` is true counts down to the
  final no-D boundary
- Crossing that boundary changes next-action guidance from `Surface` to the first
  required stop
- The schedule rounds to the next listed table row after the no-D maximum

## Forbidden Outcomes

- Failure: `Next: Surface` remains true after the no-D boundary is crossed
- Failure: bottom countdown keeps behaving like a no-D countdown after deco is
  required
- Failure: the runtime rounds to the wrong next table row

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
- Related code paths:
  - `src/dive_stopwatch/minimal/profiles.py`
  - `src/dive_stopwatch/minimal/snapshot.py`
- Related tests:
  - `tests/test_tables.py`
  - `tests/test_minimal_engine.py`
