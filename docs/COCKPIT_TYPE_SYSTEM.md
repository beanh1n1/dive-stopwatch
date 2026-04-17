# Cockpit Type System

## Purpose
Define a repeatable typography language for the mobile UI that feels closer to a US military aircraft cockpit or instrument panel than a generic app UI.

This is not a full custom font file yet. It is a design system that combines:
- a local system font base
- sizing rules
- weight rules
- tracking rules
- case rules
- semantic usage rules

## Design Intent
The UI should feel:
- mechanical
- precise
- disciplined
- instrument-driven
- operational rather than decorative

It should not feel:
- soft
- playful
- futuristic for its own sake
- overly stylized
- sci-fi neon

## Base Typeface
Current prototype base:
- `Menlo`

Why:
- more mechanical than `SFNSMono`
- less retro/stylized than `Monaco`
- available locally on macOS
- stable in Flet without bundling a download

## Role Categories

### 1. Command Labels
Examples:
- `Mode`
- `Status:`
- `Test Time`
- `Controls`
- `Event Log`

Rules:
- uppercase or title case only when operationally familiar
- medium-small size
- high weight
- slightly increased tracking when possible
- low ornamentation

Intent:
- these should read like engraved panel labels

### 2. Primary Readouts
Examples:
- main timer
- status value
- recall timer

Rules:
- largest sizes in the system
- strong weight
- minimal styling
- tight vertical rhythm
- no decorative color outside semantic rules

Intent:
- these are the instrument face

### 3. Data Rows
Examples:
- depth row
- `fsw`
- `remaining`
- `Next:`
- stop durations

Rules:
- medium size
- high clarity
- monospace alignment feel
- units stay visually attached to values

Intent:
- these should feel like cockpit data tape / panel readout text

### 4. Console Text
Examples:
- recall log
- test-time display

Rules:
- monospace
- compact leading
- slightly smaller than data rows
- optimized for block reading and copy/paste

Intent:
- these should feel like a mission log or maintenance console

## Case Rules
- operational labels may use title case if already embedded in the product language
- dynamic values should not be forced into all-caps if it reduces readability
- short utility labels can be caps-like through weight and spacing rather than literal uppercase

## Tracking Rules
When supported, use:
- slight positive tracking for labels and headers
- neutral tracking for timers
- slight positive tracking for compact panel chips

Approximate guidance:
- labels: `+0.5` to `+1.5`
- timers: `0`
- panel chips: `+0.5`

## Weight Rules
- labels: `W_700` to `W_800`
- values: `W_700` to `BOLD`
- large timers: `BOLD`
- console/log text: `W_500` to `W_600`

## Color Rules
Typography color must remain subordinate to the app's hard-coded semantic color rules.

Allowed default typography colors:
- white
- muted grey
- metallic off-white

Reserved semantic colors:
- green only for O2 or explicit AIR/O2 mode accent
- red only for air-break / warning semantics

## Spacing Rules
- readouts should feel tight and panel-like, not airy
- avoid large vertical gaps between status, timer, depth, and next-action rows
- console/log blocks may use slightly looser line height for legibility

## Current Prototype Direction
The current mobile GUI should use this progression:

1. `Menlo` as the base cockpit family
2. strong weight for operational labels and timers
3. neutral monochrome palette by default
4. semantic green only for:
   - O2 states
   - AIR/O2 mode tile accent
5. semantic red only for:
   - air-break states

## Future Exactness Path
To get closer to a true cockpit-specific look, the next escalation should be:

1. collect 3-5 reference screenshots of real US military cockpit displays / panels
2. identify the recurring glyph features:
   - zero shape
   - one shape
   - seven shape
   - curve tightness
   - stroke uniformity
   - spacing rhythm
3. define a custom glyph set for:
   - `0-9`
   - `A-Z`
   - `/`, `:`, `+`, `-`, `|`
4. either:
   - build a true custom font file
   - or build an SVG/asset-backed numeric display set for the primary readouts

## Acceptance Criteria
The type system is working when:
- the UI feels more like instrumentation than software chrome
- labels feel deliberate and utilitarian
- timers and depth rows feel like readouts
- recall/log text feels console-like
- semantic colors remain meaningful and do not become decorative
