# Scenario: 30 fsw air-break lifecycle

Status: Draft

Rule IDs:
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-8.2.2` air breaks at `30` and `20 fsw`

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Capture the case where continuous O2 exposure reaches the 30-minute threshold
while the diver is still at `30 fsw`, so the air break is required there rather than
first appearing at `20 fsw`.

## Setup

- Mode: `AIR/O2`
- Use a profile whose `30 fsw` O2 obligation itself exceeds `30 minutes`, or whose
  continuous O2 exposure reaches `30:00` before leaving `30 fsw`

## Event Sequence

1. arrive at `30 fsw`
2. `On O2`
3. remain on O2 through the 30-minute threshold
4. `Air break start`
5. attempt early break end
6. complete break
7. `Air break end`
8. continue required O2 / travel

## Critical Assertions

- continuous O2 timing begins at `On O2`
- the air break becomes due at `30 fsw` if the diver is still on O2 there at the
  30-minute threshold
- air-break time does not count toward required O2 obligation
- early break completion is blocked

## Forbidden Outcomes

- Failure: suppressing the `30 fsw` break merely because a later `20 fsw` stop
  exists
- Failure: counting air-break time toward the O2 obligation

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
- Related code paths:
  - `src/dive_stopwatch/core/engine.py`
  - `src/dive_stopwatch/core/snapshot.py`
