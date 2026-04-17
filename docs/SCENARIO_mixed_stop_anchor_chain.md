# Scenario: mixed stop anchor chain

Status: Draft

Rule IDs:
- `9-6.4`
- `9-8.2.1`
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-8.2.1` TSV / first O2-stop timing
- `9-8.2.2` continuous O2 / air-break timing

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Provide one end-to-end acceptance trace proving the anchor changes across:

- bottom
- first air stop
- later air stop
- first O2 stop
- subsequent O2 stop

## Critical Assertions

- first air stop anchors on arrival
- later air stop anchors on prior leave-stop
- first O2 stop anchors on O2 confirmation
- continuous O2 exposure carries across `30 -> 20`
- `Next:` continues to reflect the nearer obligation at each transition

## Forbidden Outcomes

- Failure: restarting later-stop timing on arrival
- Failure: starting first O2 timing before `On O2`
- Failure: breaking continuous O2 timing between `30` and `20`

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_display_and_timer_semantics.md`
  - `RULE_delay_corrections.md`
- Related code paths:
  - `src/dive_stopwatch/minimal/engine.py`
  - `src/dive_stopwatch/minimal/snapshot.py`
