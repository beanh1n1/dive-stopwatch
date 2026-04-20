# Scenario: AIR/O2 150 fsw / 40 min

Status: Draft

Rule IDs:
- `9-6.4`
- `9-6.5`
- `9-8.2`
- `9-8.2.1`
- `9-8.2.2`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-6.5` last water stop
- `9-8.2` in-water decompression on air and oxygen
- `9-8.2.1` procedures for shifting to 100% oxygen / TSV
- `9-8.2.2` air breaks at `30` and `20 fsw`
- worked example on pp. `9-14` to `9-15`

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Validate a worked AIR/O2 table entry with mixed air and oxygen decompression,
including O2 start, included travel time, and the required air break at `20 fsw`.

## Setup

- Mode: `AIR/O2`
- Max Depth: `145 fsw`, table depth `150 fsw`
- Bottom Time: `39 min`, table bottom time `40 min`
- Starting assumptions:
  - ascent rate is `30 fsw/min`
  - O2 stop time begins only when divers are confirmed on oxygen
  - the `30 -> 20` ascent time is included in the `20 fsw` O2 stop time

## Event Sequence

1. `LS`
2. `RB`
3. `LB`
4. `R1` at `50 fsw`
5. `L1`
6. `R2` at `40 fsw`
7. `L2`
8. `R3` at `30 fsw`
9. `On O2`
10. `L3`
11. `R4` at `20 fsw`
12. `Air break start`
13. `Air break end`
14. `L4`
15. `RS`

## Expected State By Step

### Step 4: `R1` at `50 fsw`

- Status: `AT STOP`
- Main timer meaning: first air-stop timer
- Depth row: `50 fsw | 02:00 left`
- Next row: `40 fsw for 6 min`
- Detail row: blank
- Allowed buttons: leave stop

### Step 6: `R2` at `40 fsw`

- Status: `AT STOP`
- Main timer meaning: subsequent stop timer includes prior travel by rule
- Depth row: `40 fsw | 06:00 left`
- Next row: `30 fsw for 7 min`
- Detail row: blank
- Allowed buttons: leave stop

### Step 8: `R3` at `30 fsw`

- Status: `TSV`
- Main timer meaning: transfer/shift/vent interval until O2 confirmation
- Depth row: `30 fsw | 07:00 left`
- Next row: `20 fsw for 35 min`
- Detail row: blank
- Allowed buttons: leave stop, `On O2`

### Step 9: `On O2`

- Status: `On O2`
- Main timer meaning: O2 elapsed time from confirmation
- Depth row: `30 fsw | 07:00 left`
- Next row: `20 fsw for 35 min`
- Detail row: blank
- Allowed buttons: leave stop, O2 control action when applicable

### Step 11: `R4` at `20 fsw`

- Status: `On O2`
- Main timer meaning: ongoing O2 elapsed timing
- Depth row: live/current stop display with remaining `20 fsw` obligation
- Next row: air break when due
- Detail row: blank
- Allowed buttons: leave stop, air-break action when due

### Step 12: Air break start

- Status: `Air Break`
- Main timer meaning: 5-minute air-break countdown
- Depth row: current depth with break countdown
- Next row: resume O2 with remaining obligation
- Detail row: blank
- Allowed buttons: air-break end only after required minimum

### Step 15: `RS`

- Status: `CLEAN TIME`
- Main timer meaning: clean-time countdown
- Depth row: final table/schedule summary
- Next row: `Monitor diver for signs and symptoms of AGE`
- Detail row: blank
- Allowed buttons: none

## Critical Assertions

- Table entry rounds `145 fsw` to `150 fsw`.
- Table entry rounds `39 min` to `40 min`.
- Required stops are:
  - `50 fsw` on air for `2 min`
  - `40 fsw` on air for `6 min`
  - `30 fsw` on O2 for `7 min`
  - `20 fsw` on O2 for `35 min`
- O2 stop timing at `30 fsw` begins only on `On O2`.
- The `30 -> 20` ascent time is included in the `20 fsw` O2 stop time.
- A five-minute air break is required during the `20 fsw` stop.
- The worked example total ascent time is `59 min 40 sec`, excluding the gas-shift
  time at `30 fsw`.
- The repetitive group designator for the worked example is `Z`.

## Forbidden Outcomes

- Failure: starting the `30 fsw` O2 timer on arrival before O2 confirmation
- Failure: restarting the `20 fsw` obligation incorrectly instead of honoring O2
  continuity rules
- Failure: omitting the required air break
- Failure: treating the `30 -> 20` ascent as outside the `20 fsw` O2 obligation

## References

- Related rules:
  - `RULE_core_definitions.md`
  - `RULE_delay_corrections.md`
- Related CSV/table rows:
  - `docs/AIR_O2.csv`
- Related tests:
  - `tests/test_tables.py`
  - `tests/test_core_engine.py`
