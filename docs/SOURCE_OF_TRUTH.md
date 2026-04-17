# Source of Truth

Status: Active

## Authority Order

The governing authority for AIR decompression behavior in this repo is:

1. [US DIVING MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf](/Users/iananderson/projects/DiveStopwatchProject/docs/US%20DIVING%20MANUAL_REV7_ChangeA-6.6.18_AIR_Decompression_Operations.pdf)
2. Rule documents in `docs/` that explicitly cite the manual chapter
3. Scenario documents in `docs/`
4. Automated tests
5. Code

If any lower layer conflicts with a higher layer, the higher layer wins.

## Contract

This means:

- docs do not invent protocol rules
- tests do not define protocol rules
- code does not imply protocol rules
- every protocol rule must trace back to the AIR Decompression chapter

## Rule IDs

Rule IDs must use the manual’s actual chapter citation numbers.

Examples:

- `9-6.4` stop timing
- `9-6.5` last water stop
- `9-8.1` in-water decompression on air
- `9-8.2` in-water decompression on air and oxygen
- `9-8.2.1` shifting to 100% oxygen / TSV semantics
- `9-8.2.2` air breaks at `30` and `20 fsw`

Recommended format:

- `9-8.2.2`
- `9-8.2.2-AIR-BREAKS`

The chapter citation must remain the leading identifier.

## Required Structure For Future Rule Docs

Every rule doc should include:

- `Rule ID`
- `Authority`
- `Manual citation`
- `Manual rule statement`
- `App interpretation`
- `Scope status`
  - `Implemented`
  - `Partially Implemented`
  - `Out of Scope`
- `Related tests`
- `Related code paths`

## Scope Labels

To keep the source-truth layer honest, every rule must be marked as one of:

- `Implemented`
- `Implemented with app-specific operator-confirmed workflow`
- `Partially Implemented`
- `Out of Scope`

Out-of-scope manual content is still authoritative. It is simply not yet implemented.

## Agent Workflow

Before any new hardening pass, agents should:

1. read the relevant section of the manual chapter
2. extract explicit rule statements
3. compare those statements against existing rule docs
4. compare rule docs against tests and code
5. only then propose changes

Agents should not start by inferring rules from current tests or UI behavior.

## Reference Docs

- [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md)
- [RULE_TRACEABILITY_MATRIX.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_TRACEABILITY_MATRIX.md)
- [HARDENING_PLAN.md](/Users/iananderson/projects/DiveStopwatchProject/docs/HARDENING_PLAN.md)
