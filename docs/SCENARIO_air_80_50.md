# Scenario: AIR 80 fsw / 50 min

Status: Draft

Rule IDs:
- `9-6.4`
- `9-6.5`
- `9-8.1`

Authority:
- [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)

Manual citation:
- `9-6.4` stop timing semantics
- `9-6.5` last water stop
- `9-8.1` in-water decompression on air

Scope status:
- Implemented with app-specific operator-confirmed workflow

## Purpose

Validate a straightforward in-water air decompression lookup and resulting stop
schedule.

## Setup

- Mode: `AIR`
- Max Depth: `78 fsw`, table depth `80 fsw`
- Bottom Time: `47 min`, table bottom time `50 min`
- Starting assumptions:
  - direct table entry uses next deeper depth and next longer bottom time
  - ascent rate is `30 fsw/min`

## Event Sequence

1. `LS`
2. `RB`
3. `LB`
4. `R1`
5. `L1`
6. `RS`

## Expected State By Step

### Step 1: `LS`

- Status: `DESCENT`
- Main timer meaning: total elapsed dive time from surface departure
- Depth row: estimated live depth during descent
- Next row: table outcome not yet committed until bottom time is known
- Detail row: blank unless hold/delay is active
- Allowed buttons: reach bottom, hold

### Step 2: `RB`

- Status: `BOTTOM`
- Main timer meaning: dive elapsed time from `LS`
- Depth row: committed max depth
- Next row: still depends on final bottom time at `LB`
- Detail row: blank
- Allowed buttons: leave bottom

### Step 3: `LB`

- Status: `TRAVELING`
- Main timer meaning: travel elapsed from leaving bottom
- Depth row: live/ascent depth
- Next row: `20 fsw for 17 min`
- Detail row: blank unless delay is active
- Allowed buttons: reach stop, delay

### Step 4: `R1`

- Status: `AT STOP`
- Main timer meaning: stop timer at `20 fsw`
- Depth row: `20 fsw | 17:00 left`
- Next row: `Surface`
- Detail row: blank
- Allowed buttons: leave stop

### Step 5: `L1`

- Status: `TRAVELING`
- Main timer meaning: travel elapsed from leaving `20 fsw`
- Depth row: live ascent depth
- Next row: `Surface`
- Detail row: blank
- Allowed buttons: reach surface

### Step 6: `RS`

- Status: `CLEAN TIME`
- Main timer meaning: clean-time countdown
- Depth row: final table/schedule summary
- Next row: `Monitor diver for signs and symptoms of AGE`
- Detail row: blank
- Allowed buttons: none

## Critical Assertions

- Table entry rounds `78 fsw` to `80 fsw`.
- Table entry rounds `47 min` to `50 min`.
- Required decompression is a single `20 fsw` stop for `17 min`.
- The repetitive group designator for the worked example is `M`.
- Direct ascent without stops is not used once this table row is selected.

## Forbidden Outcomes

- Failure: selecting a shallower or shorter table entry
- Failure: showing an intermediate stop not present in the schedule
- Failure: omitting the required `20 fsw` stop

## References

- Related rules:
  - `RULE_core_definitions.md`
- Related CSV/table rows:
  - `docs/AIR.csv`
- Related tests:
  - `tests/test_tables.py`
