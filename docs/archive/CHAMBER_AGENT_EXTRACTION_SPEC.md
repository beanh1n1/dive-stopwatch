# Chamber Agent Extraction Spec

## Purpose

This document constrains the second-pass agent extraction for Chamber mode.

The goal is not to summarize Chapter 17 generally. The goal is to extract only the
supervisor-facing operational facts needed to build a straight-stick Chamber mode
for `engine_v2`.

Primary source:

- [Chamber_Treatment_US DIVING MANUAL_REV7_ChangeA-6.6.18.pdf  2.pdf](</Users/iananderson/projects/DiveStopwatchProject/docs/Chamber_Treatment_US DIVING MANUAL_REV7_ChangeA-6.6.18.pdf  2.pdf>)

## Fixed Assumptions

These assumptions are mandatory for this extraction pass:

- all chamber operations are at sea level
- no prior hyperbaric exposure for chamber occupants
- no protocol modification path
- no UMO-driven treatment changes
- no altitude adjustments
- no non-diving HBO indications
- no diagnosis engine
- no patient-care modeling except where it changes stopwatch/table execution

This is a straight-stick chamber execution model only.

## Chamber Scope

Chamber mode should be treated as a supervisor-operated treatment-table execution
engine.

It is responsible for:

- selecting the straight-stick path based on explicit supervisor-confirmed branch inputs
- executing the selected table
- tracking depth, gas period, timer segment, and table progression
- handling standard straight-stick interruptions and resumptions
- producing supervisor-facing execution state and audit events

It is not responsible for:

- diagnosing DCS or AGE
- interpreting medical rationale
- supporting custom protocol modifications
- supporting physician/UMO overrides
- modeling general patient treatment or transport guidance

## Figures That Drive The Model

These figures are the primary control-flow source for the Chamber mode entry and
progression model:

- Figure 17-1: Treatment of Arterial Gas Embolism or Serious Decompression Sickness
- Figure 17-2: Treatment of Type I Decompression Sickness

These figures should be treated as the primary source for:

- branch checkpoints
- supervisor confirmations
- table selection predicates
- standard escalation from `TT6 -> TT6A -> TT4 -> TT7`
- standard `TT5` vs `TT6` selection for Type I

## In-Scope Tables

Extract only straight-stick operational facts for:

- `TT5`
- `TT6`
- `TT6A`
- `TT4`
- `TT7`

Do not spend extraction effort on:

- `TT8`
- `TT9`
- Air treatment tables
- non-diving HBO tables

These can be revisited later if needed.

## Desired Runtime Model Shape

Agents should extract facts that support this endstate:

- a Chamber mode with a unified entry path
- initial compression to `60 fsw`
- supervisor-facing branch checkpoints only when the flowchart requires a decision
- a selected table runtime after that decision
- explicit current depth
- explicit current segment
- explicit active timer
- explicit gas state
- explicit pending supervisor confirmation, when applicable

The extraction should support a model like:

- unified entry:
  - `DESCEND_TO_60`
  - `AT_60_INITIAL_ASSESSMENT`
- branch checkpoints:
  - `AT_60_WAITING_FIRST_DECISION`
  - `AT_DEPTH_OF_RELIEF_WAITING_MORE_TIME_DECISION`
  - `AT_60_WAITING_TT7_DECISION`
- table execution:
  - `RUNNING_TT5`
  - `RUNNING_TT6`
  - `RUNNING_TT6A`
  - `RUNNING_TT4`
  - `RUNNING_TT7`
- table segment kinds:
  - descent
  - hold
  - oxygen period
  - air break
  - ascent to next stop
  - completed

Agents should not invent these names, but should extract facts that support or
refute this shape.

## Supervisor-Confirmed Inputs To Extract

Agents should identify the minimum set of explicit operator inputs needed to run
the straight-stick chamber flow.

Candidate examples:

- complete relief within first 10 minutes at 60 fsw
- whether initial symptoms remain unchanged or worsen at 60 fsw
- whether compression should continue to depth of relief or significant improvement
- depth of relief or significant improvement
- whether more time is needed at depth of relief
- whether life-threatening symptoms require more time at 60 fsw
- whether a standard extension is being used
- whether oxygen was interrupted
- whether oxygen service was restored within the allowed window

For each input, agents should identify:

- exact decision point
- allowed values
- downstream branch effect
- whether the input is mandatory or conditional

## Table Execution Facts To Extract

For each in-scope table, agents should extract:

- entry condition
- initial depth
- descent rate
- ascent rate
- stop depths
- stop order
- oxygen periods
- air-break periods
- treatment-gas periods
- whether compression time is included in segment time
- whether ascent travel counts toward the next interval
- standard extension options
- standard completion condition

If a table has a special rule that materially changes execution, extract it.
If a rule is just medical rationale, ignore it.

## Standard Interruption Facts To Extract

Extract only standard straight-stick interruptions that affect execution timing or
table state:

- CNS oxygen toxicity handling
- oxygen interruption / oxygen loss
- standard resume rules
- standard switch-to-air fallback only if it is fully procedural and not treated as a
  custom modification path

Do not extract:

- bespoke medical modifications
- judgment-based therapeutic changes

## Tender Obligation Scope

Tender timing should be treated as a parallel derived obligation, not as the primary
patient table state machine.

The extraction goal is to support a divided UI card:

- primary card: patient table execution
- secondary card: tender obligations

For this pass, agents should extract only standard tender obligations under the
fixed assumptions:

- sea level
- no prior tender exposure

For each in-scope table, identify:

- whether tender O2 obligations exist
- at what depth those obligations are performed
- whether tender obligations depend on table extensions
- whether tender obligations can exceed the nominal patient stay at that stop
- any standard post-treatment tender restrictions that should be displayed

Agents should explicitly distinguish:

- patient runtime truth
- tender derived obligations

## Explicitly Out Of Scope

Agents must exclude:

- diagnosis prose
- symptom descriptions except when they define a branch predicate
- medical rationale
- drug administration
- airway management
- ACLS details
- transport and evacuation guidance
- non-diving HBO treatment guidance
- altitude corrections
- chamber environmental engineering details, unless they directly gate stopwatch
  execution
- UMO modification authority
- custom or nonstandard treatment paths

## Required Agent Deliverable Format

Each agent should return findings in this structure:

### 1. Runtime Facts

- fact
- source section / figure
- why it changes runtime state

### 2. Supervisor Inputs

- input
- decision point
- allowed values
- downstream branch

### 3. Table Segment Facts

- table
- depth/time/gas segment
- special timing rule if any

### 4. Tender Obligations

- table
- obligation
- timing/depth
- dependency on extension or branch

### 5. Out-Of-Scope Findings

- content type
- reason it must stay out of the runtime model

### 6. Open Ambiguities

- ambiguity
- exact source location
- why it blocks confident modeling

## Agent Task Split

Use three agents with non-overlapping goals:

### Agent 1: Branch And Table Selection

Extract only:

- Figure 17-1 branch predicates
- Figure 17-2 branch predicates
- the unified path to `60 fsw`
- the first supervisor decision point at `60 fsw`
- table selection rules for `TT5`, `TT6`, `TT6A`, `TT4`, `TT7`
- supervisor-confirmed branch inputs

Do not extract detailed segment timing except where required to understand a branch.

### Agent 2: Table Execution Mechanics

Extract only:

- straight-stick execution details for `TT5`, `TT6`, `TT6A`, `TT4`, `TT7`
- segment timing
- depth sequence
- gas periods
- extensions
- standard interruption/resume mechanics

Do not extract diagnosis or medical rationale.

### Agent 3: Tender Obligations And Exclusions

Extract only:

- standard tender O2 obligations for sea-level, no-prior-exposure conditions
- any standard post-treatment tender restrictions
- a clear exclusion list of medical material that should not enter the model

Do not redesign the chamber runtime.

## Acceptance Standard

The extraction pass is successful if it gives us enough information to define:

- Chamber entry checkpoints
- Chamber branch states
- straight-stick table execution states
- patient timers
- gas periods
- tender derived card content

without importing diagnosis logic or custom medical treatment logic into the
engine.
