# Rule: core definitions and timing semantics

Status: Draft

Rule IDs:
- `9-6.4`
- `9-6.5`
- `9-8.1`
- `9-8.2`
- `9-8.2.1`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-6.5` last water stop
- `9-8.1` in-water decompression on air
- `9-8.2` in-water decompression on air and oxygen
- `9-8.2.1` shifting to 100% oxygen / procedural TSV

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Define the core dive timing, depth, travel, and decompression terms that the live
runtime must use consistently.

## Applies In

- Mode: `AIR`, `AIR/O2`
- Phase: all phases
- Related states: `READY`, `DESCENT`, `BOTTOM`, `TRAVEL`, `AT_STOP`, `SURFACE`

## Preconditions

- A dive is being tracked through explicit operator-confirmed events.
- The app is acting as a supervisory timing and schedule aid, not as an autonomous
  detector of dive milestones.

## Trigger

These definitions apply whenever the runtime:

- computes elapsed or remaining time
- selects a table row or schedule
- displays status, timers, or next-action guidance
- applies travel, stop, O2, or air-break rules

## Expected Behavior

- `Descent Time` means elapsed time from `LS` to `RB`.
- `Bottom Time` / `TBT` means elapsed time from `LS` to `LB`, rounded up to the
  next whole minute for table lookup.
- `Total Decompression Time` / `TDT` means elapsed time from `LB` to `RS`.
- `Total Time of Dive` means elapsed time from `LS` to `RS`.
- `Maximum Depth` is the deepest depth obtained by the diver and is the depth used
  for table lookup.
- Table lookup must use the exact depth if present, otherwise the next deeper depth.
- Table lookup must use the exact bottom time if present, otherwise the next longer
  bottom time.
- `No-Decompression Limit` means the maximum bottom time that still allows direct
  ascent at the prescribed travel rate without decompression stops.
- The normal ascent rate from bottom to first stop, between stops, and from last
  stop to surface is `30 fsw/min`.
- Minor ascent-rate variations between `20` and `40 fsw/min` are acceptable and do
  not require correction.
- Descent rate on air dives is not critical, but should not exceed `75 fsw/min`.
- For air decompression:
  - first stop time begins on arrival at the first stop
  - each later stop time begins when the diver leaves the previous stop
- For AIR/O2 decompression:
  - the same stop-time rule applies, except the first O2 stop begins only when all
    divers are confirmed on oxygen
- The last in-water stop for standard in-water decompression is `20 fsw`.
- AIR/O2 stops deeper than `30 fsw` are on air.
- AIR/O2 O2 stops commence at `30 fsw` or `20 fsw` depending on the table row.
- Procedural `TSV` means `Travel/Shift/Vent` time.
- Explicitly, procedural `TSV` is:
  - `L40 -> On O2 @ 30 fsw` when the first oxygen stop follows a `40 fsw` air stop
  - `R30 -> On O2` when the first stop itself is an O2 stop at `30 fsw`
  - `R20 -> On O2` when the first stop itself is an O2 stop at `20 fsw`
- For dives with the first stop at `40 fsw` or deeper, this means procedural `TSV`
  includes:
  - the `40 -> 30` ascent segment
  - gas shift
  - confirmation time to establish that divers are on O2
- For dives whose first stop is an O2 stop at `30 fsw` or `20 fsw`, this means
  procedural `TSV` excludes travel to the stop and includes only:
  - gas shift
  - confirmation time to establish that divers are on O2

## Forbidden Behavior

- The runtime must not treat `Bottom Time` as time from `RB` to `LB`.
- The runtime must not start the first O2 stop timer before `On O2` confirmation.
- The runtime must not treat ascent travel time between later stops as separate from
  the subsequent stop’s required stop time.
- The runtime must not infer table lookup from a shallower depth or shorter time
  than the operator-confirmed maximum depth and bottom time.

## Display Requirements

- Status:
  - must use domain-consistent state terms
- Main timer:
  - must reflect the currently active procedural timer, not a generic elapsed clock
- Depth row:
  - must reflect current or committed depth semantics honestly
- Next row:
  - must describe the next required procedural action
- Detail row:
  - may show hold/delay detail when active
- Event log:
  - must preserve operator-confirmed milestone ordering

## Notes

- Source material came from the AIR Decompression chapter and is now subordinate
  to the cited manual PDF rather than to earlier working notes.
- This rule document defines vocabulary and timing semantics only. Delay corrections
  and worked examples are covered in separate docs.
- The live app uses an explicit operator-confirmed event model. Estimated travel or
  depth displays may be shown, but they do not autonomously advance the procedure.
- This document defines procedural `TSV`, not necessarily the exact UI moment when
  the app switches its visible status label to `TSV`.
- Surface decompression and repetitive-dive / residual-nitrogen workflows are
  currently out of scope for the live runtime.

## Test Cases

- Happy path:
  - `AIR/O2` dive where first O2 stop begins timing only on `On O2`
- Edge case:
  - later stop timing includes travel from previous stop rather than restarting on
    arrival
- Regression case:
  - `TSV` anchor changes depending on whether the first O2 stop follows bottom
    directly or follows an air stop

## References

- Related CSV/table rows:
  - `docs/AIR.csv`
  - `docs/AIR_O2.csv`
- Related code paths:
  - `src/dive_stopwatch/core/engine.py`
  - `src/dive_stopwatch/core/profiles.py`
  - `src/dive_stopwatch/core/snapshot.py`
- Related scenarios:
  - `SCENARIO_air_80_50.md`
  - `SCENARIO_air_o2_150_40.md`
