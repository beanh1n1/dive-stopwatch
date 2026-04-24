# Scenario: exact 30-minute continuous O2 threshold

Status: Draft

Rule IDs:
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-8.2.2` air breaks at `30` and `20 fsw`

Scope status:
- Implemented

## Purpose

Pin down the exact acceptance boundary for continuous O2 exposure reaching
`30:00`.

## Setup

- Mode: `AIR/O2`
- Use a schedule with an O2 segment long enough to reach the threshold

## Event Sequence

1. `On O2`
2. observe state just before `30:00`
3. observe state at exactly `30:00`
4. start air break

## Critical Assertions

- just before `30:00`, the break is not yet available
- at exactly `30:00`, the break is due
- the break-start action becomes available at the threshold, not later

## Forbidden Outcomes

- Failure: requiring the diver to wait past `30:00`
- Failure: exposing the break before `30:00`

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
- Related code paths:
  - `src/dive_stopwatch/core/air_o2_engine.py`
