Archived legacy runtime and UI stack.

Contents:
- `src/dive_stopwatch/legacy/`
  - preserved pre-`engine_v2` runtime and mobile UI package
- `tests/`
  - legacy runtime acceptance tests that are no longer part of the active suite

These files were archived after the active runtime stopped depending on them directly.
The only surviving AIR/AIR_O2 table/profile dependency was migrated into:
- `src/dive_stopwatch/engine_v2/domain/air_o2_profiles.py`
