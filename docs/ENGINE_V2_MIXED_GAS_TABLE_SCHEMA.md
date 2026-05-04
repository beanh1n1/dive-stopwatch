# Engine V2 Mixed Gas Table Schema

Status: Draft  
Parent docs:
- [ENGINE_V2_MIXED_GAS_PARITY.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_V2_MIXED_GAS_PARITY.md)
- [ENGINE_V2_MIXED_GAS_BUILD_CHECKLIST.md](/Users/iananderson/projects/DiveStopwatchProject/docs/ENGINE_V2_MIXED_GAS_BUILD_CHECKLIST.md)
- [MIXED_GAS_BUILD_PROMPT.md](/Users/iananderson/projects/DiveStopwatchProject/docs/MIXED_GAS_BUILD_PROMPT.md)
- [Caisson_engine_V2_Mixed_Gas_notes.txt](/Users/iananderson/projects/DiveStopwatchProject/docs/Caisson_engine_V2_Mixed_Gas_notes.txt)

## Purpose

Define the target structured format for ingesting mixed-gas Table `12-4` data
into `engine_v2`.

This document is schema guidance only. It does not attempt to fully transcribe
the PDF. The goal is to give future extraction/import work a clear target so
the data lands in a parity-safe shape the runtime can consume without hidden
manual interpretation.

## Scope

In scope:

- normal Table `12-4` schedule data for mixed-gas dives
- depth and bottom-time keyed schedule lookup
- allowable bottom-mix O2 range per schedule row
- decompression stop schedule data needed to build `MixedGasPlan`
- source-traceability fields for review and verification

Out of scope:

- emergency or abort procedures
- delay-rule logic
- `<16% O2` descent grace-window logic
- gas-shift confirmation timing at `20`, `90`, and `30 fsw`
- O2 air-break semantics
- chamber runtime data beyond what is explicitly present in the mixed-gas table

Those rules belong in runtime code and rule docs, not in the imported table
payload.

## Design Rules

1. Keep table facts separate from runtime rules.
2. Match the existing AIR/AIR_O2 CSV shape where practical.
3. Preserve exact source traceability for every imported schedule.
4. Normalize units to machine-friendly integers.
5. Treat derived runtime semantics as derived, not imported truth.

## Recommended Artifacts

Use a two-stage import target:

1. a human-reviewable CSV for extraction and verification
2. a canonical JSON artifact for runtime loading

Recommended files:

- `mixed_gas_table_12_4_schedules.csv`
- `mixed_gas_table_12_4.json`

Optional but useful:

- `mixed_gas_table_12_4_validation.json`

The CSV is for capture and audit. The JSON is the canonical runtime-facing
representation.

## Recommended CSV Schema

### `mixed_gas_table_12_4_schedules.csv`

One row per unique table schedule.

Recommended columns:

- `depth_fsw`
- `bottom_time_min`
- `gas_mix`
- `time_to_first_stop`
- `stop_190`
- `stop_180`
- `stop_170`
- `stop_160`
- `stop_150`
- `stop_140`
- `stop_130`
- `stop_120`
- `stop_110`
- `stop_100`
- `stop_90`
- `stop_80`
- `stop_70`
- `stop_60`
- `stop_50`
- `stop_40`
- `stop_30`
- `stop_20`
- `total_ascent_time`
- `chamber_o2_periods`
- `section`
- `source_page`
- `notes`

Field notes:

- `depth_fsw`: integer feet of seawater
- `bottom_time_min`: integer bottom time in minutes
  Use the common table lattice of `10, 20, 30, 40, 60, 80, 100, 120` except
  where the manual provides explicit depth-specific rows. The current verified
  exceptions are `80/25` and `100/15`.
- `gas_mix`: decimal O2 value or decimal O2 range such as `18.4-20.1`
- `time_to_first_stop`: `MM:SS`; blank for no-decompression rows
  Keep for source traceability only. Active `engine_v2` mixed-gas runtime does
  not derive travel-to-first-stop from the table.
- `stop_190` through `stop_20`: stop minutes at each listed depth; blank means no stop
- `total_ascent_time`: `MM:SS` when available from the source table
- `chamber_o2_periods`: blank until surface-decompression ingestion is in scope
- `section`: recommended enum `no_decompression` or `decompression`
- `source_page`: integer page reference from the source document
- `notes`: reviewer notes only, never required for runtime

## Canonical JSON Schema

The JSON artifact should be the importer output after CSV normalization and
validation, not the first hand-entry format.

Recommended top-level shape:

```json
{
  "table_id": "12-4",
  "table_name": "Surface-Supplied Helium-Oxygen Decompression Table",
  "source_document": "Mixed Gas Diving Operations",
  "source_revision": "REV7 Change A 6.6.18",
  "schema_version": 1,
  "schedules": []
}
```

Recommended schedule object:

```json
{
  "depth_fsw": 90,
  "bottom_time_min": 30,
  "bottom_mix_o2_percent_range": {
    "min": 16.0,
    "max": 18.4
  },
  "schedule_kind": "decompression",
  "stops": [
    {
      "sequence": 1,
      "depth_fsw": 40,
      "stop_time_min": 3
    },
    {
      "sequence": 2,
      "depth_fsw": 30,
      "stop_time_min": 12
    },
    {
      "sequence": 3,
      "depth_fsw": 20,
      "stop_time_min": 25
    }
  ],
  "source": {
    "table": "12-4",
    "page": 123,
    "row_label": "example only"
  }
}
```

The example above is illustrative only. It shows shape, not verified table
content.

`bottom_mix_o2_percent_range.min` and `.max` should be stored as decimals, not
integers. The mixed-gas table uses fractional O2 bounds.

## Normalization Rules

### Units

- store depth as integer `fsw`
- store bottom time and stop time as integer minutes
- store bottom-mix O2 bounds as decimals
- store `time_to_first_stop` and `total_ascent_time` in `MM:SS`
- do not store percentages with `%` signs

### Null and blank handling

- blanks in CSV become `null` during normalization
- use `null` only where a field is genuinely absent
- never preserve placeholder strings like `-`, `--`, `N/A`, or `none`

### Stop ordering

- stops must be sorted deepest to shallowest
- `stop_sequence` must match the sorted order
- omit zero-minute stops entirely from canonical JSON

### Schedule kind

- if `stop_count == 0`, normalize to `schedule_kind = "no_decompression"`
- if `stop_count > 0`, normalize to `schedule_kind = "decompression"`
- do not encode separate schedule kinds for `<16% O2` descent or delay branches

### Source traceability

- every schedule must retain source page information
- do not discard source labels just because the runtime does not use them
- `time_to_first_stop` may be preserved for audit/reference even when runtime
  behavior intentionally ignores it

## What Should Not Be Stored in Table Data

These belong in rules/runtime code, not the imported dataset:

- `20 second` ventilation steps
- `5 minute` `<16% O2` descent grace-window logic
- `90 fsw` `50/50` confirmation procedure
- `30 fsw` O2 confirmation anchor
- O2 air-break thresholds and suppression logic
- delay recomputation rules
- operator action names
- presentation labels
- travel-to-first-stop runtime timing

If a future importer needs those values, it should read them from rules code or
manual-backed constants, not from the table file.

## Recommended Derived Fields

These may be derived by the importer or plan loader, but should not be hand-keyed
into the raw extraction CSV unless there is a review reason to do so:

- `first_stop_depth_fsw`
- `has_decompression_stops`
- `stop_count`
- `schedule_kind`

These are safe derivatives of the stop rows and reduce duplication risk.

## Validation Checks

Validation should run in two tiers: hard failures and review warnings.

### Hard failures

- `depth_fsw` is a positive integer
- `bottom_time_min` is a positive integer
- `gas_mix` parses into one decimal or one decimal range
- bottom-mix O2 range stays within the manual-backed family bounds of `10` to
  `40` percent
- non-blank stop values are positive integers
- `section = "no_decompression"` implies no non-blank stop columns
- `section = "decompression"` implies at least one stop column

### Review warnings

- schedule depth or stop depths fall outside the expected mixed-gas stop band
  used by the chapter and should be manually rechecked
- stop depths are not in `10 fsw` increments
- a decompression schedule has no `40 fsw` stop and therefore deserves manual
  review before any surface-decompression eligibility assumptions are made
- source traceability fields are missing
- duplicate schedules appear with different source pages or notes

Warnings should not silently auto-correct source data.

## Recommended Import Behavior

1. Read `mixed_gas_table_12_4_schedules.csv`.
2. Normalize blank values and units.
3. Expand non-blank `stop_*` columns into an ordered stop list.
4. Validate hard invariants.
5. Emit warnings for suspicious but not impossible rows.
6. Write canonical `mixed_gas_table_12_4.json`.

Do not allow the runtime to consume partially validated mixed-gas table data.

## Engine V2 Consumption Expectations

The eventual `plan.py` loader should be able to rely on this data shape:

- lookup by `(depth_fsw, bottom_time_min)`
- inspect allowed bottom-mix O2 range for the selected row
- retrieve an ordered stop list
- keep source metadata available for debugging and audit

The loader should not need to reconstruct schedule rows from wide columns or
guess whether a blank cell means "no stop" or "bad extraction."

## Deferred Questions

These should be decided when the importer is implemented, not during raw table
capture:

- final repository home for the canonical JSON artifact
- whether source-page numbering should use PDF page count or printed manual page
- whether any mixed-gas surface-decompression schedule data from the chapter
  should live in the same JSON file or a separate artifact
- whether a generated validation report should be checked into the repo

## Recommendation

For eventual agent-based extraction, target:

- one agent producing raw schedule rows
- one agent verifying the extracted rows against the source pages
- one writer/import step normalizing into the JSON format above

That split keeps source reading, accuracy checking, and write-side normalization
separate without forcing runtime code to consume spreadsheet-shaped data.
