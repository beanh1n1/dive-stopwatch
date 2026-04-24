# Scenario: terminal 20 fsw air-break lifecycle

Status: Draft

Rule IDs:
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-8.2.2` air breaks at `30` and `20 fsw`
- worked AIR/O2 example on pp. `9-14` to `9-15`

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Capture the full lifecycle of air-break eligibility, start, blocked early end,
resume on O2, and the cutoff case where no further air break is required.

## Setup

- Mode: `AIR/O2`
- Use a profile with a terminal `20 fsw` O2 stop long enough to require at least
  one air break
- Starting assumptions:
  - O2 continuity has already been established
  - the diver arrives at the final `20 fsw` stop with an active remaining O2
    obligation

## Event Sequence

1. arrive at `20 fsw`
2. remain on O2 until air break is due
3. `Air break start`
4. attempt early `Air break end`
5. complete required break duration
6. `Air break end`
7. remain on O2 until final cutoff logic is reached
8. `Lx`
9. `RS`

## Expected State By Step

### Break not yet due

- Status: `On O2`
- Next row: still the remaining O2 obligation, not an air break

### Break due

- Status: `On O2`
- Next row: `Air break in 00:00` or equivalent immediate break guidance
- Secondary action becomes the break-start action

### Active break

- Status: `Air Break`
- Main timer meaning: break elapsed time
- Depth row: current depth with break countdown
- Next row: remaining O2 obligation after break

### Early end attempt

- Break must not end early
- The runtime should instruct completion of the break first

### Resumed O2

- Status: `On O2`
- Remaining obligation resumes from the preserved O2 obligation
- Air-break time itself does not reduce required O2 time

### Final cutoff

- If remaining O2 obligation is `<= 35 minutes`, no new final air break is required

## Critical Assertions

- Break eligibility starts only after the required continuous O2 interval
- Air-break time does not reduce required O2 obligation
- Early break completion is blocked
- Final `<= 35 min` remaining suppresses another air break

## Forbidden Outcomes

- Failure: allowing an early break end
- Failure: reducing O2 obligation while on air break
- Failure: demanding a new final air break when remaining O2 obligation is within
  the cutoff

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
  - `RULE_delay_corrections.md`
- Related code paths:
  - `src/dive_stopwatch/core/air_o2_engine.py`
  - `src/dive_stopwatch/core/air_o2_snapshot.py`
- Related tests:
  - `tests/test_core_engine.py`
