# Hardening Plan

This folder is the working area for formalizing protocol rules, scenario traces,
and acceptance criteria for the live runtime.

The intent is:

1. write explicit rule documents
2. write explicit scenario documents
3. review and agree on them
4. translate them into tests and validation checks
5. only then automate broader hardening work

This keeps the runtime contract stable before we expand the test surface.

## Source Authority

The governing authority is:

1. [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)
2. [SOURCE_OF_TRUTH.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SOURCE_OF_TRUTH.md)
3. [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
4. rule docs
5. scenario docs
6. tests
7. code

Rule IDs should use actual chapter citation numbers from the manual.

## Suggested Workflow

1. Add or edit rule documents using `RULE_TEMPLATE.md`
2. Add or edit scenario documents using `SCENARIO_TEMPLATE.md`
3. Keep one file per rule or scenario once content becomes substantial
4. Review wording until the behavior is unambiguous
5. Mark each document as:
   - `Draft`
   - `Reviewed`
   - `Approved`
6. After approval, convert documents into:
   - regression tests
   - scenario acceptance tests
   - invariant tests
   - table validation tests

## Recommended File Naming

- Rules:
  - `RULE_<short_name>.md`
  - example: `RULE_first_o2_timer_anchor.md`
- Scenarios:
  - `SCENARIO_<short_name>.md`
  - example: `SCENARIO_air_o2_120_90.md`

## Scope

These documents should describe:

- protocol behavior
- user-triggered transitions
- timer anchor rules
- delay and recompute rules
- display expectations that are safety-relevant

## Current Scope Boundaries

The current live runtime intentionally assumes:

- the app is an operator-confirmed supervisory tool
- phase progression depends on explicit user input at operational milestones
- estimated depth/travel timing may be displayed, but does not autonomously
  advance the procedure

The current live runtime intentionally does not yet implement:

- surface decompression workflow
- repetitive-dive / residual-nitrogen workflow
- broader post-dive planning beyond the current clean-time behavior

These documents should not try to explain:

- code structure
- implementation details
- stylistic GUI choices unless they affect operational safety

## Review Goal

A rule or scenario is ready for implementation only when:

- a new engineer could read it and understand the required behavior
- the wording does not depend on hidden assumptions
- expected display behavior is explicit where it matters
- forbidden behavior is explicitly named
