# Scenario: delay boundary handling

Status: Draft

Rule IDs:
- `9-11.3`
- `9-11.4`
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-11.3` delays in arriving at the first decompression stop
- `9-11.4` delays in leaving a stop or between decompression stops
- `9-8.2.2` oxygen-delay handling at `30` and `20 fsw`
- examples on pp. `9-31` to `9-35`

Scope status:
- Partially Implemented

## Purpose

Capture the highest-risk delay correction boundaries at exactly `1 minute` and
exactly `50 fsw`, including both recompute and non-recompute branches.

## Setup

- Mode: `AIR` or `AIR/O2`
- Choose example profiles that exercise:
  - first-stop delay
  - between-stop / leaving-stop delay
  - delay depth `> 50 fsw`
  - delay depth `<= 50 fsw`

## Event Sequence

### Case A: first-stop delay, exact `1:00`

1. `LS`
2. `RB`
3. `LB`
4. delayed travel to first stop, with actual delay `= 60s`

### Case B: first-stop delay, `> 1:00` at `<= 50 fsw`

1. `LS`
2. `RB`
3. `LB`
4. delayed travel to first stop, with delay `> 60s` and current depth `<= 50`

### Case C: between-stop delay, exact `1:00`

1. enter a decompression stop
2. `Lx`
3. delayed travel or delayed departure, with actual delay `= 60s`

### Case D: between-stop delay, `> 1:00` at `> 50 fsw`

1. enter a decompression stop
2. `Lx`
3. delay `> 60s` while deeper than `50 fsw`

## Expected State By Step

### Exact `1:00`

- Delay `<= 1 minute` is ignored
- No recompute occurs
- Event log should not claim a schedule change

### `> 1:00` and `<= 50 fsw` at first stop

- Delay is rounded up to whole minutes
- Added to first stop obligation
- No schedule recompute

### `> 1:00` and `> 50 fsw`

- Delay is rounded up to whole minutes
- Added to bottom time
- Schedule recompute occurs
- Recomputed schedule becomes authoritative
- Event log records the updated schedule

## Critical Assertions

- Exact `1:00` is handled on the ignore branch
- Exact `50 fsw` is handled on the shallow branch
- Recompute occurs only for `> 1:00` and `> 50 fsw`
- Recompute metadata is retained for logging/audit

## Forbidden Outcomes

- Failure: recomputing at exactly `1:00`
- Failure: treating exactly `50 fsw` as a deep-delay recompute branch
- Failure: silently changing the live schedule without audit/log evidence

## References

- Related rules:
  - `RULE_delay_corrections.md`
- Related code paths:
  - `src/dive_stopwatch/minimal/profiles.py`
  - `src/dive_stopwatch/minimal/engine.py`
- Related tests:
  - `tests/test_minimal_profiles.py`
  - `tests/test_minimal_engine.py`
