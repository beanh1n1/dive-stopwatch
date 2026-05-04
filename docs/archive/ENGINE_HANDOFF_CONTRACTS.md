# Engine Handoff Contracts

Status: Proposed  
Parent docs:
- [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)
- [ENGINE_SURD_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_SURD_RUNTIME_SPEC.md)  
Behavioral reference: `main` at `6d115a9`

## Position

The handoff seam is part of runtime truth. It must be explicit, testable, and
small.

If the seam is vague, the redesign will drift back into the same failure mode
as the old engine: one runtime implicitly reaching into another runtime's
meaning through snapshots, event strings, or helper inference.

That is not acceptable.

## Rules

- AIR/AIR-O2 owns in-water truth until the explicit `L40` leave-stop action.
- SURD owns truth only after the handoff object is created.
- SURD must never inspect live AIR runtime state after handoff.
- Snapshot text is not a handoff contract.
- Audit lines are carried into the handoff as history, not as operational state.

## Minimal SURD Handoff Contract

Current redesign handoff contract:

```python
@dataclass(frozen=True)
class RedesignSURDHandoff:
    entry_kind: RedesignSURDEntryKind
    source_mode_text: str
    input_depth_fsw: int
    input_bottom_time_min: int
    source_profile_schedule_text: str
    source_table_depth_fsw: int | None
    source_table_bottom_time_min: int | None
    left_water_stop_depth_fsw: int | None
    remaining_in_water_obligation_sec: float | None
    handed_off_at: datetime
    audit_lines: tuple[str, ...]
```

Current supported `entry_kind`:

- `L40_NORMAL`

This is intentionally narrow.

## Why Each Field Exists

- `entry_kind`
  Prevents future SURD entry paths from being smuggled through an ambiguous
  generic handoff.
- `source_mode_text`
  Makes the source procedural context explicit at the seam.
- `input_depth_fsw`
  Needed to rebuild the authoritative SURD surface profile.
- `input_bottom_time_min`
  Needed to rebuild the authoritative SURD surface profile.
- `source_profile_schedule_text`
  Snapshot/display continuity only. This is carried for traceability, not
  chamber-state logic.
- `source_table_depth_fsw`
  Traceability. Makes the source schedule basis explicit.
- `source_table_bottom_time_min`
  Traceability. Makes the source schedule basis explicit.
- `left_water_stop_depth_fsw`
  States exactly what stop was exited at handoff.
- `remaining_in_water_obligation_sec`
  States whether any in-water obligation remained. For normal `L40` handoff it
  must be `0.0`.
- `handed_off_at`
  Defines SURD ownership start time.
- `audit_lines`
  Carries audit history forward without making logs authoritative.

## What Is Deliberately Not In The Contract

- live AIR runtime object references
- snapshot instances
- inferred timer anchors
- decoded event semantics
- mutable shared state
- UI button meaning

If SURD needs one of those, the contract is underspecified.

## Current Locked Case

Fixture:
- [tests/fixtures/redesign_handoff_contracts.json](/Users/iananderson/projects/DiveStopwatchProject/tests/fixtures/redesign_handoff_contracts.json)

Test:
- [tests/test_redesign_handoff_contract.py](/Users/iananderson/projects/DiveStopwatchProject/tests/test_redesign_handoff_contract.py)

Locked handoff case:

- `SURD` mode
- `150 fsw`
- bottom time rounded to `45 min`
- explicit `L40` leave-stop
- handoff created at the exact leave-stop timestamp
- `remaining_in_water_obligation_sec == 0.0`
- audit tail includes the in-water stop history

## Engineering Constraint

Keep the handoff contract smaller than the temptation.

If a future SURD path needs more fields, add them because a specific runtime
decision needs them, not because “it might be useful.” That is how seams bloat
and become another hidden runtime model.
