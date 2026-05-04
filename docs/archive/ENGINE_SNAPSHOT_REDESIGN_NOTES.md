# Engine Snapshot Redesign Notes

Status: Proposed  
Parent docs:
- [ENGINE_REDESIGN_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_REDESIGN_PLAN.md)
- [ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_AIR_AIR_O2_RUNTIME_SPEC.md)
- [ENGINE_SURD_RUNTIME_SPEC.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_SURD_RUNTIME_SPEC.md)
- [ENGINE_HANDOFF_CONTRACTS.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_HANDOFF_CONTRACTS.md)  
Behavioral reference: `main` at `6d115a9`

## Position

The current snapshot contract is useful and wrong.

Useful because:
- it gives us a stable display/test contract during the redesign
- it already locks important user-visible behavior through golden paths

Wrong because:
- it reflects old UI layout decisions more than explicit runtime meaning
- it forces AIR/AIR-O2 and SURD into one flattened display shape
- it encourages projector logic to do semantic interpretation work

The right move is not an immediate rewrite. The right move is to define what
the next snapshot contract should and should not represent, then redesign it
after runtime truth is stable.

## What To Preserve For Now

Keep the current snapshot contract in place until runtime/state contracts are
finished.

Reasons:
- golden-path fixtures already lock it
- it gives us a safe comparison surface between legacy and redesign runtimes
- changing runtime truth and display schema at the same time is needless risk

Preserve now:
- existing `Snapshot` shape
- current top-level user-visible strings where they are already locked
- projector-only compatibility rewrites needed for regression coverage

## What Is Wrong With The Current Snapshot Shape

### 1. It is too layout-shaped

Fields like:
- `primary_text`
- `primary_value_text`
- `remaining_text`
- `detail_text`
- `summary_text`

are presentation slots, not semantic runtime concepts.

They tell us where text goes on screen, not what the state means.

### 2. It mixes state meaning with styling meaning

Fields like:
- `status_value_kind`
- `primary_value_kind`
- `depth_timer_kind`
- `summary_value_kind`

mix:
- semantic severity
- gas context
- warning state
- UI color/styling intent

That is manageable for a transitional renderer and poor as a long-term contract.

### 3. It cannot express mode-specific semantics cleanly

Examples:
- AIR/O2 air break due vs active air break vs Off-O2 deviation
- SURD chamber waiting-on-O2 vs chamber On-O2 vs chamber Off-O2
- in-water to SURD handoff ownership

The current contract can display them, but only by overloading generic text
slots and value kinds.

### 4. It encourages projector inference

If the snapshot schema does not have a place for a concept, the projector has
to smuggle it into text.

That is exactly the failure mode we are trying to remove from the runtime.

## Snapshot V2 Design Goal

Snapshot v2 should be a semantic display contract, not a grid of text cells.

It should answer:
- what phase is active
- what obligation is active
- what timer is authoritative
- what gas state is active
- what warnings are active
- what actions are currently valid

It should not answer:
- where the UI should place every piece of text
- how to color every field directly
- how to reconstruct runtime state

## Proposed Snapshot V2 Shape

This is a target, not an implementation order.

```python
@dataclass(frozen=True)
class DisplaySnapshotV2:
    mode: str
    phase: str
    phase_label: str

    depth_label: str
    schedule_label: str

    active_timer: DisplayTimer | None
    secondary_timer: DisplayTimer | None

    obligation: DisplayObligation | None
    warning: DisplayWarning | None

    gas_state: DisplayGasState | None
    handoff_state: DisplayHandoffState | None

    actions: tuple[DisplayAction, ...]
```

### DisplayTimer

```python
@dataclass(frozen=True)
class DisplayTimer:
    role: TimerRole
    label: str
    value_text: str
    emphasis: str
```

Examples of `role`:
- `BOTTOM`
- `TRAVEL`
- `STOP_REMAINING`
- `TSV`
- `AIR_BREAK_REMAINING`
- `SURFACE_INTERVAL`
- `CLEAN_TIME`

### DisplayObligation

```python
@dataclass(frozen=True)
class DisplayObligation:
    kind: str
    label: str
```

Examples:
- `reach_stop`
- `leave_stop`
- `confirm_on_o2`
- `start_air_break`
- `resume_o2`
- `reach_surface`
- `reach_chamber_50`
- `move_chamber_to_40`

This should replace most of the current `summary_text` overload.

### DisplayWarning

```python
@dataclass(frozen=True)
class DisplayWarning:
    kind: str
    label: str
    severity: str
```

Examples:
- `surface_interval_penalty`
- `surface_interval_exceeded`
- `air_break_due`
- `depth_unsupported`

### DisplayGasState

```python
@dataclass(frozen=True)
class DisplayGasState:
    kind: str
    label: str
```

Examples:
- `air`
- `o2`
- `off_o2`
- `air_break`
- `waiting_on_o2`

### DisplayAction

```python
@dataclass(frozen=True)
class DisplayAction:
    operator_action: str
    label: str
    enabled: bool
    emphasis: str = "default"
```

This removes the fake “primary/secondary” meaning from the contract.

## What Snapshot V2 Should Explicitly Delete

Delete these ideas from the long-term contract:
- `primary_value_text` as a separate field from the actual timer/value
- `remaining_text` as a special one-off slot
- `detail_text` as a dumping ground for leftover meaning
- multiple parallel `*_kind` fields for per-slot styling
- slot-oriented button fields:
  - `primary_button_label`
  - `secondary_button_label`

These are renderer concerns, not engine contract concerns.

## What Must Stay Runtime-Only

The snapshot must never become a backdoor state model.

Keep these out of snapshot v2 unless they are explicitly needed for display:
- raw timer anchors
- paused elapsed values
- profile recompute internals
- delay recompute internals
- audit event lists
- handoff audit tails
- stop indexes as authoritative runtime IDs

Those belong in runtime state and tests, not display projection.

## Migration Strategy

Do this in two stages, not one.

### Stage 1: Stable Transitional Layer

- keep current `Snapshot`
- continue using the shared projector helper
- tighten semantic naming inside the runtime, not the display contract
- add tests that lock semantic state separately from snapshot text

### Stage 2: Introduce Snapshot V2 Beside Snapshot V1

- add `DisplaySnapshotV2`
- build a dual projector for redesign runtimes only
- map v2 back to legacy `Snapshot` during transition if needed
- migrate tests in layers:
  - handoff contract
  - obligation/timer semantics
  - final UI-facing text

Only after v2 is stable should v1 be retired.

## Non-Goals

Do not:
- redesign the whole UI at the same time
- invent an abstract display DSL
- create one schema that hides all mode-specific differences
- make snapshot v2 so generic that every runtime has to cram meaning back into strings

Minimal LOC matters here. The smallest correct schema is better than a clever one.

## Practical Recommendation

Do not start snapshot v2 implementation yet.

Start when:
- operator-action protocol is stable
- handoff contract is stable
- no major runtime phase changes remain for AIR/AIR-O2 or SURD

At that point, design v2 from the runtime state outward and keep a temporary
`v2 -> current Snapshot` adapter until the UI and tests are ready to move.
