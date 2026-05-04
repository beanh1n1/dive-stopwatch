# Active Refactor Spec

This is the only active implementation spec to consult for the upcoming
mode/profile refactor.

Older overlapping design/build specs have been archived under
[docs/archive](/Users/iananderson/projects/DiveStopwatchProject/docs/archive)
to reduce planning conflicts.

# Mode × Profile Refactor — Implementation Spec

**Branch**: `codex/engine-redesign`  
**Status**: Engine behavioral parity achieved (all four state machines tested); Mode × Profile
refactor not yet started — all six steps pending.  
**Objective**: Introduce a two-layer `DivingMode × DecoProfile` system that replaces the
current flat `EngineMode` enum as the user-facing concept, while keeping all engine state
machines untouched.

---

## 1. Problem Statement

`EngineMode` in `contracts/view.py` conflates two separate concepts:

| Current `EngineMode` value | What it actually means |
|---|---|
| `AIR` | Diving context: air-table dive, AIR-only deco |
| `AIR_O2` | Diving context: air-table dive, O2 deco |
| `MIXED_GAS` | Diving context: mixed-gas dive |
| `SURD` | *Deco profile intent* (pre-select surface deco) OR *active SURD execution* |
| `CHAMBER` | Standalone chamber operation |

`SURD` especially is overloaded: it is both a pre-dive profile choice AND a runtime
execution mode. The Coordinator compensates via the `_surface_active` flag, creating a
subtle dual-state dependency.

Additionally:
- Mixed Gas has no SURD handoff path despite sharing eligibility rules with AIR.
- SURD's `SURFACE_INTERVAL_EXCEEDED` penalty path (`SurdPenaltyKind.EXCEEDED`) is a dead
  branch — `build_surd_chamber_plan()` ignores it and no plan is produced.
- `Chamber` has no "Treatment" entry path for escalation from SURD.
- `Session._launch_mode()` special-cases `ChamberEngine` outside the Coordinator,
  creating a `EngineCoordinator | ChamberEngine` union type on `_engine`.

---

## 2. Target Design

### 2.1 Two-Layer Concept

```
DivingMode (user selects top level)
  AIR
  MIXED_GAS
  CHAMBER

DecoProfile (user selects within mode)
  AIR          — valid for DivingMode.AIR
  O2           — valid for DivingMode.AIR
  SURD         — valid for DivingMode.AIR and DivingMode.MIXED_GAS
  MIXED_GAS    — valid for DivingMode.MIXED_GAS
  TREATMENT    — valid for DivingMode.CHAMBER (auto-entered from SURD handoff, or manual)
  AIR (chamber)— valid for DivingMode.CHAMBER (standalone, same as current chamber)
```

### 2.2 Full Execution Graph

```
DivingMode.AIR
  DecoProfile.AIR     → AirEngine(DecoMode.AIR)
  DecoProfile.O2      → AirEngine(DecoMode.AIR_O2)
  DecoProfile.SURD    → AirEngine(DecoMode.AIR_O2)
                           └─ auto-handoff at L40 (existing _start_normal_surd_handoff)
                           └─ manual SWITCH_TO_SURD at 30/20 (existing _switch_to_surd)
                                 │
                                 ▼
DivingMode.MIXED_GAS          SurdEngine
  DecoProfile.MIXED_GAS         └─ SI > 7 min → SURFACE_INTERVAL_EXCEEDED
    → MixedGasEngine()                │
  DecoProfile.SURD                    ▼
    → MixedGasEngine()           ChamberEngine.start_treatment(SurdToChamberHandoff)
        └─ SWITCH_TO_SURD ──────▶ (DecoProfile.TREATMENT)
             at 40 fsw (L40_NORMAL)
             at 30/20 fsw (ADAPTER_30_20)

DivingMode.CHAMBER
  DecoProfile.AIR       → ChamberEngine() fresh (existing standalone flow)
  DecoProfile.TREATMENT → ChamberEngine.start_treatment(SurdToChamberHandoff)
                          (operator still selects TT5/6/6A; handoff provides context)
```

### 2.3 Handoff Contracts

Two immutable handoff structs form the hard seams:

1. **`InWaterToSurdHandoff`** — rename of `AirToSurdHandoff`; `source_mode: str` already
   accommodates both `"AIR_O2"` and `"MIXED_GAS"`.

2. **`SurdToChamberHandoff`** — new; created by SurdEngine when
   `phase == SURFACE_INTERVAL_EXCEEDED`.

### 2.4 Internal `EngineMode` Stays Intact

`EngineMode` in `contracts/view.py` is used inside every engine's `derive_view()` return.
**Do not remove or rename it.** It remains as the internal routing identifier on
`EngineView.mode`. The new `DivingMode` / `DecoProfile` enums live in `contracts/modes.py`
and are the public API. The mapping is done once in `EngineCoordinator.__init__`.

---

## 3. New Files (4)

### 3.1 `src/dive_stopwatch/engine_v2/contracts/modes.py`

```python
from __future__ import annotations
from enum import Enum, auto


class DivingMode(Enum):
    AIR = auto()
    MIXED_GAS = auto()
    CHAMBER = auto()


class DecoProfile(Enum):
    AIR = auto()         # AIR mode: air-only deco stops
    O2 = auto()          # AIR mode: O2 deco stops
    SURD = auto()        # AIR or MIXED_GAS: surface deco
    MIXED_GAS = auto()   # MIXED_GAS mode: full in-water mixed-gas
    TREATMENT = auto()   # CHAMBER mode: from SURD handoff or manual DCS treatment


VALID_PROFILES: dict[DivingMode, tuple[DecoProfile, ...]] = {
    DivingMode.AIR: (DecoProfile.AIR, DecoProfile.O2, DecoProfile.SURD),
    DivingMode.MIXED_GAS: (DecoProfile.MIXED_GAS, DecoProfile.SURD),
    DivingMode.CHAMBER: (DecoProfile.AIR, DecoProfile.TREATMENT),
}
```

### 3.2 `src/dive_stopwatch/engine_v2/contracts/chamber_handoff.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .events import AuditEvent
from .surd_handoff import SurdEntryKind


@dataclass(frozen=True)
class SurdToChamberHandoff:
    trigger: str                           # always "SURFACE_INTERVAL_EXCEEDED"
    surface_interval_elapsed_sec: float
    source_entry_kind: SurdEntryKind       # L40_NORMAL or ADAPTER_30_20
    input_depth_fsw: int
    input_bottom_time_min: int
    handed_off_at: datetime
    audit_tail: tuple[AuditEvent, ...] = ()
```

### 3.3 `src/dive_stopwatch/engine_v2/modes/mixed_gas/surd_handoff_builder.py`

Mirror of `modes/air/surd_handoff_builder.py` with these differences:
- Operates on `MixedGasState` instead of `AirState`
- `source_mode` is `"MIXED_GAS"` (literal string)
- Uses `MixedGasPhase.AT_STOP` and `state.plan.stops[state.current_stop_index]` for current
  stop (not `stop_by_index` from air profiles)
- Eligible depths are identical to AIR: `{40}` for L40_NORMAL, `{30, 20}` for ADAPTER_30_20
- `remaining_in_water_obligation_sec`: use `elapsed(state.stop_timer.timer, now)` against
  stop `duration_min * 60` to compute remaining, same pattern as AIR rules

```python
from __future__ import annotations
from datetime import datetime
from ...contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from .state import MixedGasPhase, MixedGasState


def can_build_surd_handoff(state: MixedGasState) -> bool:
    if state.phase is not MixedGasPhase.AT_STOP:
        return False
    if state.plan is None or state.current_stop_index is None:
        return False
    stops = state.plan.stops
    if state.current_stop_index >= len(stops):
        return False
    return stops[state.current_stop_index].depth_fsw in {30, 20}


def can_build_normal_surd_handoff(state: MixedGasState) -> bool:
    if state.phase is not MixedGasPhase.AT_STOP:
        return False
    if state.plan is None or state.current_stop_index is None:
        return False
    stops = state.plan.stops
    if state.current_stop_index >= len(stops):
        return False
    return stops[state.current_stop_index].depth_fsw == 40


def build_surd_handoff(state: MixedGasState, *, now: datetime,
                       audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    # ADAPTER_30_20 path
    ...  # implement analogous to air's build_surd_handoff


def build_normal_surd_handoff(state: MixedGasState, *, now: datetime,
                               audit_tail: tuple = ()) -> InWaterToSurdHandoff:
    # L40_NORMAL path
    ...  # implement analogous to air's build_normal_surd_handoff
```

### 3.4 `src/dive_stopwatch/engine_v2/modes/surd/chamber_handoff_builder.py`

```python
from __future__ import annotations
from datetime import datetime
from ...contracts.chamber_handoff import SurdToChamberHandoff
from ...contracts.timers import elapsed
from .state import SurdPhase, SurdState


def can_build_chamber_handoff(state: SurdState) -> bool:
    return state.phase is SurdPhase.SURFACE_INTERVAL_EXCEEDED


def build_chamber_handoff(state: SurdState, *, now: datetime,
                          audit_tail: tuple = ()) -> SurdToChamberHandoff:
    assert can_build_chamber_handoff(state)
    assert state.handoff is not None
    assert state.surface_interval_timer is not None
    return SurdToChamberHandoff(
        trigger="SURFACE_INTERVAL_EXCEEDED",
        surface_interval_elapsed_sec=elapsed(state.surface_interval_timer, now),
        source_entry_kind=state.handoff.entry_kind,
        input_depth_fsw=state.handoff.input_depth_fsw,
        input_bottom_time_min=state.handoff.input_bottom_time_min,
        handed_off_at=now,
        audit_tail=audit_tail,
    )
```

---

## 4. Renamed / Modified Contracts

### 4.1 Rename `AirToSurdHandoff` → `InWaterToSurdHandoff`

File: `src/dive_stopwatch/engine_v2/contracts/surd_handoff.py`

- Rename the dataclass to `InWaterToSurdHandoff`.
- Keep all fields identical — `source_mode: str` already handles `"MIXED_GAS"`.
- Add `__all__ = ["InWaterToSurdHandoff", "SurdEntryKind"]`.
- Update all import sites (grep for `AirToSurdHandoff`):
  - `modes/air/surd_handoff_builder.py` — return type annotation
  - `modes/air/engine.py` — return type annotation (`build_surd_handoff`, `build_normal_surd_handoff`)
  - `modes/surd/engine.py` — parameter annotation on `start_handoff`
  - `modes/surd/reducer.py` — import
  - `modes/surd/state.py` — field annotation on `SurdState.handoff`
  - `modes/surd/transitions/entry.py` — parameter annotation
  - `modes/mixed_gas/surd_handoff_builder.py` — return type (new file, Step 2)

---

## 5. Modified Files (7)

### 5.1 `modes/mixed_gas/engine.py`

Add four public methods (no state machine changes):

```python
from .surd_handoff_builder import (
    can_build_surd_handoff, can_build_normal_surd_handoff,
    build_surd_handoff, build_normal_surd_handoff,
)

class MixedGasEngine:
    # ... existing code unchanged ...

    def can_switch_to_surd(self) -> bool:
        return can_build_surd_handoff(self.state)

    def can_start_normal_surd_handoff(self) -> bool:
        return can_build_normal_surd_handoff(self.state)

    def build_surd_handoff(self) -> InWaterToSurdHandoff:
        return build_surd_handoff(self.state, now=self._now_provider(),
                                  audit_tail=self._events)

    def build_normal_surd_handoff(self) -> InWaterToSurdHandoff:
        return build_normal_surd_handoff(self.state, now=self._now_provider(),
                                         audit_tail=self._events)
```

### 5.2 `modes/surd/engine.py`

Add two public methods:

```python
from .chamber_handoff_builder import can_build_chamber_handoff, build_chamber_handoff
from ...contracts.chamber_handoff import SurdToChamberHandoff

class SurdEngine:
    # ... existing code unchanged ...

    def can_handoff_to_chamber(self) -> bool:
        return can_build_chamber_handoff(self.state)

    def build_chamber_handoff(self) -> SurdToChamberHandoff:
        return build_chamber_handoff(self.state, now=self._now_provider(),
                                     audit_tail=self._events)
```

### 5.3 `modes/chamber/engine.py`

Add one entry method for Treatment profile:

```python
from ...contracts.chamber_handoff import SurdToChamberHandoff

class ChamberEngine:
    # ... existing code unchanged ...

    def start_treatment(self, handoff: SurdToChamberHandoff) -> None:
        """Enter Treatment profile with context from a SURD handoff.
        
        Stores handoff context for display; operator still selects TT5/6/6A.
        The chamber execution state machine is identical to standalone AIR profile.
        """
        from dataclasses import replace
        self.state = replace(self.state, treatment_handoff=handoff)
```

Also update `ChamberState` in `modes/chamber/state.py` to add:

```python
from ...contracts.chamber_handoff import SurdToChamberHandoff

@dataclass(frozen=True)
class ChamberState:
    # ... existing fields unchanged ...
    treatment_handoff: SurdToChamberHandoff | None = None
```

The `treatment_handoff` field is display-only context; it does not change any phase
transitions or rules in the chamber state machine.

### 5.4 `runtime/coordinator.py`

This is the primary logic change. Replace the existing coordinator entirely with the
following design.

**Constructor signature changes:**

```python
# BEFORE
def __init__(self, *, mode: EngineMode, now_provider=None) -> None:

# AFTER
def __init__(self, *, diving_mode: DivingMode, deco_profile: DecoProfile,
             now_provider=None) -> None:
```

**Internal engine selection** (replaces the current ternary on line 26):

```python
from ..contracts.modes import DivingMode, DecoProfile
from ...legacy.core.air_o2_profiles import DecoMode

def _air_deco_mode(diving_mode: DivingMode, deco_profile: DecoProfile) -> DecoMode:
    if diving_mode is DivingMode.AIR and deco_profile is DecoProfile.AIR:
        return DecoMode.AIR
    return DecoMode.AIR_O2  # O2 and SURD both use AIR_O2 tables
```

**Active engine tracking** (replaces `_mode` + `_surface_active` flags):

```python
self._diving_mode = diving_mode
self._deco_profile = deco_profile
self._active: Literal["air", "mixed_gas", "surd", "chamber"] = _initial_active(diving_mode)
self._air: AirEngine | None = ...      # created if AIR mode
self._mixed_gas: MixedGasEngine | None = ...  # created if MIXED_GAS mode
self._surd: SurdEngine | None = SurdEngine(now_provider=...)   # always created
self._chamber: ChamberEngine | None = ChamberEngine(now_provider=...) # always created
```

**`_initial_active` helper:**
```python
def _initial_active(diving_mode: DivingMode) -> str:
    if diving_mode is DivingMode.CHAMBER:
        return "chamber"
    if diving_mode is DivingMode.MIXED_GAS:
        return "mixed_gas"
    return "air"
```

**`dispatch()` logic:**

```python
def dispatch(self, action: EngineAction) -> tuple[AuditEvent, ...]:
    self.tick()
    # SURD → Chamber auto-handoff check (fires after every SURD dispatch/tick)
    if self._active == "surd" and self._surd.can_handoff_to_chamber():
        return self._handoff_surd_to_chamber()
    # SWITCH_TO_SURD (manual mid-dive)
    if action is EngineAction.SWITCH_TO_SURD:
        return self._switch_to_surd()
    # AIR mode: auto L40 normal handoff when SURD profile pre-selected
    if (self._active == "air"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.LEAVE_STOP
            and self._air.can_start_normal_surd_handoff()):
        return self._start_normal_surd_handoff()
    # MIXED_GAS mode: auto L40 normal handoff when SURD profile pre-selected
    if (self._active == "mixed_gas"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.LEAVE_STOP
            and self._mixed_gas.can_start_normal_surd_handoff()):
        return self._start_normal_surd_handoff()
    # Normal routing
    if self._active == "mixed_gas":
        return self._mixed_gas.dispatch(action)
    if self._active == "surd":
        return self._surd.dispatch(action)
    if self._active == "chamber":
        return self._chamber.dispatch(action)
    return self._air.dispatch(action)
```

**`tick()` logic:**

```python
def tick(self) -> None:
    if self._active == "surd":
        self._surd.tick()
        if self._surd.can_handoff_to_chamber():
            self._handoff_surd_to_chamber()
```

**`view()` logic** — remove the SWITCH_TO_SURD suppression for AIR mode (line 68–70 in
current code); that suppression existed because `EngineMode.AIR` meant "no SURD planned",
but now the profile handles this. Instead, SWITCH_TO_SURD availability is determined
solely by the engine's own `can_switch_to_surd()`:

```python
def view(self) -> EngineView:
    self.tick()
    if self._active == "chamber":
        return self._chamber.view()
    if self._active == "surd":
        return self._surd.view()
    if self._active == "mixed_gas":
        return self._mixed_gas.view()
    return self._air.view()
```

**New private methods:**

```python
def _switch_to_surd(self) -> tuple[AuditEvent, ...]:
    now = self._now_provider()
    active_engine = self._mixed_gas if self._active == "mixed_gas" else self._air
    if not active_engine.can_switch_to_surd():
        return (AuditEvent(kind=AuditEventKind.INVALID_ACTION, at=now,
                           payload={"action": EngineAction.SWITCH_TO_SURD.name}),)
    handoff = active_engine.build_surd_handoff()
    self._surd.start_handoff(handoff)
    self._active = "surd"
    self._deco_profile = DecoProfile.SURD
    return (AuditEvent(kind=AuditEventKind.HANDOFF_CREATED, at=now,
                       payload={"entry_kind": handoff.entry_kind.name,
                                "left_water_stop_depth_fsw": handoff.left_water_stop_depth_fsw}),)

def _start_normal_surd_handoff(self) -> tuple[AuditEvent, ...]:
    now = self._now_provider()
    active_engine = self._mixed_gas if self._active == "mixed_gas" else self._air
    handoff = active_engine.build_normal_surd_handoff()
    self._surd.start_handoff(handoff)
    self._active = "surd"
    return (AuditEvent(kind=AuditEventKind.HANDOFF_CREATED, at=now,
                       payload={"entry_kind": handoff.entry_kind.name,
                                "left_water_stop_depth_fsw": handoff.left_water_stop_depth_fsw}),)

def _handoff_surd_to_chamber(self) -> tuple[AuditEvent, ...]:
    now = self._now_provider()
    handoff = self._surd.build_chamber_handoff()
    self._chamber.start_treatment(handoff)
    self._active = "chamber"
    self._deco_profile = DecoProfile.TREATMENT
    return (AuditEvent(kind=AuditEventKind.HANDOFF_CREATED, at=now,
                       payload={"trigger": handoff.trigger,
                                "surface_interval_elapsed_sec": handoff.surface_interval_elapsed_sec}),)
```

**`state()` method** — update to reflect new types:

```python
@dataclass(frozen=True)
class CoordinatorState:
    diving_mode: DivingMode
    deco_profile: DecoProfile
    active: str   # "air" | "mixed_gas" | "surd" | "chamber"
```

**Remove `_surface_active` flag entirely** — it is replaced by `_active == "surd"`.

**`selected_table_name()` and `tender_view()`** — delegate to chamber when active:

```python
def tender_view(self):
    if self._active == "chamber":
        return self._chamber.tender_view()
    return None

def selected_table_name(self) -> str | None:
    if self._active == "chamber":
        return self._chamber.selected_table_name()
    if self._active == "surd":
        return self._surd.schedule_label() or None
    return None
```

**Input routing methods** — replace `_mode` checks with `_active` checks (currently omitted
from existing coordinator; must be included in the rewrite):

```python
def set_depth(self, *, raw_text: str, depth_fsw: int | None) -> None:
    if self._active == "mixed_gas":
        self._mixed_gas.set_depth(raw_text=raw_text, depth_fsw=depth_fsw)
    elif self._active not in {"surd", "chamber"}:
        self._air.set_depth(raw_text=raw_text, depth_fsw=depth_fsw)

def set_bottom_mix(self, *, raw_text: str, bottom_mix_o2_percent: float | None) -> None:
    if self._active == "mixed_gas":
        self._mixed_gas.set_bottom_mix(raw_text=raw_text,
                                       bottom_mix_o2_percent=bottom_mix_o2_percent)

def set_relief_depth(self, depth_fsw: int | None) -> None:
    if self._active == "chamber":
        self._chamber.set_relief_depth(depth_fsw)

def depth_input_text(self) -> str:
    if self._active == "mixed_gas":
        return self._mixed_gas.state.depth_text
    if self._active in {"surd", "chamber"}:
        return ""
    return self._air.state.depth_text

def bottom_mix_input_text(self) -> str:
    if self._active == "mixed_gas":
        return self._mixed_gas.state.bottom_mix_o2_text
    return ""

def relief_depth_input_text(self) -> str:
    if self._active == "chamber":
        return self._chamber.relief_depth_input_text()
    return ""

def schedule_label(self) -> str:
    if self._active == "surd":
        return self._surd.schedule_label()
    if self._active == "mixed_gas":
        return self._mixed_gas.schedule_label()
    if self._active == "chamber":
        return self._chamber.schedule_label()
    return self._air.schedule_label()
```

### 5.5 `runtime/session.py`

**Remove** the `EngineCoordinator | ChamberEngine` union. `_engine` is always
`EngineCoordinator`.

```python
# BEFORE
self._engine: EngineCoordinator | ChamberEngine

# AFTER
self._engine: EngineCoordinator
```

**Replace `launch_mode(mode: EngineMode)`** with:

```python
def launch(self, diving_mode: DivingMode,
           deco_profile: DecoProfile | None = None) -> None:
    if deco_profile is None:
        deco_profile = VALID_PROFILES[diving_mode][0]  # first is default
    self._diving_mode = diving_mode
    self._deco_profile = deco_profile
    self._audit_events = ()
    self._engine = EngineCoordinator(
        diving_mode=diving_mode,
        deco_profile=deco_profile,
        now_provider=self._now,
    )
    self._append_runtime_event(
        AuditEventKind.MODE_LAUNCHED,
        {"diving_mode": diving_mode.name, "deco_profile": deco_profile.name},
    )
```

**Add `set_deco_profile()`** (READY-state only; guard not strictly enforced in engine, but
semantically required):

```python
def set_deco_profile(self, profile: DecoProfile) -> None:
    self.launch(self._diving_mode, profile)
```

**Add properties:**

```python
@property
def diving_mode(self) -> DivingMode:
    return self._diving_mode

@property
def deco_profile(self) -> DecoProfile:
    return self._deco_profile
```

**Keep `launch_mode(mode: EngineMode)` as a deprecated shim** to avoid breaking existing
tests (many call `session.launch_mode(EngineMode.AIR)` etc.). The shim maps old
`EngineMode` values to `DivingMode + DecoProfile`:

```python
_ENGINE_MODE_MAP: dict[EngineMode, tuple[DivingMode, DecoProfile]] = {
    EngineMode.AIR:       (DivingMode.AIR, DecoProfile.AIR),
    EngineMode.AIR_O2:    (DivingMode.AIR, DecoProfile.O2),
    EngineMode.MIXED_GAS: (DivingMode.MIXED_GAS, DecoProfile.MIXED_GAS),
    EngineMode.SURD:      (DivingMode.AIR, DecoProfile.SURD),
    EngineMode.CHAMBER:   (DivingMode.CHAMBER, DecoProfile.AIR),
}

def launch_mode(self, mode: EngineMode) -> None:
    dm, dp = _ENGINE_MODE_MAP[mode]
    self.launch(dm, dp)
```

**Remove `_launch_mode()` private method** — its logic moves into `launch()`.

**Update `presentation_model()`** — `mode_name` should reflect `DivingMode × DecoProfile`,
and the dive log mode argument should use the engine view (not `self._mode`) to stay aligned
with `EngineView.mode` (Invariant 4):

```python
view = self._engine.view()
base = build_presentation_model(
    view,
    log_rows=build_dive_log(self._audit_events, mode=view.mode),
    ...
)
return replace(base,
    title=_title_for_mode(self._diving_mode),
    mode_name=f"{self._diving_mode.name}/{self._deco_profile.name}")
```

**Update `_title_for_mode()`** — signature changes from `EngineMode` to `DivingMode`:

```python
def _title_for_mode(diving_mode: DivingMode) -> str:
    return "CAISSON Chamber" if diving_mode is DivingMode.CHAMBER else "CAISSON Active"
```

**Update `EngineMode` guards in input-event helpers** — three methods in session currently
guard audit events with legacy `EngineMode` checks; replace with `DivingMode`:

```python
# set_depth_text — change:
if self._mode is not EngineMode.CHAMBER:
# to:
if self._diving_mode is not DivingMode.CHAMBER:

# set_relief_depth_text — change:
if self._mode is EngineMode.CHAMBER:
# to:
if self._diving_mode is DivingMode.CHAMBER:

# set_bottom_mix_text — change:
if self._mode is EngineMode.MIXED_GAS:
# to:
if self._diving_mode is DivingMode.MIXED_GAS:
```

### 5.6 `modes/surd/plan.py`

Remove the incomplete `EXCEEDED` branch from `build_surd_chamber_plan()`. The `EXCEEDED`
case is now fully handled by the Coordinator's `_handoff_surd_to_chamber()` — SURD never
needs to build a plan for it.

Note: the `SURFACE_INTERVAL_EXCEEDED` transition in `transitions/surface_interval.py`
(`reach_chamber_50`, line 41) already correctly sets `phase=SurdPhase.SURFACE_INTERVAL_EXCEEDED`
and `chamber_plan=None`. The assert below is purely a safety net confirming EXCEEDED never
reaches the plan builder after the coordinator handoff is wired.

**Before** (lines 30-34 reference):
```python
class SurdPenaltyKind(Enum):
    NONE = auto()
    PLUS_15_AT_50 = auto()
    EXCEEDED = auto()
```

**After** — keep `EXCEEDED` in the enum (it is the phase signal that Coordinator reads
via `can_build_chamber_handoff()`), but `build_surd_chamber_plan()` should assert it is
never called with `EXCEEDED`:

```python
def build_surd_chamber_plan(*, input_depth_fsw: int, input_bottom_time_min: int,
                             penalty_kind: SurdPenaltyKind) -> SurdChamberPlan:
    assert penalty_kind is not SurdPenaltyKind.EXCEEDED, \
        "EXCEEDED penalty must be handled by Coordinator handoff, not SURD plan builder"
    # ... rest of existing code unchanged ...
```

### 5.7 `mobile/gui_v2.py`

**Keep a single mode tile and use ready-state button 2 as the deco selector.**

```python
# Mode tile — cycles DivingMode (AIR | Mixed Gas | Chamber)
# Only active in READY phase
self.mode_chip = ft.Container(...)

# Ready-state button 2 — "Select Deco" for AIR and MIXED_GAS, blank for CHAMBER
# In-water button 2 continues to be driven by available_actions
```

**`_cycle_mode()` replacement:**

```python
def _cycle_diving_mode(self) -> None:
    modes = (DivingMode.AIR, DivingMode.MIXED_GAS, DivingMode.CHAMBER)
    next_mode = modes[(modes.index(self.session.diving_mode) + 1) % len(modes)]
    self.session.launch(next_mode)
    self._clear_inputs()
    self._render()

def _ready_deco_options(self) -> tuple[DecoProfile, ...]:
    if self.session.diving_mode is DivingMode.AIR:
        return (DecoProfile.O2, DecoProfile.SURD)
    if self.session.diving_mode is DivingMode.MIXED_GAS:
        return (DecoProfile.SURD,)
    return ()
```

**Ready-state button 2 behavior:**

```python
def _ready_secondary_label(self) -> str:
    if self.session.diving_mode is DivingMode.CHAMBER:
        return ""
    return "Select Deco"

def _ready_secondary_options(self) -> tuple[DecoProfile, ...]:
    return self._ready_deco_options()

def _on_ready_secondary(self) -> None:
    # Open dropdown anchored to button 2; selecting an option calls set_deco_profile(...)
    ...
```

Defaults when no option is selected:
- `DivingMode.AIR` implies `DecoProfile.AIR`
- `DivingMode.MIXED_GAS` implies `DecoProfile.MIXED_GAS`
- `DivingMode.CHAMBER` implies `DecoProfile.AIR`

Selecting an alternate ready-state profile updates the mode tile text, while button 2
continues to display `Select Deco`.

Examples:
- `AIR` → `AIR/O2`
- `AIR` → `AIR/SURD`
- `Mixed Gas` → `Mixed Gas/SURD`

**Mode tile display labels:**

```python
def _mode_tile_label(diving_mode: DivingMode, deco_profile: DecoProfile) -> str:
    if diving_mode is DivingMode.AIR and deco_profile is DecoProfile.O2:
        return "AIR/O2"
    if diving_mode is DivingMode.AIR and deco_profile is DecoProfile.SURD:
        return "AIR/SURD"
    if diving_mode is DivingMode.MIXED_GAS and deco_profile is DecoProfile.SURD:
        return "Mixed Gas/SURD"
    if diving_mode is DivingMode.MIXED_GAS:
        return "Mixed Gas"
    if diving_mode is DivingMode.CHAMBER:
        return "CHAMBER"
    return "AIR"
```

**In-water SURD selection:**

- If `SWITCH_TO_SURD` appears in `view.available_actions`, button 2 continues to occupy the
  same control position and dispatches `SWITCH_TO_SURD`.
- This keeps SURD reachable both as a ready-state preselection and as an in-water switch.
- No second chip is introduced.

---

## 6. `available_actions` in EngineView

`SWITCH_TO_SURD` must appear in `EngineView.available_actions` for both AirEngine and
MixedGasEngine when at an eligible stop.

**AirEngine** already emits `SWITCH_TO_SURD` in `available_actions` from `queries.py`.
The Coordinator previously **stripped** it when mode was `EngineMode.AIR` (lines 68–70
in current `coordinator.py`). **Remove that stripping** — profile awareness now determines
whether SURD is reachable, not the Coordinator's view filter.

**MixedGasEngine** — update `queries.py` to include `SWITCH_TO_SURD` in
`available_actions` when `can_build_surd_handoff(state)` is true (AT_STOP at 30/20 fsw)
or `can_build_normal_surd_handoff(state)` is true (AT_STOP at 40 fsw).

---

## 7. Implementation Sequence

Execute in order. Each step must leave the test suite green before proceeding.

```
Step 1 — New contracts (no logic yet)
  contracts/modes.py           (create)
  contracts/chamber_handoff.py  (create)
  contracts/surd_handoff.py     (rename AirToSurdHandoff → InWaterToSurdHandoff)
  Update all import sites for the rename (grep: AirToSurdHandoff)

Step 2 — Mixed Gas SURD handoff builder
  modes/mixed_gas/surd_handoff_builder.py  (create)
  modes/mixed_gas/engine.py               (add 4 methods)
  modes/mixed_gas/queries.py              (emit SWITCH_TO_SURD in available_actions)

Step 3 — SURD → Chamber handoff
  modes/surd/chamber_handoff_builder.py  (create)
  modes/surd/engine.py                   (add 2 methods)
  modes/surd/plan.py                     (add assert for EXCEEDED, keep enum value)
  modes/chamber/state.py                 (add treatment_handoff field)
  modes/chamber/engine.py                (add start_treatment method)

Step 4 — Coordinator refactor
  runtime/coordinator.py  (full rewrite as described in §5.4)
  - Remove _surface_active flag
  - Add _active: Literal["air","mixed_gas","surd","chamber"]
  - Add _handoff_surd_to_chamber()
  - Generalize _switch_to_surd() to work from mixed_gas
  - Remove SWITCH_TO_SURD suppression in view()

Step 5 — Session refactor
  runtime/session.py  (as described in §5.5)
  - Remove | ChamberEngine union
  - Add launch(DivingMode, DecoProfile) as primary API
  - Keep launch_mode(EngineMode) shim for test compatibility

Step 6 — GUI update
  mobile/gui_v2.py  (single mode tile + ready-state "Select Deco" flow as described in §5.7)
```

---

## 8. Do Not Touch

The following files must remain **byte-for-byte identical** unless touched by steps above:

- `modes/air/engine.py`, `state.py`, `reducer.py`, `queries.py`, `rules.py`, `plan.py`,
  `invariants.py`, `transitions/`
- `modes/surd/state.py`, `reducer.py`, `queries.py`, `rules.py`, `invariants.py`,
  `transitions/`
- `modes/mixed_gas/state.py`, `reducer.py`, `rules.py`, `invariants.py`, `transitions/`
  (Note: `modes/mixed_gas/engine.py` and `modes/mixed_gas/queries.py` **are** modified by Step 2)
- `modes/chamber/reducer.py`, `queries.py`, `rules.py`, `plan.py`, `invariants.py`,
  `tender.py`
- `contracts/actions.py`, `contracts/events.py`, `contracts/view.py`, `contracts/timers.py`
- `projection/presentation_builder.py`, `projection/dive_log.py`
- All files in `legacy/`

---

## 9. Test Requirements

### 9.1 Existing Tests Must Pass Without Modification

All tests in `tests/engine_v2/` must pass after Step 5 due to the `launch_mode()` shim.
Do not modify existing test files to accommodate the refactor.

### 9.2 New Tests Required

Create `tests/engine_v2/test_engine_v2_mode_profile.py`:

**Profile selection (READY phase):**
- `test_air_mode_default_profile_is_air` — `launch(DivingMode.AIR)` → `deco_profile == DecoProfile.AIR`
- `test_mixed_gas_default_profile_is_mixed_gas`
- `test_chamber_default_profile_is_air`
- `test_set_deco_profile_o2` — launch AIR, set_deco_profile(O2), engine is AIR_O2
- `test_set_deco_profile_surd_air_mode` — launch AIR, set_deco_profile(SURD), engine is AIR_O2

**Mid-dive profile switch (AIR → SURD):**
- `test_air_o2_mode_switch_to_surd_at_40fsw` — dive, reach 40 fsw stop, dispatch
  SWITCH_TO_SURD, verify coordinator._active == "surd"
- `test_surd_pre_selected_auto_handoff_at_40fsw` — launch AIR+SURD, dive to 40 fsw stop,
  dispatch LEAVE_STOP, verify auto-handoff fires without explicit SWITCH_TO_SURD

**Mid-dive profile switch (Mixed Gas → SURD):**
- `test_mixed_gas_switch_to_surd_at_40fsw` — mixed gas dive to 40 fsw stop,
  dispatch SWITCH_TO_SURD, verify coordinator._active == "surd"
- `test_mixed_gas_switch_to_surd_at_30fsw` — same but at 30 fsw (ADAPTER_30_20)

**SURD → Chamber handoff:**
- `test_surd_surface_interval_exceeded_triggers_chamber_handoff` — complete in-water
  phase, SURD handoff, advance test time > 7 min, dispatch REACH_CHAMBER_50, verify
  coordinator._active == "chamber" and coordinator._deco_profile == DecoProfile.TREATMENT
- `test_chamber_treatment_has_handoff_context` — verify `chamber.state.treatment_handoff`
  is populated after SURD → Chamber transition

**Chamber standalone Treatment profile:**
- `test_chamber_manual_treatment_profile` — `launch(DivingMode.CHAMBER, DecoProfile.TREATMENT)`,
  verify engine is ChamberEngine (no handoff pre-loaded, but profile label is TREATMENT)

---

## 10. Key Invariants

1. **Engine state machines are pure.** No transitions, reducers, or query functions receive
   `DivingMode` or `DecoProfile` as arguments. Profile-awareness lives only in Coordinator.

2. **Handoffs are one-way.** After `_switch_to_surd()`, the Coordinator never dispatches
   back to `_air` or `_mixed_gas`. After `_handoff_surd_to_chamber()`, it never dispatches
   back to `_surd`. `_active` is monotonically forward.

3. **RESET action resets active engine only.** Dispatching `RESET` calls the active engine's
   reducer with RESET. It does not reset the Coordinator's `_active` flag. A full session
   reset requires `session.launch()`.

4. **`EngineMode` on `EngineView.mode` is unchanged.** All existing views that read
   `view.mode` (presentation_builder, tests) continue to receive `EngineMode.AIR`,
   `EngineMode.AIR_O2`, `EngineMode.MIXED_GAS`, `EngineMode.SURD`, or `EngineMode.CHAMBER`.
   The new `DivingMode` / `DecoProfile` do not appear on `EngineView`.

5. **`available_actions` drives in-water SURD UI.** The button-2 "Switch → SURD"
   affordance is driven by `SWITCH_TO_SURD` appearing in `view.available_actions`, not by
   hardcoded phase/mode checks in the GUI.

6. **Mixed Gas SURD stop eligibility is identical to AIR.** The `surd_handoff_builder.py`
   for Mixed Gas must use the same depth thresholds: `{40}` for L40_NORMAL,
   `{30, 20}` for ADAPTER_30_20.

7. **`SurdPenaltyKind.EXCEEDED` remains in the enum** — it is the state signal that
   `can_build_chamber_handoff()` reads. Do not delete it.

8. **`treatment_handoff` on `ChamberState` is display-only.** No chamber reducer, rule, or
   transition reads it. It is purely for presentation context (e.g., showing dive history
   in the chamber UI).

---

## 11. Current Code Anchors (for grep / navigation)

| Symbol | File | Line |
|---|---|---|
| `EngineMode` enum | `contracts/view.py` | 7 |
| `AirToSurdHandoff` | `contracts/surd_handoff.py` | 16 |
| `SurdPenaltyKind` | `modes/surd/plan.py` | 9 |
| `SurdPhase.SURFACE_INTERVAL_EXCEEDED` | `modes/surd/state.py` | 16 |
| `reach_chamber_50` (EXCEEDED branch) | `modes/surd/transitions/surface_interval.py` | 41 |
| `_cycle_mode()` in GUI | `mobile/gui_v2.py` | 412 |
| Coordinator `air_mode` ternary | `runtime/coordinator.py` | 26 |
| Coordinator `_switch_to_surd` | `runtime/coordinator.py` | 101 |
| Coordinator SWITCH_TO_SURD suppression | `runtime/coordinator.py` | 68 |
| Session `_launch_mode` | `runtime/session.py` | 124 |
| Session `_engine` type annotation | `runtime/session.py` | 21 |
| `can_build_surd_handoff` (AIR) | `modes/air/surd_handoff_builder.py` | 11 |
| `MixedGasPhase.AT_STOP` | `modes/mixed_gas/state.py` | 17 |
| `MixedGasPlan.stops` tuple | `modes/mixed_gas/state.py` | 68 |
| `MixedGasEngine` (no SURD methods yet) | `modes/mixed_gas/engine.py` | 14 |
# Active Refactor Spec

This is the only active implementation spec to consult for the upcoming
mode/profile refactor.

The following older design/build specs have been archived under
[docs/archive](/Users/iananderson/projects/DiveStopwatchProject/docs/archive)
to reduce planning conflicts:

- `CHAMBER_AGENT_EXTRACTION_SPEC.md`
- `ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md`
- `ENGINE_HANDOFF_CONTRACTS.md`
- `ENGINE_REDESIGN_PLAN.md`
- `ENGINE_SNAPSHOT_REDESIGN_NOTES.md`
- `ENGINE_SURD_RUNTIME_SPEC.md`
- `ENGINE_V2_MIXED_GAS_BUILD_CHECKLIST.md`
- `ENGINE_V2_MIXED_GAS_PARITY.md`
- `MIXED_GAS_BUILD_PROMPT.md`
- `SURFACE_ENGINE_DRAFT.md`
