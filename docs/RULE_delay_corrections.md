# Rule: delay corrections and recompute boundaries

Status: Draft

Rule IDs:
- `9-8.2.2` for oxygen-delay handling
- `Chapter 9, pp. 9-31 to 9-35` for ascent-delay guidance pending finer subsection mapping

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-8.2.2` air breaks at `30` and `20 fsw`
- Chapter 9 delay guidance on pp. `9-31` to `9-35`

Scope status:
- Partially Implemented

## Purpose

Define how ascent delays are handled, including when they are ignored, when they
change stop timing, and when they trigger schedule recomputation.

## Applies In

- Mode: `AIR`, `AIR/O2`
- Phase: `TRAVEL`, `AT_STOP`
- Related states: first stop arrival, between-stop travel, leaving a stop, O2 travel

## Preconditions

- A decompression ascent is in progress.
- Delay duration is measured from expected travel/leave timing against actual travel
  or stop departure timing.
- The diver is not sent deeper in order to recover a missed stop.

## Trigger

This rule applies when ascent to the first stop, ascent between stops, or leaving a
stop is delayed beyond expected travel timing.

## Expected Behavior

### First decompression stop

- Delay `<= 1 minute`:
  - ignore the delay
- Delay `> 1 minute`, `> 50 fsw`:
  - round the delay up to the next whole minute
  - add it to bottom time
  - recompute the decompression schedule
  - if no schedule change occurs, continue the planned schedule
  - if a new schedule is required and it calls for a stop deeper than current depth,
    perform missed deeper obligations at the diver’s current depth
  - do not send the diver deeper
- Delay `> 1 minute`, `<= 50 fsw`:
  - round the delay up to the next whole minute
  - add it to the first decompression stop time

### Leaving an air stop or between air stops

- Delay `<= 1 minute` leaving an air stop:
  - ignore the delay
- Delay `<= 1 minute` between air stops:
  - ignore the delay
- Delay `> 1 minute`, `> 50 fsw`:
  - add the delay to bottom time
  - recalculate decompression
  - if a new schedule is required, pick up the new schedule at the present or
    subsequent stop
  - ignore any missed stops or time deeper than the depth at which the delay
    occurred
- Delay `> 1 minute`, `<= 50 fsw`:
  - ignore the delay
  - resume the normal schedule after the delay

### Oxygen delays

- Delay leaving the `30 fsw` oxygen stop or during O2 travel from `30` to `20`:
  - subtract qualifying O2 delay time from the subsequent `20 fsw` O2 obligation
  - if total O2 time deeper than `20 fsw` would exceed `30 minutes`, shift to air at
    the `30-minute` mark
  - when the issue is resolved, shift back to O2 and resume decompression
  - ignore time spent on air during that interruption
- Delay leaving the `20 fsw` oxygen stop:
  - may be ignored
  - however, the diver must not remain on O2 longer than the allowed continuous O2
    period
  - if required, shift to air and remain on air until travel to surface is possible

## Forbidden Behavior

- The runtime must not recompute a schedule for delays of `<= 1 minute`.
- The runtime must not send the diver deeper to recover missed stops.
- The runtime must not treat shallow delays above the first stop the same way as
  deep delays above `50 fsw`.
- The runtime must not count ignored air-break time toward required O2 obligation.

## Display Requirements

- Status:
  - must remain aligned with actual phase and stop context during the delay
- Main timer:
  - must continue to reflect the active procedural timer
- Depth row:
  - must continue to reflect current procedural location and any active stop timing
- Next row:
  - must reflect the recomputed schedule when a recompute occurs
- Detail row:
  - may display active delay metadata while the delay is ongoing
- Event log:
  - must record schedule changes when recomputation changes the table/schedule

## Notes

- Source material originally came from working notes, but the governing authority
  is now the AIR Decompression chapter and the cited delay pages.
- This rule intentionally separates:
  - first-stop delays
  - air-stop departure/between-stop delays
  - oxygen delays
- The live runtime applies these rules only within the currently implemented
  in-water supervisory workflow.
- The broad ascent-delay logic has been mapped to the manual pages, but the exact
  subsection header should still be tightened in a later citation pass.
- Surface decompression delay handling described in the broader manual is currently
  out of scope.

## Test Cases

- Happy path:
  - first-stop delay `> 1 min` deeper than `50 fsw` triggers recompute
- Edge case:
  - first-stop delay `> 1 min` shallower than `50 fsw` adds time to first stop only
- Regression case:
  - `30 -> 20` oxygen travel delay subtracts from the `20 fsw` O2 obligation rather
    than restarting it

## References

- Related CSV/table rows:
  - rows requiring first stop deeper than `50 fsw`
  - AIR/O2 rows with O2 obligations at `30` and `20 fsw`
- Related code paths:
  - `src/dive_stopwatch/minimal/profiles.py`
  - `src/dive_stopwatch/minimal/engine.py`
  - `src/dive_stopwatch/minimal/snapshot.py`
- Related scenarios:
  - `SCENARIO_air_o2_150_40.md`
