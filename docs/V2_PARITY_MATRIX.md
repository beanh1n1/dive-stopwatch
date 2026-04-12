# V2 Parity Matrix

This is the canonical contract for v2 behavior parity with prior legacy dive logic.

## Scope

- The v2 kernel must preserve all safety-critical procedure/rule behavior from legacy.
- UI/presentation wording may differ.
- Legacy files are not the target architecture; parity is enforced by the v2 parity test suite.

## Runtime Goal

- Single shared kernel for:
  - microcontroller frontend
  - phone frontend
  - desktop test harness
- Minimize redundancy and repeated rescans.
- Prefer O(1) incremental state updates during normal operation.

## Required Rule Areas

Status key:
- `P0`: safety-critical, required before legacy deletion.
- `P1`: required parity after P0, not blocker for first field test.
- `P2`: nice-to-have parity details.

### Dive phase and transitions

- [x] `P0` `READY -> DESCENT -> BOTTOM -> ASCENT -> SURFACE/CLEAN`
- [x] `P0` ascent stop arrival/departure sequencing
- [x] `P0` descent hold start/end sequencing
- [x] `P0` ascent delay start/end sequencing

### Timer anchor rules

- [x] `P0` first air stop timer starts on first `Reach Stop`
- [x] `P0` later air stop timer starts on previous `Leave Stop`
- [x] `P0` first O2 stop timer starts on `On O2`
- [x] `P0` 20 fsw O2 stop timer starts on leave 30 fsw
- [x] `P0` TSV timing anchor behavior
- [x] `P0` air-break timer anchors

### Delay rules and boundaries

- [x] `P0` first-stop delay handling outcomes
- [x] `P0` between/leave-stop delay handling outcomes
- [x] `P0` `<= 1:00` treated as ignore branch
- [x] `P0` `<= 50 fsw` treated as shallow branch
- [x] `P0` recompute schedule branch behavior and profile selection

### AIR/O2 procedure rules

- [x] `P0` first oxygen confirmation gate at first O2 stop
- [x] `P0` active O2 mode detection
- [x] `P0` air break eligibility rule
- [x] `P0` oxygen elapsed and break-due threshold
- [x] `P0` ignored-air intervals during break windows
- [x] `P0` 30->20 O2 credit behavior
- [x] `P0` remaining oxygen obligation behavior
- [x] `P0` shift-to-air-for-surface behavior

### Next-action semantics

- [x] `P0` `Next` means next required action, not only next stop
- [x] `P0` air-break next-action precedence when due
- [x] `P1` oxygen-target styling metadata parity

### Presentation state contract

- [x] `P1` fixed status vocabulary:
  - `READY`
  - `DESCENT`
  - `BOTTOM`
  - `TRAVELING`
  - `AT STOP`
  - `AT O2 STOP`
  - `SURFACE`
- [x] `P1` line-2 timer-kind parity (state-driven)
- [x] `P1` line-3 depth/modifier parity
- [x] `P1` line-5 event text parity for hold/delay

### Logs

- [x] `P1` chronological event/action logging in v2
- [x] `P2` rule-specific audit phrasing parity with legacy

## Deletion Gates

- Gate A: all `P0` checks passing in v2 parity tests.
- Gate B: all `P1` checks passing.
- Gate C: remove legacy runtime default paths.
- Gate D: delete legacy runtime modules after parity suite is green.

Current gate status:
- [x] Gate A complete
- [x] Gate B complete
- [x] Gate C complete
- [x] Gate D complete (minimal compatibility file retained at `legacy/__init__.py`)

## Test Strategy

- Differential scenario tests:
  - run same event sequence against legacy and v2
  - compare normalized procedure outputs
  - compare key timer anchors and next-action outcomes
- Rule boundary tests:
  - explicit checks at `1:00`, `50 fsw`, first O2 confirmation, break thresholds
- Frontend independence tests:
  - same kernel state/input must produce same outputs regardless of frontend
