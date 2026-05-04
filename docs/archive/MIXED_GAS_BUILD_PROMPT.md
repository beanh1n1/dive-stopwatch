# Mixed Gas Mode Build Prompt

Status: Ready for agent use  
Branch: `codex/engine-redesign`  
Working directory: `src/dive_stopwatch/engine_v2/`

---

## Your Task

Implement the `MIXED_GAS` mode for `engine_v2` as described in this document.
This is new behavior, not a refactor. The existing `AIR` and `SURD` engines must
not change. Follow the build sequence in this document and stop where it says to
stop.

Emergency procedures, abort-during-descent branches, repetitive dives, and
full chamber runtime for mixed-gas surface decompression are explicitly out of
scope.

---

## Required Reading Before Writing Any Code

Read these documents in full before writing any code. They are the authority
for this task. Do not substitute local inference for manual-backed rules.

**Primary mixed-gas source material:**

- [docs/Caisson_engine_V2_Mixed_Gas_notes.txt](Caisson_engine_V2_Mixed_Gas_notes.txt)
  — manual-extracted rules for sections 12-3 through 12-4.12, including gas
  families, descent, gas shifts, air breaks, delay rules, and surface
  decompression eligibility.

**Primary design documents:**

- [docs/ENGINE_V2_MIXED_GAS_PARITY.md](ENGINE_V2_MIXED_GAS_PARITY.md)
  — parity targets, reuse map, proposed state model, operator actions, handoff
  contract shape, test scaffold, and build sequence. This is the design authority.
- [docs/ENGINE_V2_MIXED_GAS_BUILD_CHECKLIST.md](ENGINE_V2_MIXED_GAS_BUILD_CHECKLIST.md)
  — phase-by-phase checklist with acceptance criteria per phase.

**Active architecture references:**

- [docs/ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md](ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md)
  — full transition contract for AIR/AIR-O2. Use this as the structural
  template. Mixed gas follows the same pattern where rules permit.
- [docs/ENGINE_HANDOFF_CONTRACTS.md](ENGINE_HANDOFF_CONTRACTS.md)
  — handoff contract design rules. Mixed-gas surface-decompression handoff must
  follow these rules. Do not reuse the AIR SURD handoff shape.
- [docs/ENGINE_GOLDEN_PATHS.md](ENGINE_GOLDEN_PATHS.md)
  — canonical behavioral paths for AIR and SURD. The mixed-gas build must not
  regress any of these.
- [docs/MANUAL_APP_MISMATCH_AUDIT.md](MANUAL_APP_MISMATCH_AUDIT.md)
  — lessons from prior audit cycles. Read the "Previously Missed Drift" section.
  The continuous-O2 miss described there is the canonical example of what happens
  when you harden against local contract instead of the manual.

**Existing mode to treat as structural template:**

- [src/dive_stopwatch/engine_v2/modes/air/](../src/dive_stopwatch/engine_v2/modes/air/)
  — read `state.py`, `engine.py`, `reducer.py`, `queries.py`, `rules.py`,
  `plan.py`, `invariants.py`, and each file under `transitions/`. The mixed-gas
  package must match this layout, not improve or generalize it.

**Existing contracts you must extend, not replace:**

- [src/dive_stopwatch/engine_v2/contracts/view.py](../src/dive_stopwatch/engine_v2/contracts/view.py)
- [src/dive_stopwatch/engine_v2/contracts/actions.py](../src/dive_stopwatch/engine_v2/contracts/actions.py)
- [src/dive_stopwatch/engine_v2/contracts/events.py](../src/dive_stopwatch/engine_v2/contracts/events.py)
- [src/dive_stopwatch/engine_v2/runtime/coordinator.py](../src/dive_stopwatch/engine_v2/runtime/coordinator.py)
- [src/dive_stopwatch/engine_v2/runtime/session.py](../src/dive_stopwatch/engine_v2/runtime/session.py)
- [src/dive_stopwatch/engine_v2/projection/presentation_builder.py](../src/dive_stopwatch/engine_v2/projection/presentation_builder.py)

**GUI entry point to wire:**

- [src/dive_stopwatch/mobile/gui_v2.py](../src/dive_stopwatch/mobile/gui_v2.py)

---

## What "Lessons Learned From the Audit" Means Here

The audit doc records two critical lessons that directly shape how you should
build mixed gas:

**Lesson 1: Extract from the manual before writing a rule.**  
The continuous-O2 air-break miss in AIR/O2 happened because the implementation
hardened against a narrower inferred rule rather than the actual manual wording.
For every behavioral rule you implement in mixed gas — delay logic, gas-shift
timing, air-break continuity across stops, the `<16% O2` grace window — read the
relevant section in `Caisson_engine_V2_Mixed_Gas_notes.txt` and the parity doc
before deciding what the code should do. If your implementation contradicts a
manual extract, the manual wins.

**Lesson 2: Runtime truth is explicit state, not inference.**  
The redesign made this principle central after prior engines required projection
code to search audit history to reconstruct anchors and phase identity. Every
timer anchor, every gas identity, every shift confirmation state, every delay
outcome must live as a field in `MixedGasState`. Projection and presentation code
must be pure reads from that state. Never let a query function call into the audit
log to decide what the current gas is or whether an air break is due.

These two lessons are not stylistic preferences. They are the direct cause-and-fix
of the failures the audit documents.

---

## Scope: What to Build in This Slice

Build phases 0 through 8 from the checklist, in order.

### In scope

- `EngineMode.MIXED_GAS` enum value
- `modes/mixed_gas/` package with the full file structure described below
- explicit phase model from `READY` through `COMPLETE`
- explicit breathing-gas identity and shift/confirmation state
- `>=16% O2` and `<16% O2` descent paths
- 5-minute grace-window rule for `<16% O2` bottom-time anchor
- decompression stop chain from bottom exit to surface
- `90 fsw` shift to `50/50` in both cases: when `90` is a stop and when it is
  not
- `30 fsw` shift to `100% O2` with explicit confirmation anchor
- continuous O2 carry from `30 fsw` to `20 fsw`
- air-break semantics at `30` and `20` including the `<=35 min` final suppression
- mixed-gas-specific delay rules from section `12-4.12`
- mixed-gas surface-decompression eligibility seam after completing `40 fsw`
- `MixedGasSurfaceHandoff` contract (define it; do not build the chamber runtime)
- coordinator and session wiring to allow mode launch from the GUI
- presentation labels for mixed-gas mode, gas identity, and gas confirmation state
- test files as described below

### Out of scope (do not build)

- abort-during-descent branches and descent emergency recovery
- repetitive mixed-gas planning
- mixed-gas surface-decompression chamber runtime
- generalized multi-diver synchronization
- unifying AIR/AIR-O2/MIXED_GAS behind a shared base class or super-engine

---

## File Structure to Create

```
src/dive_stopwatch/engine_v2/modes/mixed_gas/
    __init__.py
    state.py
    engine.py
    reducer.py
    queries.py
    rules.py
    plan.py
    invariants.py
    transitions/
        __init__.py
        descent.py
        gas_shift.py
        travel_stop.py
        delay.py
```

Do not add shared base classes or cross-mode helpers to accomplish this. Each
file should have exactly the scope its name implies, matching the `modes/air/`
precedent.

---

## State Design Requirements

These are mandatory, not suggestions.

### `MixedGasPhase` (in `state.py`)

```python
class MixedGasPhase(Enum):
    READY = auto()
    DESCENT_TO_20_ON_AIR = auto()       # <16% O2 path only
    AT_20_PREBOTTOM_SHIFT = auto()      # <16% O2 path only
    DESCENT_TO_BOTTOM = auto()
    BOTTOM = auto()
    TRAVEL_TO_FIRST_STOP = auto()
    AT_STOP = auto()
    TRAVEL_TO_SURFACE = auto()
    COMPLETE = auto()
```

Both `DESCENT_TO_20_ON_AIR` and `AT_20_PREBOTTOM_SHIFT` are only reachable when
the bottom mix is `<16% O2`. The normal path skips directly to
`DESCENT_TO_BOTTOM`.

### `MixedGasBreathingGas` (in `state.py`)

```python
class MixedGasBreathingGas(Enum):
    AIR = auto()
    BOTTOM_MIX = auto()
    HELIOX_50_50 = auto()
    OXYGEN = auto()
```

### `MixedGasShiftState` (in `state.py`)

```python
class MixedGasShiftState(Enum):
    NONE = auto()
    AWAITING_BOTTOM_MIX_CONFIRM = auto()
    AWAITING_50_50_CONFIRM = auto()
    AWAITING_O2_CONFIRM = auto()
    OFF_O2 = auto()
    AIR_BREAK = auto()
```

This separates what gas the schedule requires from what gas is confirmed in use.
That distinction is load-bearing for `30 fsw` stop timing and for `90 fsw` shift
behavior when there is no stop at `90`.

### `MixedGasState` (in `state.py`)

Must include at minimum:

- `phase: MixedGasPhase`
- `depth_text: str`
- `depth_fsw: int | None`
- `bottom_mix_o2_percent: float | None`
- `breathing_gas: MixedGasBreathingGas`
- `shift_state: MixedGasShiftState`
- explicit timer fields for: bottom, surface, travel, stop, shift, air break,
  clean time, and the grace-window countdown
- `plan: MixedGasPlan | None`
- `oxygen: MixedGasOxygenState` — continuous O2 exposure anchor and paused
  remaining obligation
- `delay: MixedGasDelayState`

Do not store computed values. Store anchors and let `queries.py` compute elapsed
and remaining from them.

---

## Operator Actions Required

Add these to the existing `EngineAction` contract. Do not create a parallel
action type.

New mixed-gas-specific actions:

- `CONFIRM_BOTTOM_MIX` — explicit confirmation that the diver is on bottom mix
  at `20 fsw` during `<16% O2` descent
- `CONFIRM_50_50` — explicit confirmation of gas shift at `90 fsw`
- `SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION` — initiates handoff after
  completing `40 fsw` water stop

All existing reusable actions apply:
`LEAVE_SURFACE`, `REACH_BOTTOM`, `LEAVE_BOTTOM`, `REACH_STOP`, `LEAVE_STOP`,
`CONFIRM_ON_O2`, `TOGGLE_OFF_O2`, `START_AIR_BREAK`, `END_AIR_BREAK`,
`START_DELAY`, `END_DELAY`, `REACH_SURFACE`, `RESET`.

Do not hide gas confirmations behind implicit arrival logic. Every gas shift
must require an explicit confirmation action before the shift is recorded as
active. This is not optional — the manual makes confirmations procedurally
required steps with timing consequences.

---

## Key Behavioral Rules by Section

These are the manual-backed rules you must implement. Each one maps to a section
of `Caisson_engine_V2_Mixed_Gas_notes.txt`. Read the source before coding the
rule.

### Descent (12-4.4, 12-4.5)

**`>=16% O2` path:**  
Phase goes directly `READY -> DESCENT_TO_BOTTOM`. Bottom time begins at
`LEAVE_SURFACE`.

**`<16% O2` path:**  
1. Diver starts on air (`AIR`), descends to `20 fsw`.
2. At `20 fsw`, shift to bottom mix. Operator confirms with `CONFIRM_BOTTOM_MIX`.
3. A 5-minute grace window begins. If the diver leaves `20 fsw` within 5 minutes,
   bottom time anchors to the moment of leaving `20 fsw`. If the diver exceeds
   5 minutes at `20 fsw`, bottom time anchors to the 5-minute mark.
4. Grace window must be explicit runtime state, not a display-only countdown.

The abort/restart branch in section 12-4.5 step 8 is out of scope.

### Gas shift at `90 fsw` (12-4.7)

All decompression dives require a shift from bottom mix to `50/50` at `90 fsw`.

- If there is a stop at `90 fsw`: ventilate the diver, confirm on `50/50` with
  `CONFIRM_50_50`. The shift confirmation time is included in stop time — the stop
  clock runs from arrival, not from confirmation.
- If there is no stop at `90 fsw`: `shift_state` moves to
  `AWAITING_50_50_CONFIRM` at depth. Delay ventilation and confirmation until
  arrival at the next shallower stop.

The distinction between "90 is a stop" and "90 is only a shift point" must be
explicit in the plan and in the transition logic.

### Gas shift at `30 fsw` (12-4.8)

All decompression dives require a shift to `100% O2` at `30 fsw`.

- The `30 fsw` stop clock begins only when the diver is confirmed on oxygen via
  `CONFIRM_ON_O2`.
- This is the opposite of the `90 fsw` rule. Do not conflate them.
- `shift_state` = `AWAITING_O2_CONFIRM` on arrival. Stop timing begins on
  explicit confirmation.

### Air breaks at `30` and `20 fsw` (12-4.9)

- Continuous O2 exposure is clocked from the moment all divers are confirmed on
  oxygen (`CONFIRM_ON_O2`). This anchor carries across the `30 -> 20` transition.
- Air break is required at 30 minutes of continuous O2 exposure.
- Air break is 5 minutes. Air-break time does not count toward decompression
  obligation.
- Suppression rule: if total O2 stop time is `<=35 min`, the first break is not
  required. If the final O2 period is `<=35 min`, the final break is not required.
- The `30 -> 20` travel time counts toward the `20 fsw` oxygen stop. Continuous
  O2 exposure must not reset on the stop transition.

The continuous-O2 carry across `30 -> 20` is the most common place to introduce
a regression. Read the audit doc's "Previously Missed Drift" section before
implementing this.

### Delay rules (12-4.12)

Mixed-gas delay rules differ from AIR delay rules. Implement them in
`transitions/delay.py` with explicit branching. Do not share delay logic with
the AIR engine.

Branches to implement:

1. **Delay to first stop, `<=1 min`:** ignore.
2. **Delay to first stop, `>1 min`:** round up and add to bottom time. Recompute
   from the updated bottom time.
3. **Delay deeper than `90 fsw`:** recompute at present or subsequent stop
   without going deeper.
4. **Delay between `90` and `70 fsw`, `<=5 min`:** ignore (resume normally).
5. **Delay between `90` and `70 fsw`, `>5 min`:** shift to air, recompute using
   the air-breathing rule.
6. **Delay at `90 fsw` and shallower (excluding the `>5 min` high-O2 case):**
   ignore `<1 min`, resume normally.
7. **Delay leaving `30 fsw`:** subtract delay from `20 fsw` stop time.

Each branch must be explicitly named and must emit an audit event with the branch
taken and the delta applied.

### Surface decompression eligibility (12-4.11)

Mixed-gas surface decompression eligibility becomes available after completing the
`40 fsw` water stop. This means `LEAVE_STOP` at `40 fsw` is the earliest moment
`SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION` becomes a valid action.

Do not reuse the AIR SURD handoff contract. Define a dedicated
`MixedGasSurfaceHandoff` as described in the parity doc.

The handoff must include at minimum:
- `bottom_mix_o2_percent`
- `left_water_stop_depth_fsw` (must be `40`)
- `completed_water_stop_depth_fsw`
- `input_depth_fsw`, `input_bottom_time_min`
- `source_table_depth_fsw`, `source_table_bottom_time_min`
- `handed_off_at`
- `audit_tail`

Do not build the chamber runtime beyond defining this contract.

---

## Coordinator and Session Wiring

Extend `coordinator.py` to route `EngineMode.MIXED_GAS` to a new
`MixedGasEngine` instance. Follow the exact same pattern as the AIR and SURD
routing — do not introduce a new dispatch architecture.

Extend `session.py` to support launching mixed-gas mode. Follow existing session
wiring conventions.

Extend `presentation_builder.py` only where mixed-gas labels require explicit
additions. New labels needed at minimum:

- mode chip: `Mixed Gas`
- gas labels: `Bottom Mix`, `50/50`, `O2`, `Air`
- confirmation prompt: `Next: Confirm Bottom Mix`, `Next: Confirm 50/50`
- handoff prompt: `Next: Surface Decompression`

Do not put mixed-gas procedural logic into `gui_v2.py` or
`presentation_builder.py`. Those layers are pure display. All truth lives in
`MixedGasState`.

---

## Test Files to Create

```
tests/engine_v2/test_engine_v2_mixed_gas_architecture.py
tests/engine_v2/test_engine_v2_mixed_gas_semantics.py
tests/engine_v2/test_engine_v2_mixed_gas_timers.py
tests/engine_v2/test_engine_v2_mixed_gas_presentation.py
```

### Mandatory test coverage

Write tests for each of these before considering a phase complete:

1. `EngineMode.MIXED_GAS` can be launched and projects a valid `EngineView`
   without crashing.
2. Normal `>=16% O2` descent anchors bottom time at `LEAVE_SURFACE`.
3. `<16% O2` path: grace window `<=5 min` anchors bottom time at departure from
   `20 fsw`.
4. `<16% O2` path: grace window `>5 min` anchors bottom time at the 5-minute
   mark.
5. First decompression stop times on arrival. Later stops include elapsed travel
   from the prior leave-stop.
6. `90 fsw` is a stop: shift state becomes `AWAITING_50_50_CONFIRM` on arrival;
   stop clock runs from arrival regardless of confirmation timing.
7. `90 fsw` is not a stop: `AWAITING_50_50_CONFIRM` is set at depth; confirmation
   is deferred until the next shallower stop.
8. `30 fsw` stop clock begins only on `CONFIRM_ON_O2`, not on arrival.
9. Continuous O2 exposure carries across the `30 -> 20` transition — the anchor
   is not reset on `REACH_STOP` at `20 fsw`.
10. Air break becomes required at exactly 30 minutes continuous O2.
11. Air-break time does not reduce the O2 decompression obligation.
12. `<=35 min` terminal O2 suppresses the air-break requirement correctly.
13. Delay `>1 min` to first stop recomputes the schedule.
14. Delay `>5 min` between `90` and `70 fsw` triggers air fallback.
15. Delay leaving `30 fsw` subtracts from the `20 fsw` obligation.
16. Surface-decompression eligibility action is not available before `LEAVE_STOP`
    at `40 fsw`.
17. Existing AIR, AIR-O2, and SURD golden paths do not regress.

Follow the test style in `tests/engine_v2/test_engine_v2_air_semantics.py` —
construct state directly, apply actions, and assert on explicit state fields.
Do not test display text as the primary behavioral assertion.

---

## Hard Constraints

These are non-negotiable:

- Do not overload `AIR_O2` or `AIR` mode to mean mixed gas for any case.
- Do not put behavioral truth in `presentation_builder.py` or `gui_v2.py`.
- Do not let `queries.py` or presentation code read the audit log to reconstruct
  phase or gas identity.
- Do not share delay logic between `modes/air` and `modes/mixed_gas`.
- Do not introduce shared base classes or abstract base classes for modes.
- Do not add optional parameters to existing AIR engine interfaces to accommodate
  mixed gas.
- The AIR, SURD, and CHAMBER engines must remain unmodified except for the
  minimum extensions to shared contracts (`EngineMode`, `EngineAction`).
- Every gas shift must be explicitly confirmed by an operator action before it is
  recorded as active in runtime state.

---

## Build Sequence

Work in this order. Do not skip phases.

1. **Phase 0** — Add `EngineMode.MIXED_GAS`. Verify no existing tests regress.
2. **Phase 1** — Create `modes/mixed_gas/` package skeleton. All files import
   cleanly. No runtime wiring yet.
3. **Phase 2** — Define `MixedGasState`, `MixedGasPhase`, `MixedGasBreathingGas`,
   `MixedGasShiftState`, and all supporting types. Implement `queries.py` to
   project `EngineView` from a manually constructed state. Write architecture
   smoke test.
4. **Phase 3** — Wire coordinator, session, and GUI ready-state. GUI can cycle
   into `MIXED_GAS`. Ready-state renders without crash.
5. **Phase 4** — Implement descent and bottom timing for both `>=16%` and `<16%`
   paths. Write descent and grace-window tests.
6. **Phase 5** — Implement stop chain: first-stop anchor-on-arrival, later-stop
   anchor-on-prior-leave, `90 fsw` shift (both cases), `30 fsw` O2 confirmation
   anchor, `30 -> 20` carry, final surface ascent.
7. **Phase 6** — Implement air-break semantics across `30` and `20`. Write
   continuous-O2 and air-break tests.
8. **Phase 7** — Implement mixed-gas-specific delay rules. Write delay branch
   tests.
9. **Phase 8** — Define `MixedGasSurfaceHandoff` and wire eligibility after
   `40 fsw`. Write eligibility tests. Stop here — do not build the chamber
   runtime.

Run the full test suite after each phase.

---

## Table Data Note

Table 12-4 (mixed-gas decompression schedules) is not yet represented as a CSV
in the repo. For the first implementation slice, bottom-mix percentage input
should be accepted as a free decimal value in the valid range for the given
depth (as defined in Table 12-4). Do not constrain the runtime contract to
whole-number percentages; the table includes fractional O2 bounds. Plan lookup
will require the table to exist as structured data before full stop schedule
resolution is possible.

If Table 12-4 data is not yet available:

- Implement all runtime state, transitions, and gas-shift semantics against a
  stub plan.
- Document the plan-loading gap explicitly in `plan.py`.
- Do not fake table data or hardcode schedules.

---

## Definition of Done for This Slice

- `EngineMode.MIXED_GAS` exists and is the only mixed-gas mode entry.
- `modes/mixed_gas/` package matches the `modes/air/` structure.
- All mandatory test cases pass.
- All AIR, SURD, and CHAMBER golden paths continue to pass.
- No behavioral rules live in presentation or GUI code.
- No projection code reads the audit log.
- `MixedGasSurfaceHandoff` is defined but the chamber runtime is not built.
