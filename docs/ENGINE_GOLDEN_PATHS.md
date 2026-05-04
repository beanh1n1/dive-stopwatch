# Engine Golden Paths

Status: Active reference  
Execution protocol:
- [ENGINE_VALIDATION_PROTOCOL.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_VALIDATION_PROTOCOL.md)
Authority:
- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/Source%20Truth/SOURCE_OF_TRUTH.md)

## Purpose

This document defines the canonical behavioral paths that lock the redesign to
the current intended procedure.

A golden path is:

- one concrete setup
- one concrete operator-action sequence
- a fixed set of checkpoints
- explicit expectations at each checkpoint

It is the reference behavior the replacement engine must preserve unless we
explicitly decide to change the product contract.

## What A Golden Path Must Lock

Every golden path should lock these categories where relevant:

- phase/state identity
- active timer basis
- depth / stop identity
- next required action
- key snapshot labels
- key audit lines
- schedule-change behavior

The point is not just text parity. The point is procedural parity.

## Fixture Format

Each golden-path fixture should eventually become a structured test vector with:

```yaml
id: string
mode: AIR | AIR/O2 | SURD
purpose: string
setup:
  depth_text: string
  start_time: timestamp
actions:
  - at_plus: duration
    action: enum
checkpoints:
  - after_action: number
    expect_phase: string
    expect_status: string
    expect_timer_basis: string
    expect_depth: string
    expect_next: string
    expect_audit_contains: [string]
```

This doc defines the canonical contents of those future fixtures.

## Golden Path Inventory

The minimum redesign lock set is:

1. `GP-AIR-ND-001`
   AIR no-decompression dive to clean time
2. `GP-AIR-DECO-001`
   AIR decompression dive with single 20 fsw stop
3. `GP-AIR-O2-MIXED-001`
   AIR/O2 mixed-stop dive with first O2 stop after 40 fsw air stop
4. `GP-AIR-O2-DIRECT-001`
   AIR/O2 first O2 stop directly from bottom
5. `GP-AIR-O2-BREAK30-001`
   AIR/O2 air break becomes due at 30 fsw
6. `GP-AIR-O2-BREAK20-001`
   AIR/O2 terminal 20 fsw air-break lifecycle
7. `GP-AIR-O2-DELAY-001`
   AIR/O2 deep-delay recompute path
8. `GP-SURD-NORMAL-001`
   SURD normal L40 handoff through chamber completion
9. `GP-SURD-PENALTY-001`
   SURD surface-interval penalty path

## GP-AIR-ND-001

### Name

AIR no-decompression dive to clean time

### Purpose

Lock the simplest in-water path and the app-specific clean-time behavior.

### References

- `tests/test_v2_parity_p0.py`
- `tests/test_v2_smoke.py`
- [SCENARIO_no_d_boundary_crossover.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_no_d_boundary_crossover.md)

### Setup

- Mode: `AIR`
- Depth input: `60`

### Action Sequence

1. `LEAVE_SURFACE`
2. `REACH_BOTTOM` at `+02:00`
3. remain at bottom for `+10:00`
4. `LEAVE_BOTTOM`
5. `REACH_SURFACE` at `+01:00`

### Required Checkpoints

Checkpoint A: after `LEAVE_SURFACE`

- phase: `DESCENT`
- status: `DESCENT`
- timer basis: elapsed since `LS`
- next: unresolved until bottom-time commitment
- audit contains: `LS`

Checkpoint B: after `REACH_BOTTOM`

- phase: `BOTTOM`
- status: `BOTTOM`
- timer basis: elapsed since `LS`
- audit contains: `RB`

Checkpoint C: after `LEAVE_BOTTOM`

- phase: `TRAVEL_TO_SURFACE`
- status: `TRAVELING`
- timer basis: elapsed since `LB`
- next: `Surface`
- audit contains: `LB`

Checkpoint D: after `REACH_SURFACE`

- phase: `SURFACE_CLEAN_TIME`
- status: `CLEAN TIME`
- timer basis: clean-time countdown
- next: `Monitor diver for signs and symptoms of AGE`
- audit contains: `RS`

### Primary Risk Locked

- clean-time survives redesign as explicit post-surface behavior

## GP-AIR-DECO-001

### Name

AIR decompression dive with single 20 fsw stop

### Purpose

Lock basic AIR table lookup, single-stop schedule ownership, and standard
air-stop timing.

### References

- [SCENARIO_air_80_50.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_air_80_50.md)
- `tests/test_tables.py`

### Setup

- Mode: `AIR`
- Depth input: `78`
- Expected table row: `80 / 50`

### Action Sequence

1. `LEAVE_SURFACE`
2. `REACH_BOTTOM`
3. `LEAVE_BOTTOM` after bottom time rounding to `50`
4. `REACH_STOP` at `20 fsw`
5. `LEAVE_STOP`
6. `REACH_SURFACE`

### Required Checkpoints

Checkpoint A: after `LEAVE_BOTTOM`

- phase: `TRAVEL_TO_FIRST_STOP`
- next: `20 fsw for 17 min`
- plan authority: rounded to `80 / 50`
- audit contains: `LB`

Checkpoint B: after `REACH_STOP`

- phase: `AT_AIR_STOP`
- status: `AT STOP`
- depth: `20 fsw`
- timer basis: first air stop anchored on arrival
- depth timer: `17:00 left`
- next: `Surface`
- audit contains: `R1`

Checkpoint C: after `LEAVE_STOP`

- phase: `TRAVEL_TO_SURFACE`
- next: `Surface`
- audit contains: `L1`

### Primary Risk Locked

- basic AIR schedule lookup and first-stop anchor semantics do not regress

## GP-AIR-O2-MIXED-001

### Name

AIR/O2 mixed-stop dive with first O2 stop after 40 fsw air stop

### Purpose

Lock the main mixed-stop AIR/O2 branch, including:

- air stops
- `L40 -> On O2 @ 30` procedural TSV branch
- continuous O2 carry to `20`
- terminal air break

### References

- [SCENARIO_air_o2_150_40.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_air_o2_150_40.md)
- [SCENARIO_first_o2_stop_after_air_stop.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_first_o2_stop_after_air_stop.md)
- [SCENARIO_mixed_stop_anchor_chain.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_mixed_stop_anchor_chain.md)

### Setup

- Mode: `AIR/O2`
- Depth input: `145`
- Table row: `150 / 40`

### Action Sequence

1. `LEAVE_SURFACE`
2. `REACH_BOTTOM`
3. `LEAVE_BOTTOM`
4. `REACH_STOP` at `50`
5. `LEAVE_STOP`
6. `REACH_STOP` at `40`
7. `LEAVE_STOP`
8. `REACH_STOP` at `30`
9. `CONFIRM_ON_O2`
10. `LEAVE_STOP`
11. `REACH_STOP` at `20`
12. `START_AIR_BREAK`
13. `END_AIR_BREAK` after `5:00`
14. `LEAVE_STOP`
15. `REACH_SURFACE`

### Required Checkpoints

Checkpoint A: at `50`

- phase: `AT_AIR_STOP`
- timer basis: first air stop anchored on arrival
- next: `40 fsw for 6 min`

Checkpoint B: at `40`

- phase: `AT_AIR_STOP`
- timer basis: later air stop anchored on prior leave-stop, not arrival
- next: `30 fsw for 7 min`

Checkpoint C: at `30` before O2 confirmation

- phase: `AT_O2_STOP_WAITING`
- display status: `AT O2 STOP`
- display timer basis: procedural TSV
- procedural TSV anchor: `L40`
- next: `20 fsw for 35 min`

Checkpoint D: immediately after `CONFIRM_ON_O2`

- phase: `AT_O2_STOP_ON_O2`
- status: `On O2`
- timer basis: elapsed since explicit O2 confirmation
- audit contains: `On O2`

Checkpoint E: at `20`

- phase: `AT_O2_STOP_ON_O2`
- O2 continuity: preserved across `30 -> 20`
- next: air break when due, not before

Checkpoint F: during air break

- phase: `AT_O2_STOP_AIR_BREAK`
- status: `Air Break`
- timer basis: air-break elapsed
- next: resume O2 with preserved remaining obligation

Checkpoint G: after surface

- status: `CLEAN TIME`
- audit contains: `RS`

### Primary Risk Locked

- the core AIR/O2 operational branch survives with explicit anchor behavior

## GP-AIR-O2-DIRECT-001

### Name

AIR/O2 first O2 stop directly from bottom

### Purpose

Lock the alternate TSV branch where there is no prior 40 fsw air stop.

### References

- [SCENARIO_first_o2_stop_from_bottom.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_first_o2_stop_from_bottom.md)

### Setup

- Mode: `AIR/O2`
- Choose a schedule whose first stop is `30` or `20` on O2

### Action Sequence

1. `LEAVE_SURFACE`
2. `REACH_BOTTOM`
3. `LEAVE_BOTTOM`
4. `REACH_STOP` at first O2 stop
5. `CONFIRM_ON_O2`

### Required Checkpoints

Checkpoint A: on travel before first O2 stop

- phase: `TRAVEL_TO_FIRST_STOP`
- status: `TRAVELING`
- display must not show `TSV` yet

Checkpoint B: on arrival at first O2 stop before confirmation

- phase: `AT_O2_STOP_WAITING`
- display timer basis: procedural TSV
- TSV anchor: `R1`, not `LB`
- next: later required stop or surface

Checkpoint C: after `CONFIRM_ON_O2`

- phase: `AT_O2_STOP_ON_O2`
- timer basis: explicit O2 confirmation time

### Primary Risk Locked

- the two TSV branches stay distinct and explicit

## GP-AIR-O2-BREAK30-001

### Name

AIR/O2 air break becomes due at 30 fsw

### Purpose

Lock the exact `30:00` threshold behavior and prove that the break becomes due
at `30 fsw` when continuous O2 reaches the threshold there.

### References

- [SCENARIO_30fsw_air_break.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_30fsw_air_break.md)
- [SCENARIO_exact_30min_o2_threshold.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_exact_30min_o2_threshold.md)

### Setup

- Mode: `AIR/O2`
- Choose a schedule whose `30 fsw` O2 interval itself reaches or exceeds `30:00`

### Action Sequence

1. arrive at `30`
2. `CONFIRM_ON_O2`
3. observe state at `29:59`
4. observe state at `30:00`
5. `START_AIR_BREAK`
6. attempt early `END_AIR_BREAK`
7. `END_AIR_BREAK` after `5:00`

### Required Checkpoints

Checkpoint A: at `29:59`

- phase: `AT_O2_STOP_ON_O2`
- break not yet due
- secondary action is not break-start

Checkpoint B: at `30:00`

- phase: `AT_O2_STOP_ON_O2`
- break due now
- next: immediate air-break guidance
- secondary action becomes break-start

Checkpoint C: early break-end attempt

- phase remains `AT_O2_STOP_AIR_BREAK`
- completion blocked

### Primary Risk Locked

- exact threshold behavior at `30:00`

## GP-AIR-O2-BREAK20-001

### Name

AIR/O2 terminal 20 fsw air-break lifecycle

### Purpose

Lock the terminal O2 branch at `20`, including:

- break due at the right time
- early-end block
- air-break time not reducing O2 obligation
- final `<= 35 min` suppression of new break

### References

- [SCENARIO_terminal_20fsw_air_break.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_terminal_20fsw_air_break.md)
- `archive/legacy_runtime/tests/test_core_engine.py`

### Setup

- Mode: `AIR/O2`
- Use a final `20 fsw` O2 stop long enough to require at least one break

### Action Sequence

1. arrive at `20`
2. stay on O2 until break due
3. `START_AIR_BREAK`
4. attempt early `END_AIR_BREAK`
5. `END_AIR_BREAK` after required minimum
6. remain on O2 until final cutoff branch is reached
7. `LEAVE_STOP`
8. `REACH_SURFACE`

### Required Checkpoints

Checkpoint A: before break due

- next: remaining O2 obligation
- next must not preview break prematurely

Checkpoint B: when break due

- next: `Air break in 00:00` or equivalent immediate guidance

Checkpoint C: during break

- phase: `AT_O2_STOP_AIR_BREAK`
- air-break time does not reduce O2 remaining

Checkpoint D: after resume

- phase: `AT_O2_STOP_ON_O2`
- remaining O2 preserved from pre-break state

Checkpoint E: final suppression

- if remaining continuous O2 to surface is `<= 35 min`, no new final break is
  required

### Primary Risk Locked

- final terminal-break rules survive without inference bugs

## GP-AIR-O2-DELAY-001

### Name

AIR/O2 deep-delay recompute path

### Purpose

Lock the branch where a delay `> 60s` and `> 50 fsw` changes the authoritative
schedule.

### References

- [SCENARIO_delay_boundaries.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_delay_boundaries.md)
- `archive/legacy_runtime/tests/test_core_engine.py`
- `tests/test_core_profiles.py`

### Setup

- Mode: `AIR` or `AIR/O2`
- Use a profile whose first-stop or deep between-stop delay triggers recompute

### Action Sequence

1. progress to a delay-eligible travel phase
2. `TOGGLE_DELAY`
3. let delay exceed `60s` while depth is `> 50`
4. `TOGGLE_DELAY`
5. continue to next stop

### Required Checkpoints

Checkpoint A: delay active

- phase: unchanged travel phase
- detail shows active delay
- audit contains: `Delay 1 start`

Checkpoint B: delay ended

- `delay_result.schedule_changed = True`
- updated plan becomes authoritative
- audit contains prior and updated schedule summaries

Checkpoint C: at next stop

- stop obligation matches recomputed schedule, not original schedule

### Primary Risk Locked

- recompute behavior is explicit and auditable

## GP-SURD-NORMAL-001

### Name

SURD normal L40 handoff through chamber completion

### Purpose

Lock the normal SURD procedure from in-water `L40` through chamber completion.

### References

- [ENGINE_SURD_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_SURD_RUNTIME_SPEC.md)
- [SURFACE_ENGINE_DRAFT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SURFACE_ENGINE_DRAFT.md)
- `archive/legacy_runtime/tests/test_surd_engine.py`
- `archive/legacy_runtime/tests/test_core_engine.py`

### Setup

- Mode: `SURD`
- Use the normal `150 / 45` style path with explicit `40 fsw` handoff

### Action Sequence

1. progress in-water to `40 fsw`
2. `LEAVE_STOP` at `40` to trigger SURD handoff
3. `REACH_SURFACE`
4. `LEAVE_SURFACE`
5. `REACH_CHAMBER_50`
6. `CONFIRM_ON_O2`
7. complete first `50 fsw` segment
8. `ADVANCE_CHAMBER_TRANSITION` to `40`
9. complete first `40 fsw` segment
10. `START_AIR_BREAK`
11. `COMPLETE_AIR_BREAK`
12. `CONFIRM_ON_O2` / resume period 2 as required by runtime action mapping
13. continue until final `Reach Surface`

### Required Checkpoints

Checkpoint A: immediately before handoff

- in-water truth still active
- next: `40 fsw -> Surface`

Checkpoint B: immediately after handoff

- phase: `SURFACE_ASCENT_FROM_40`
- status: `40 -> Surface`
- timer basis: surface interval from `L40`
- depth timer: `05:00 left`
- next: `Undress`
- audit contains: `SurD start from 40 fsw`

Checkpoint C: after `REACH_SURFACE`

- phase: `SURFACE_UNDRESS`
- next: `Surface -> 50 fsw`
- audit contains: `RS`, `Undress`

Checkpoint D: after `REACH_CHAMBER_50`

- phase: `CHAMBER_AT_50_WAITING_O2`
- next: `50 fsw for 15 min`
- O2 has not started yet

Checkpoint E: after `CONFIRM_ON_O2`

- phase: `CHAMBER_ON_O2`
- status: `50 fsw O2`
- detail: `O2 00:00 | 15:00 left`

Checkpoint F: first `50` segment complete

- next: `Move chamber to 40 fsw`
- no auto-advance

Checkpoint G: first `40` segment complete

- next: `Start air break`
- no auto-advance

Checkpoint H: air break complete

- next: `Resume O2 period 2`

Checkpoint I: final completion

- next: `Surface`
- then `CLEAN TIME`

### Primary Risk Locked

- SURD remains a first-class explicit runtime, not an adapter

## GP-SURD-PENALTY-001

### Name

SURD surface-interval penalty path

### Purpose

Lock the `> 5:00` and `<= 7:00` surface-interval branch that applies `+15 min`
O2 at `50`.

### References

- [SURFACE_ENGINE_DRAFT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SURFACE_ENGINE_DRAFT.md)
- `archive/legacy_runtime/tests/test_surd_engine.py`
- `archive/legacy_runtime/tests/test_core_engine.py`

### Setup

- Mode: `SURD`
- Use normal `L40` handoff path

### Action Sequence

1. hand off at `L40`
2. allow surface interval to reach `05:10`
3. `REACH_SURFACE`
4. `LEAVE_SURFACE`
5. `REACH_CHAMBER_50`

### Required Checkpoints

Checkpoint A: at `05:10` before chamber arrival

- phase: still a surface-interval phase
- primary/depth timer indicates overdue by `+00:10`
- summary: `Next: Chamber 50 with penalty`

Checkpoint B: on chamber arrival

- penalty state: `PLUS_15_AT_50`
- audit contains: `Surface interval penalty (+15 O2 @ 50)`
- first chamber `50` segment duration becomes `30:00`

Checkpoint C: waiting at `50`

- next: `50 fsw for 30 min`
- secondary action: `On O2`

### Primary Risk Locked

- the penalty changes the authoritative chamber plan, not just the UI

## What Is Not A Golden Path

The following are important, but they are not the primary golden-path set:

- every minor label permutation
- every unsupported/out-of-scope recovery workflow
- exhaustive property testing of delay math
- every intermediate UI rendering state

Those belong in secondary regression coverage, not in the canonical lock set.

## Next Step

The next implementation step should be to convert these paths into structured
fixtures and then make both the legacy engine and replacement engine run against
the same fixture set during migration.
