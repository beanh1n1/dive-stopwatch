# Rule Traceability Matrix

Status: Draft

This matrix maps the current app contract to the AIR Decompression chapter using
manual citation numbers as rule IDs.

## Columns

- `Rule ID`: chapter citation from the manual
- `Topic`: short rule label
- `Manual authority`: chapter section or cited page reference
- `Current app status`: implemented / partial / out of scope
- `Primary doc`: current repo rule doc
- `Related tests`: main test coverage anchor
- `Related code`: main implementation anchor
- `Notes`: clarification or follow-up

| Rule ID | Topic | Manual authority | Current app status | Primary doc | Related tests | Related code | Notes |
|---|---|---|---|---|---|---|---|
| `9-6.4` | Stop timing semantics | Chapter 9, p.8 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md) | `tests/test_minimal_engine.py` later-stop timing coverage | `src/dive_stopwatch/minimal/engine.py` | Later stop time includes travel from previous stop; first O2 stop is the exception |
| `9-6.5` | Last water stop is `20 fsw` | Chapter 9, p.8 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md) | `tests/test_minimal_engine.py` final stop coverage | `src/dive_stopwatch/minimal/profiles.py` | Applies to current in-water runtime |
| `9-8.1` | In-water decompression on air | Chapter 9, p.11 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md) | `tests/test_tables.py` and AIR scenarios | `src/dive_stopwatch/minimal/profiles.py` | Table lookup and AIR row interpretation |
| `9-8.2` | In-water decompression on air and oxygen | Chapter 9, p.11 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md) | `tests/test_tables.py`, AIR/O2 scenarios | `src/dive_stopwatch/minimal/profiles.py` | AIR/O2 mode selection and stop structure |
| `9-8.2.1` | Shift to 100% oxygen / TSV | Chapter 9, p.13 | Implemented with app-specific display semantics | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md), [RULE_display_and_timer_semantics.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_display_and_timer_semantics.md) | `tests/test_minimal_engine.py` first O2 / TSV tests | `src/dive_stopwatch/minimal/engine.py`, `src/dive_stopwatch/minimal/snapshot.py` | Explicitly: `L40 -> On O2 @ 30`, or if first stop is O2, `R30/R20 -> On O2` |
| `9-8.2.2` | Air breaks at `30` and `20 fsw` | Chapter 9, p.13 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md), [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md) | `tests/test_minimal_engine.py` air-break coverage | `src/dive_stopwatch/minimal/engine.py`, `src/dive_stopwatch/minimal/snapshot.py` | Continuous O2 timing begins when all divers are confirmed on oxygen |
| `9-8.2.2-35MIN` | `<= 35 min` air-break exception | Chapter 9, p.13 | Implemented | [RULE_core_definitions.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_core_definitions.md), [SCENARIO_terminal_20fsw_air_break.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_terminal_20fsw_air_break.md), [SCENARIO_30fsw_air_break.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_30fsw_air_break.md) | `tests/test_minimal_engine.py` final 20 stop exception, short total-O2 chain exception | `src/dive_stopwatch/minimal/engine.py` | Applies when total continuous O2 remaining to surface or the final O2 period is `<= 35 min` |
| `9-11.3` | Delay arriving at first decompression stop | Chapter 9, pp.31-32 | Partially Implemented | [RULE_delay_corrections.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_delay_corrections.md), [SCENARIO_delay_boundaries.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_delay_boundaries.md) | `tests/test_minimal_engine.py` first-stop delay tests | `src/dive_stopwatch/minimal/profiles.py`, `src/dive_stopwatch/minimal/engine.py` | Exact `<= 1 min`, deep recompute, and shallow first-stop extension are covered |
| `9-11.4` | Delay leaving a stop or between stops | Chapter 9, pp.32-35 | Partially Implemented | [RULE_delay_corrections.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_delay_corrections.md), [SCENARIO_delay_boundaries.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_delay_boundaries.md) | `tests/test_minimal_engine.py` and `tests/test_minimal_profiles.py` delay tests | `src/dive_stopwatch/minimal/profiles.py`, `src/dive_stopwatch/minimal/engine.py` | Deep recompute, exact-60s ignore, shallow later-stop auditability, and explicit `30 -> 20` O2 delay credit are covered; the distinct `20 fsw` departure-delay branch is still not separately modeled |
| `9-8.1-NOD` | No-decompression boundary crossover | AIR table behavior / table pages | Implemented with app-specific bottom-display interpretation | [SCENARIO_no_d_boundary_crossover.md](/Users/iananderson/projects/DiveStopwatchProject/docs/SCENARIO_no_d_boundary_crossover.md) | `tests/test_tables.py`, `tests/test_minimal_engine.py` no-D countdown tests | `src/dive_stopwatch/minimal/profiles.py`, `src/dive_stopwatch/minimal/snapshot.py` | Bottom display counts down to no-D limit, then changes `Next:` to the first deco stop |
| `APP-CLEAN-TIME` | Clean time and AGE monitoring prompt | App-specific, no direct manual authority | Implemented | [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md) | `tests/test_minimal_engine.py` clean-time tests | `src/dive_stopwatch/minimal/snapshot.py` | Explicitly app-specific; not manual-derived |
| `APP-DELAY-LOG` | Delay outcome logging and retained recompute state | App-specific auditability feature | Implemented | [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md), [RULE_delay_corrections.md](/Users/iananderson/projects/DiveStopwatchProject/docs/RULE_delay_corrections.md) | `tests/test_minimal_engine.py` delay log tests | `src/dive_stopwatch/minimal/engine.py` | Supports recall/event-log auditability even when no schedule change occurs |
| `9-8.3` | Surface decompression using oxygen | Chapter 9, Table 9-9 context | Out of Scope | [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md) | none | none | Manual authority retained; current runtime does not implement SurD workflow |
| `9-12.10` | Omitted decompression stop handling | Chapter 9, later recovery sections | Out of Scope | [MANUAL_APP_MISMATCH_AUDIT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MANUAL_APP_MISMATCH_AUDIT.md) | none | none | Recovery / emergency procedures intentionally not yet modeled |

## Maintenance Rules

- Add a new row before adding a new protocol rule doc.
- If a test changes expected behavior, update the matrix row and cite the manual basis.
- If a behavior is app-specific rather than manual-derived, note that clearly in `Notes`.
