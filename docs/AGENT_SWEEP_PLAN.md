# Agent Sweep Plan

Status: Draft

## Purpose

Define the next broad, aggressive hardening sweep so agents start from the manual
authority chain instead of from inferred local behavior.

## Preconditions

Before this sweep:

- [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md) is accepted as the authority contract
- [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md) is the current mapping surface
- [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md) is the current discrepancy ledger

## Sweep Order

### Wave 1: Manual extraction audit

Goal:
- extract explicit rule statements from the AIR Decompression chapter
- identify any remaining doc gaps or citation gaps

Output:
- proposed additions or corrections to rule docs
- citation corrections for partially mapped rules

### Wave 2: Traceability audit

Goal:
- verify every implemented rule has:
  - manual citation
  - rule doc
  - scenario or acceptance coverage
  - test anchor
  - code anchor

Output:
- updates to [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
- list of missing test/doc/code links

### Wave 3: Scenario expansion

Goal:
- convert chapter-backed scenarios into stronger acceptance-style test coverage

Primary targets:
- AIR/O2 worked example flow
- delay boundary flows
- continuous O2 / air-break flows
- first O2 stop directly from bottom
- no-D boundary crossover

Output:
- proposed acceptance tests
- identified gaps in current scenario docs

### Wave 4: Invariant and property sweep

Goal:
- verify engine behavior across broad runtime transitions

Primary targets:
- `Next:` must not contradict the nearer required action
- O2 timing continuity
- air-break timing and exception behavior
- stop-anchor monotonicity
- delay logging / retained recompute metadata
- no impossible phase/status combinations

Output:
- invariant tests
- known-risk engine mismatches

### Wave 5: Table / chapter parity extension

Goal:
- continue broad parity between CSVs, chapter examples, and runtime behavior

Primary targets:
- remaining manual example rows
- AIR vs AIR/O2 example parity
- edge rows likely to hide transcription errors

Output:
- table parity tests
- source-data correction candidates

## Agent Roles

Recommended roles:

- `manual-audit`
  - reads the chapter and extracts explicit rules
- `traceability-audit`
  - checks docs/tests/code against the matrix
- `scenario-audit`
  - expands or tightens scenario coverage
- `engine-invariant-audit`
  - targets runtime/property mismatches
- `table-parity-audit`
  - targets CSV/manual/runtime alignment

## Guardrails

- agents must start from the manual chapter, not from tests
- agents must cite section numbers or page references
- agents must distinguish:
  - implemented
  - partially implemented
  - out of scope
- agents must not treat current UI behavior as authoritative without a manual or
  app-contract basis

## Merge Discipline

For each agent wave:

1. review findings first
2. agree on contract changes
3. implement tests or code in bounded batches
4. rerun full suite
5. update traceability docs

This keeps the broad sweep aggressive in coverage but disciplined in change
control.
