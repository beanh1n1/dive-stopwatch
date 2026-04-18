# Manual vs App Audit

Status: Draft  
Source reference: [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

## Purpose
This document records where the current app:
- matches the AIR Decompression chapter closely enough to be treated as aligned
- intentionally differs because the feature is out of scope
- previously drifted and therefore needs stronger contract/test discipline

This is a chapter-level audit, not a claim that every paragraph in Chapter 9 is fully implemented.

## Confirmed Alignments

### Stop timing includes travel to subsequent stops
Manual reference:
- Page 8: "ascent time between stops is included in the subsequent stop time"
- Page 8: "The same rules apply to in-water decompression on air/oxygen with the exception of the first stop on oxygen. The time at the first oxygen stop begins when all divers are confirmed on oxygen and ends when the divers leave the stop."

App status:
- aligned
- later stop timing is anchored from the previous leave-stop event
- first O2 stop timing is anchored from `On O2`

Relevant code:
- [/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/engine.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/engine.py)

### TSV timing
Manual reference:
- Page 13: for first O2 stop at `40 fsw` or deeper, TSV includes the `40 -> 30` ascent plus shift/vent/confirm
- Page 13: for first O2 stop at `30 fsw` or `20 fsw`, TSV excludes travel to the stop and includes only shift/vent/confirm

App status:
- aligned as a procedural rule
- display semantics are intentionally separate from procedural definition

### Continuous oxygen timing for air breaks
Manual reference:
- Page 13: "For purposes of timing air breaks, begin clocking oxygen time when all divers are confirmed on oxygen."
- Page 13: "If the total oxygen stop time is 35 minutes or less, an air break is not required at 30 minutes."
- Page 13: "If the final oxygen period is 35 minutes or less, a final air break at the 30-min mark is not required."
- Page 13: "In either case, surface the diver on 100% oxygen upon completion of the oxygen time."

App status:
- aligned after the April 17 correction
- continuous O2 exposure is tracked from `On O2`
- the `<= 35 min` terminal exception remains implemented

Relevant code:
- [/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/engine.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/engine.py)
- [/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/snapshot.py](/Users/iananderson/projects/DiveStopwatchProject/src/dive_stopwatch/minimal/snapshot.py)

## Previously Missed Drift

### Continuous O2 air-break rule was under-modeled
What drifted:
- the app and tests had hardened around a narrower rule where `Next:` often preferred the next stop and did not always surface the continuous-O2 air-break obligation correctly
- this allowed the wrong interpretation to survive test hardening

What corrected it:
- air-break timing is now keyed from continuous O2 exposure beginning at `On O2`
- delay and air-break tests were updated to reflect the manual wording rather than the earlier inferred behavior

Why this matters:
- this is the clearest recent example that agent hardening must start from manual extraction, not only from the current local contract

## Confirmed Intentional Scope Differences

### Surface decompression workflow
Manual coverage:
- Chapter 9 includes surface decompression procedures and related worksheet/chart material

App status:
- not implemented
- intentionally out of current scope

### Omitted decompression and recovery procedures
Manual coverage:
- later pages of the chapter include omitted stop handling, recovery procedures, chamber treatment escalation, and related emergency guidance

App status:
- not implemented as runtime workflow
- intentionally out of current scope for the current supervisory app

### Repetitive dive / altitude / residual nitrogen workflows
Manual coverage:
- later chapter sections include repetitive dives, altitude corrections, and worksheet-driven schedule derivation

App status:
- not implemented as active workflow
- repetitive group display exists, but repetitive-dive planning logic is out of scope

## Confirmed Manual-Backed Alignments Added During Hardening

### Oxygen-delay correction is now explicitly modeled
Manual coverage:
- `9-11.4` and `9-8.2.2` describe special handling for delays leaving the `30 fsw`
  oxygen stop, delays during O2 travel from `30` to `20`, and delays leaving the
  `20 fsw` oxygen stop.

App status:
- implemented for the current in-water runtime
- the runtime now has a distinct `30 -> 20` oxygen-delay correction path that
  subtracts qualifying O2 delay time from the subsequent `20 fsw` stop and resets
  the O2 segment when the delay exceeds the remaining continuous-O2 limit
- the runtime also has a distinct `20 fsw` departure-delay path that ignores the
  schedule change, shifts the diver to air once the continuous-O2 limit is reached,
  and resumes surface travel on oxygen when departure becomes possible

Why this matters:
- this was a real protocol branch that earlier test waves had missed
- it is now encoded as an explicit rule path instead of being inferred from the
  generic travel/delay model

## Operational Notes

### Operator-confirmed model remains intentional
The app still intentionally relies on explicit operator actions such as:
- `RB`
- `LB`
- `Reach Stop`
- `Leave Stop`
- `On O2`
- `RS`

This is not treated as a mismatch. It is a design choice to avoid unsafe inference.

### Estimated depth/travel display remains advisory
The app may display estimated current depth during descent/travel, but those displays do not autonomously advance protocol state.

## Next Hardening Recommendation
Before another broad agent hardening pass:

1. Read the relevant manual chapter or subsection first.
2. Extract explicit rule statements into repo docs.
3. Compare code/tests against those rule statements.
4. Only then write or broaden tests.

This sequencing is necessary because the recent continuous-O2 miss showed that agents can harden the wrong local contract if the manual is not treated as the first authority.
