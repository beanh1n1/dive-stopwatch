# Rule: display and timer semantics

Status: Draft

Rule IDs:
- `9-6.4`
- `9-8.2.1`
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-8.2.1` shifting to oxygen / TSV procedure
- `9-8.2.2` air-break timing basis

Scope status:
- Implemented with app-specific display interpretation

## Purpose

Define what the operator-facing status, timers, depth row, and next-action text
mean in the live app.

## Applies In

- Mode: `AIR`, `AIR/O2`
- Phase: all active dive phases
- Related states: travel, O2 confirmation, air break, clean time, active delay, hold

## Preconditions

- The app is operating in dive mode, not stopwatch mode.
- The runtime state and `Snapshot` fields are already derived from the live engine.
- Operator-facing text must describe the current procedure truthfully and without
  previewing a later but non-immediate action.

## Trigger

These rules apply whenever the app renders:

- status text
- the main timer
- the depth row and inline timer
- the `Next` row
- detail text

## Expected Behavior

### Status semantics

- `READY` means the dive has not yet left the surface.
- `DESCENT` means the dive is descending and bottom has not yet been confirmed.
- `BOTTOM` means bottom has been confirmed and ascent has not yet begun.
- `TRAVELING` means the dive is between bottom/stop/surface milestones and not in
  a special O2 waiting state.
- `AT STOP` means the diver is at a decompression stop that is not currently in the
  O2 waiting state.
- Display status `TSV` means the diver is at the first O2 stop and O2 has not yet
  been confirmed.
- `On O2` means the diver is at an O2 stop with O2 confirmed and no active air
  break.
- `On O2/ Traveling` means the diver is traveling between O2 obligations while O2
  credit/continuity is active.
- `Air Break` means the diver is in an active air break.
- `CLEAN TIME` means the diver has reached surface and is in the 10-minute
  clean-time interval.

### Main timer semantics

- In `DESCENT` and `BOTTOM`, the main timer reflects elapsed time since `LS`.
- At a non-O2 stop, the main timer reflects elapsed stop time anchored according to
  stop-timing rules.
- At the first O2 stop before confirmation, the main timer reflects `TSV`.
- Procedural `TSV` and display status `TSV` are related but not identical:
  - procedural `TSV` is defined in `RULE_core_definitions.md`
  - display status `TSV` is used only once the runtime is at the first O2 stop and
    waiting for O2 confirmation
- Explicit display-anchor rule:
  - if the first O2 stop follows a `40 fsw` air stop, visible `TSV` represents
    `L40 -> On O2 @ 30 fsw`
  - if the first stop itself is an O2 stop, visible `TSV` represents
    `R30 -> On O2` or `R20 -> On O2`
- At an O2 stop after confirmation, the main timer reflects elapsed O2 time from
  the active O2 anchor.
- During an active air break, the main timer reflects elapsed air-break time.
- During `TRAVEL`, the main timer reflects elapsed travel time from the applicable
  travel anchor.
- During `CLEAN TIME`, the main timer is the remaining clean-time countdown.

### Depth row semantics

- The depth row must show current or committed depth truthfully.
- During descent and travel, live current depth may be shown.
- At stop phases, the depth row reflects the current stop depth.
- When an inline timer is shown on the depth row, it must represent the currently
  relevant obligation at that line, not a future preview.
- `mm:ss left` is green only when it represents O2 time.
- Air-break inline countdowns are red.
- AIR stop countdowns and bottom remaining countdowns are not green.

### Next-row semantics

- `Next:` always means the next required procedural action.
- It must not preview a later O2 stop or later air break if a nearer required action
  still comes first.
- While `Next: Surface` is still true, bottom remaining may count down to the final
  no-decompression boundary.
- During clean time, the next row displays:
  - `Monitor diver for signs and symptoms of AGE`

### Detail-row semantics

- Detail text is for active hold/delay metadata or other secondary procedural
  detail.
- Detail text must not be the primary source of critical next-action guidance.

## Forbidden Behavior

- The app must not show `TSV` during ordinary travel before the first O2 stop is
  reached.
- The app must not show `On O2` before O2 confirmation.
- The app must not show a future O2 stop as `Next` when an air stop or other nearer
  required action still comes first.
- The app must not color non-O2 `mm:ss left` timers green.
- The app must not restart continuous O2 obligation incorrectly when continuity
  rules say it should carry through travel.

## Display Requirements

- Status:
  - must describe the current procedural state, not a convenient approximation
- Main timer:
  - must reflect the currently active procedural timer
- Depth row:
  - must reflect current procedural position and any inline obligation timer
- Next row:
  - must be literal next-action guidance
- Detail row:
  - may show secondary operational context only
- Event log:
  - should support auditability of user-confirmed milestones

## Notes

- This rule captures app-specific display semantics rather than broader manual
  terminology.
- The chapter citations above are the manual basis for the timing/procedure
  contract; the visible UI mapping remains an app-specific interpretation layer.
- The live app has already been iteratively tested against many of these semantics;
  this doc exists mainly to keep future hardening work aligned with the current
  product contract.

## Test Cases

- Happy path:
  - `L40 -> R30 -> On O2` shows `TRAVELING`, then `TSV`, then `On O2`, with
    procedural TSV meaning `L40 -> On O2 @ 30 fsw`
- Edge case:
  - `BOTTOM -> first O2 stop` uses `TRAVELING` before `R1`, then `TSV` after `R1`,
    with procedural TSV meaning `R30/R20 -> On O2`
- Regression case:
  - `Next` must always reflect the actual next stop/action from the schedule

## References

- Related CSV/table rows:
  - `docs/AIR.csv`
  - `docs/AIR_O2.csv`
- Related code paths:
  - `src/dive_stopwatch/core/air_o2_snapshot.py`
  - `src/dive_stopwatch/mobile/gui.py`
- Related scenarios:
  - `SCENARIO_air_o2_150_40.md`
