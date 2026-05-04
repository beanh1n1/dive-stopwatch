# Engine V2 Method Reference

This document explains what each `engine_v2` method/helper does and when it is called.

Scope:
- runtime/session orchestration
- mode engines
- reducers/transitions
- query/view builders
- projection/presentation helpers
- shared timer/depth helpers

Notes:
- Data-only enums/dataclasses are listed briefly for context, but this document focuses on functions and methods.
- "When called" describes the normal call path, not every possible test invocation.

## Call Flow

Typical UI/runtime path:

1. `EngineV2Session.dispatch(action_name)`
2. `EngineCoordinator.dispatch(action)` or mode engine `dispatch(action)`
3. mode `reduce_action(state, action, now)`
4. transition helper for that action
5. `derive_view(state, now)`
6. `build_presentation_model(view, ...)`
7. GUI renders `PresentationModel`

## Shared Contracts

### `src/dive_stopwatch/engine_v2/contracts/actions.py`

- `EngineAction`
  - Purpose: canonical action vocabulary across AIR, SURD, and CHAMBER.
  - When used: decoded in `EngineV2Session.dispatch()`, routed in reducers, referenced in queries for `available_actions`.

### `src/dive_stopwatch/engine_v2/contracts/events.py`

- `AuditEventKind`
  - Purpose: canonical runtime/audit event vocabulary.
  - When used: emitted by transitions, coordinator, and session runtime logging.

- `AuditEvent`
  - Purpose: immutable runtime log row with `kind`, timestamp, and payload.
  - When used: accumulated in session and rendered into recall/event log.

### `src/dive_stopwatch/engine_v2/contracts/surd_handoff.py`

- `SurdEntryKind`
  - Purpose: identifies the kind of AIR->SURD entry.
  - When used: set in handoff builders and interpreted by SURD/coordinator.

- `AirToSurdHandoff`
  - Purpose: immutable AIR->SURD handoff payload.
  - When used: built by AIR handoff builders and consumed by SURD/coordinator.

### `src/dive_stopwatch/engine_v2/contracts/timers.py`

- `TimerState`
  - Purpose: shared timer primitive.
  - When used: wrapped inside mode-specific timers.

- `elapsed(timer, now)`
  - Purpose: compute total elapsed time for a timer.
  - When called: anywhere a mode/query/presentation needs elapsed time.

- `pause(timer, now)`
  - Purpose: freeze accumulation while preserving carried elapsed time.
  - When called: interruption-style semantics where a timer must stop advancing.

- `resume(timer, now)`
  - Purpose: restart accumulation from a paused timer.
  - When called: resuming previously paused timers.

- `shift(timer, seconds=...)`
  - Purpose: move the timer anchor without changing carried elapsed time.
  - When called: currently used in AIR delay recompute handling.

- `remaining(timer, now, target_sec=...)`
  - Purpose: compute remaining time against a target duration.
  - When called: generic timer countdown computations.

### `src/dive_stopwatch/engine_v2/contracts/view.py`

- `EngineMode`
  - Purpose: top-level active mode identity.

- `TimerRole`
  - Purpose: presentation/runtime timer category.

- `ObligationKind`
  - Purpose: current required operator action.

- `WarningKind`
  - Purpose: warning flags surfaced into view/presentation.

- `TimerView`
  - Purpose: normalized timer payload for `EngineView`.

- `EngineView`
  - Purpose: mode-neutral semantic view consumed by presentation layers.
  - When used: returned by each mode/coordinator `view()` method and transformed into GUI-facing models.

## Shared Domain Helpers

### `src/dive_stopwatch/engine_v2/domain/depth.py`

- `linear_depth_fsw(start_depth_fsw, end_depth_fsw, elapsed_sec, rate_fsw_per_sec)`
  - Purpose: interpolate live depth along a linear ascent/descent/travel leg.
  - When called: AIR/SURD/CHAMBER query layers when a depth should move continuously.

- `depth_label(depth_fsw)`
  - Purpose: normalize depth display text.
  - When called: presentation builder for line-3 depth text.

## Runtime Layer

### `src/dive_stopwatch/engine_v2/runtime/coordinator.py`

- `CoordinatorState`
  - Purpose: container for active AIR and SURD runtime state.

- `EngineCoordinator.__init__(mode, now_provider)`
  - Purpose: initialize the active AIR/AIR_O2/SURD runtime shell.
  - When called: session launch for non-CHAMBER modes.

- `EngineCoordinator.set_depth(raw_text, depth_fsw)`
  - Purpose: forward max-depth input into AIR.
  - When called: session input updates for AIR/AIR_O2.

- `EngineCoordinator.dispatch(action)`
  - Purpose: top-level dispatcher for AIR/AIR_O2/SURD plus coordinator-owned handoffs.
  - When called: session action dispatch.

- `EngineCoordinator.activate_surd_handoff(handoff)`
  - Purpose: explicitly activate SURD from a prepared handoff.
  - When called: coordinator handoff flows.

- `EngineCoordinator.view()`
  - Purpose: return the active semantic `EngineView`.
  - When called: session/presentation on every render.

- `EngineCoordinator.state()`
  - Purpose: expose the active underlying mode state for debugging/tests.
  - When called: tests and some internal parity checks.

- `EngineCoordinator._switch_to_surd()`
  - Purpose: build AIR->SURD handoff at the alternate switch seam.
  - When called: internally from `dispatch()` on `SWITCH_TO_SURD`.

- `EngineCoordinator._start_normal_surd_handoff()`
  - Purpose: build AIR->SURD handoff for normal L40 path.
  - When called: internally from `dispatch()` on normal SURD start path.

### `src/dive_stopwatch/engine_v2/runtime/session.py`

- `EngineV2Session.__init__(now_provider, initial_mode)`
  - Purpose: top-level GUI/session runtime wrapper.
  - When called: GUI startup or tests.

- `EngineV2Session.mode`
  - Purpose: current active mode property.
  - When called: GUI mode cycling/render logic.

- `EngineV2Session.launch_mode(mode)`
  - Purpose: start a fresh mode session and clear per-session audit history.
  - When called: GUI mode switching.

- `EngineV2Session.set_depth_text(raw_text)`
  - Purpose: parse/log/apply AIR/AIR_O2 depth input.
  - When called: GUI depth field changes.

- `EngineV2Session.set_relief_depth_text(raw_text)`
  - Purpose: parse/log/apply CHAMBER relief depth input.
  - When called: GUI Chamber relief input changes.

- `EngineV2Session.dispatch(action_name)`
  - Purpose: log and dispatch a string-named action into the active engine.
  - When called: GUI primary/secondary/utility actions.

- `EngineV2Session.presentation_model()`
  - Purpose: build the GUI-facing `PresentationModel` from the current engine view and audit log.
  - When called: every render refresh.

- `EngineV2Session.advance_test_time(delta_seconds)`
  - Purpose: fast-forward session time by changing the test-time offset.
  - When called: GUI test-time buttons.

- `EngineV2Session.reset_test_time()`
  - Purpose: return test time to live.
  - When called: tests or future UI reset if exposed.

- `EngineV2Session.test_time_label()`
  - Purpose: format the visible test-time status string.
  - When called: GUI render.

- `EngineV2Session.raw_audit_events()`
  - Purpose: expose the full session audit/runtime log.
  - When called: tests/debugging.

- `EngineV2Session._launch_mode(mode)`
  - Purpose: internal mode-specific engine construction.
  - When called: constructor and `launch_mode()`.

- `EngineV2Session._now()`
  - Purpose: return live time plus test-time offset.
  - When called: throughout the session when time is needed.

- `EngineV2Session._schedule_label()`
  - Purpose: derive the small schedule/profile label for presentation.
  - When called: `presentation_model()`.

- `EngineV2Session._append_runtime_event(kind, payload)`
  - Purpose: append session-owned runtime log events.
  - When called: mode launches, input changes, action dispatches, test-time changes.

- `_parse_optional_int(raw_text)`
  - Purpose: parse integer input fields safely.
  - When called: depth and relief-depth setters.

- `_title_for_mode(mode)`
  - Purpose: old-shell title compatibility helper.
  - When called: session title selection.

## Projection Layer

### `src/dive_stopwatch/engine_v2/projection/gui_view.py`

- `GuiView`
  - Purpose: older compatibility projection for tests/legacy seams.

- `build_gui_view(view)`
  - Purpose: build legacy-style GUI snapshot data from `EngineView`.
  - When called: compatibility tests/older scaffolding.

### `src/dive_stopwatch/engine_v2/projection/presentation_builder.py`

- `PresentationAction`
  - Purpose: GUI-facing action label/name pair.

- `PresentationAuditRow`
  - Purpose: GUI-facing event log row with display tone.

- `PresentationTenderCard`
  - Purpose: GUI-facing tender obligations card for Chamber.

- `PresentationModel`
  - Purpose: GUI-facing view model consumed by `mobile/gui_v2.py`.

- `build_presentation_model(view, ...)`
  - Purpose: convert `EngineView` plus audit/tender/schedule context into `PresentationModel`.
  - When called: `EngineV2Session.presentation_model()`.

- `_title(mode)`
  - Purpose: GUI title by mode.
  - When called: `build_presentation_model()`.

- `_phase_label(view)`
  - Purpose: human-facing phase label.
  - When called: `build_presentation_model()`.

- `_status_label(view)`
  - Purpose: left-side status label line.
  - When called: `build_presentation_model()`.

- `_status_value_text(view)`
  - Purpose: prominent status value text.
  - When called: `build_presentation_model()`.

- `_primary_value(view)`
  - Purpose: main instrument/timer value.
  - When called: `build_presentation_model()`.

- `_depth_inline_text(view)`
  - Purpose: depth line text.
  - When called: `build_presentation_model()`.

- `_remaining_label(view)`
  - Purpose: optional remaining-time label.
  - When called: `build_presentation_model()`.

- `_depth_timer_label(view)`
  - Purpose: side timer / overtime / current stop countdown line.
  - When called: `build_presentation_model()`.

- `_summary_text(view)`
  - Purpose: line-5 `Next:` summary text and other primary prompts.
  - When called: `build_presentation_model()`.

- `_detail_text(view, selected_table_name=...)`
  - Purpose: line-6 detail/secondary context.
  - When called: `build_presentation_model()`.

- `_should_show_gas_detail(view)`
  - Purpose: suppress low-value detail echoes.
  - When called: `_detail_text()`.

- `_surd_detail_text(view)`
  - Purpose: SURD-specific detail string formatting.
  - When called: `_detail_text()`.

- `_warning_labels(warnings)`
  - Purpose: convert warning enums to labels.
  - When called: `build_presentation_model()`.

- `_summary_kind(view)`
  - Purpose: classify line-5 semantics for color handling (`default`, `o2`, `air_break`).
  - When called: `build_presentation_model()`.

- `_action_view(view, action_name)`
  - Purpose: build a labeled GUI action object.
  - When called: `build_presentation_model()`.

- `_action_label(view, action_name)`
  - Purpose: humanize action names contextually.
  - When called: `_action_view()`.

- `_prioritized_actions(view, available_actions)`
  - Purpose: choose primary/secondary/extra action order for the GUI.
  - When called: `build_presentation_model()`.

- `_utility_actions(available_actions)`
  - Purpose: separate utility actions like `RESET`.
  - When called: `build_presentation_model()`.

- `_audit_row(event)`
  - Purpose: convert an `AuditEvent` into a GUI-facing log row.
  - When called: `build_presentation_model()`.

- `_event_summary(event)`
  - Purpose: format event log text.
  - When called: `_audit_row()`.

- `_audit_tone(event)`
  - Purpose: classify event rows for color emphasis.
  - When called: `_audit_row()`.

- `_tender_card(tender_view)`
  - Purpose: convert Chamber tender view into presentation form.
  - When called: `build_presentation_model()`.

- `_format_mmss(total_sec)`
  - Purpose: timer formatter.
  - When called: multiple presentation helpers.

- `_format_tenths(total_sec)`
  - Purpose: high-resolution timer formatter.
  - When called: `_primary_value()`.

- `_format_duration_label(total_sec)`
  - Purpose: tender duration label formatter.
  - When called: `_tender_card()`.

- `_deco_mode(mode)`
  - Purpose: map `EngineMode` to AIR/AIR_O2 decompression mode.
  - When called: no-decompression preview and bottom-profile helpers.

- `_ready_no_decompression_preview(view)`
  - Purpose: compute ready-screen no-decompression preview text.
  - When called: `_summary_text()`.

- `_air_bottom_profile(view)`
  - Purpose: reconstruct the active decompression profile while on bottom.
  - When called: `_summary_text()`, `_depth_timer_label()`, `_summary_kind()`.

## AIR Mode

### `src/dive_stopwatch/engine_v2/modes/air/engine.py`

- `AirEngine.__init__(mode, now_provider)`
  - Purpose: AIR/AIR_O2 mode object wrapper.
  - When called: coordinator construction or tests.

- `AirEngine.set_depth(raw_text, depth_fsw)`
  - Purpose: update AIR max depth input.
  - When called: coordinator/session input path.

- `AirEngine.dispatch(action)`
  - Purpose: apply one AIR action and persist resulting state/events.
  - When called: coordinator dispatch.

- `AirEngine.view()`
  - Purpose: build semantic AIR `EngineView`.
  - When called: coordinator/session render path.

- `AirEngine.audit_events()`
  - Purpose: expose AIR-owned event history.
  - When called: tests/debugging.

- `AirEngine.can_switch_to_surd()`
  - Purpose: check alternate SURD handoff eligibility.
  - When called: coordinator/handoff logic.

- `AirEngine.build_surd_handoff()`
  - Purpose: construct alternate AIR->SURD handoff.
  - When called: coordinator switch path.

- `AirEngine.can_start_normal_surd_handoff()`
  - Purpose: check normal L40 SURD handoff eligibility.
  - When called: coordinator normal SURD path.

- `AirEngine.build_normal_surd_handoff()`
  - Purpose: construct normal SURD handoff.
  - When called: coordinator normal SURD path.

### `src/dive_stopwatch/engine_v2/modes/air/invariants.py`

- `validate_state(state)`
  - Purpose: guard AIR state consistency assumptions.
  - When called: immediately after AIR transition helpers mutate state.

### `src/dive_stopwatch/engine_v2/modes/air/plan.py`

- `build_air_plan(mode, depth_fsw, bottom_elapsed_sec)`
  - Purpose: build AIR/AIR_O2 decompression profile from input depth and elapsed in-water time.
  - When called: `leave_bottom()`.

- `next_required_stop(profile, current_stop_index)`
  - Purpose: find the next stop in a decompression profile.
  - When called: AIR transitions and some rules.

### `src/dive_stopwatch/engine_v2/modes/air/rules.py`

- `next_required_stop(profile, current_stop_index)`
  - Purpose: local alias/helper for next stop lookup.
  - When called: AIR transitions.

- `elapsed(timer, now)`
  - Purpose: AIR timer wrapper around shared timer elapsed.
  - When called: AIR queries/rules/transitions.

- `pause_timer(timer, now)`
  - Purpose: pause an AIR timer while preserving timer kind.
  - When called: interruption semantics.

- `current_stop_remaining_sec(state, now)`
  - Purpose: compute current stop remaining time.
  - When called: AIR rules/presentation logic.

- `continuous_o2_remaining_sec(state, now)`
  - Purpose: compute continuous O2 time remaining until air break.
  - When called: AIR break/warning logic.

- `air_break_due(state, now)`
  - Purpose: determine whether an air break warning is active.
  - When called: AIR query warnings and presentation.

- `air_break_due_remaining_sec(state, now)`
  - Purpose: countdown to air break due.
  - When called: AIR queries and line-5 presentation.

- `estimated_travel_depth(state, now)`
  - Purpose: estimate current travel depth for delay start anchoring.
  - When called: `start_delay()`.

### `src/dive_stopwatch/engine_v2/modes/air/state.py`

- Data types:
  - `AirPhase`, `AirGasState`, `AirTimerKind`, `AirTimer`, `AirPlan`, `AirDelayStatus`, `AirDelayState`, `AirOxygenState`, `AirState`
  - Purpose: AIR/AIR_O2 authoritative state model.

- `make_initial_state(mode, depth_text="", depth_fsw=None)`
  - Purpose: create clean AIR/AIR_O2 startup state.
  - When called: `AirEngine.__init__()`.

### `src/dive_stopwatch/engine_v2/modes/air/reducer.py`

- `reduce_action(state, action, now)`
  - Purpose: AIR dispatch router from action to the correct transition helper.
  - When called: `AirEngine.dispatch()`.

- `invalid_action(now, action_name)`
  - Purpose: build a standardized invalid-action event.
  - When called: reducer fallback paths.

### `src/dive_stopwatch/engine_v2/modes/air/queries.py`

- `derive_view(state, now)`
  - Purpose: convert AIR state into semantic `EngineView`.
  - When called: `AirEngine.view()`.

- `_obligation(state)`
  - Purpose: current required action.
  - When called: `derive_view()`.

- `_available_actions(state)`
  - Purpose: legal action set for the current AIR state.
  - When called: `derive_view()`.

- `_can_switch_to_surd(state)`
  - Purpose: handoff eligibility check used by action selection.
  - When called: `_available_actions()`.

- `_timer_role(kind)`
  - Purpose: map AIR timer kind to generic timer role.
  - When called: `_active_timer_view()`.

- `_active_timer_view(state, now, current_stop)`
  - Purpose: choose and format the currently displayed AIR timer.
  - When called: `derive_view()`.

- `_current_stop_remaining_sec(state, now, current_stop)`
  - Purpose: stop countdown for the current stop.
  - When called: `derive_view()`.

- `_select_active_timer(state)`
  - Purpose: default priority order for active AIR timers.
  - When called: `_active_timer_view()`.

- `_display_depth_fsw(state, now, current_stop)`
  - Purpose: compute live display depth including descent/travel freezes.
  - When called: `derive_view()`.

- `_travel_overtime_sec(state, now)`
  - Purpose: compute first-stop travel overtime.
  - When called: `derive_view()`.

- `_traveling_on_o2(state, current_stop, next_stop)`
  - Purpose: detect the special between-O2-stop travel presentation state.
  - When called: `derive_view()`, `_active_timer_view()`.

- `_traveling_on_o2_remaining_sec(state, now)`
  - Purpose: countdown for O2-travel remaining.
  - When called: `_active_timer_view()`.

- `_total_hold_elapsed_sec(state, now)`
  - Purpose: accumulated hold time for descent depth freezing.
  - When called: `_display_depth_fsw()`.

- `_active_hold_label(state, now)`
  - Purpose: build the `H1 00:45` style hold label.
  - When called: `derive_view()`.

### `src/dive_stopwatch/engine_v2/modes/air/surd_handoff_builder.py`

- `can_build_surd_handoff(state)`
  - Purpose: alternate SURD handoff eligibility.
  - When called: AIR engine/coordinator handoff logic.

- `can_build_normal_surd_handoff(state)`
  - Purpose: normal SURD handoff eligibility.
  - When called: AIR engine/coordinator handoff logic.

- `build_surd_handoff(state, now, audit_tail=())`
  - Purpose: build alternate AIR->SURD handoff payload.
  - When called: `AirEngine.build_surd_handoff()`.

- `build_normal_surd_handoff(state, now, audit_tail=())`
  - Purpose: build normal AIR->SURD handoff payload.
  - When called: `AirEngine.build_normal_surd_handoff()`.

### `src/dive_stopwatch/engine_v2/modes/air/transitions/travel_stop.py`

- `leave_surface(state, now)`
  - Purpose: start descent from ready state.
  - When called: AIR reducer on `LEAVE_SURFACE`.

- `reach_bottom(state, now)`
  - Purpose: move from descent to bottom.
  - When called: AIR reducer on `REACH_BOTTOM`.

- `leave_bottom(state, now)`
  - Purpose: build decompression plan and begin ascent/travel.
  - When called: AIR reducer on `LEAVE_BOTTOM`.

- `reach_stop(state, now)`
  - Purpose: arrive at the next decompression stop.
  - When called: AIR reducer on `REACH_STOP`.

- `leave_stop(state, now)`
  - Purpose: depart the current stop and start the next travel leg.
  - When called: AIR reducer on `LEAVE_STOP`.

- `reach_surface(state, now)`
  - Purpose: complete ascent to surface.
  - When called: AIR reducer on `REACH_SURFACE`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid event for this transition family.
  - When called: travel/stop invalid paths.

### `src/dive_stopwatch/engine_v2/modes/air/transitions/gas_management.py`

- `confirm_on_o2(state, now)`
  - Purpose: start O2 timing at a waiting-on-O2 stop.
  - When called: AIR reducer on `CONFIRM_ON_O2`.

- `toggle_off_o2(state, now)`
  - Purpose: enter/exit interrupted O2 or air break states.
  - When called: AIR reducer on `TOGGLE_OFF_O2`.

- `convert_to_air(state, now)`
  - Purpose: convert the active O2 stop/profile to AIR semantics.
  - When called: AIR reducer on `CONVERT_TO_AIR`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid event for gas-management errors.
  - When called: gas invalid paths.

### `src/dive_stopwatch/engine_v2/modes/air/transitions/delay.py`

- `start_delay(state, now)`
  - Purpose: start an ascent delay and capture frozen delay depth.
  - When called: AIR reducer on `START_DELAY`.

- `end_delay(state, now)`
  - Purpose: apply ascent delay recompute and resume travel state.
  - When called: AIR reducer on `END_DELAY`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid event for delay errors.
  - When called: delay invalid paths.

### `src/dive_stopwatch/engine_v2/modes/air/transitions/hold.py`

- `start_hold(state, now)`
  - Purpose: freeze descent depth and start hold timer.
  - When called: AIR reducer on `START_HOLD`.

- `end_hold(state, now)`
  - Purpose: end a descent hold and accumulate hold time.
  - When called: AIR reducer on `END_HOLD`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid event for hold errors.
  - When called: hold invalid paths.

## CHAMBER Mode

### `src/dive_stopwatch/engine_v2/modes/chamber/engine.py`

- `ChamberEngine.__init__(now_provider)`
  - Purpose: CHAMBER mode wrapper.
  - When called: session launch for Chamber.

- `ChamberEngine.set_relief_depth(relief_depth_fsw)`
  - Purpose: store operator-entered TT6A relief depth.
  - When called: session relief-depth input path.

- `ChamberEngine.dispatch(action)`
  - Purpose: apply a Chamber action and persist state/events.
  - When called: session dispatch in Chamber mode.

- `ChamberEngine.view()`
  - Purpose: build semantic Chamber view.
  - When called: session render.

- `ChamberEngine.tender_view()`
  - Purpose: derive secondary tender obligations view.
  - When called: presentation model building.

- `ChamberEngine.selected_table_name()`
  - Purpose: expose chosen TT5/TT6/TT6A table name.
  - When called: presentation model building.

- `ChamberEngine.audit_events()`
  - Purpose: expose chamber-local audit history.
  - When called: tests/debugging.

### `src/dive_stopwatch/engine_v2/modes/chamber/plan.py`

- `ChamberTable`, `ChamberGas`, `ChamberSegment`
  - Purpose: chamber table/segment data model.

- `build_tt5_plan(extension_count_30=0)`
  - Purpose: build TT5 segment plan.
  - When called: Chamber rules.

- `build_tt6_plan(extension_count_60=0, extension_count_30=0)`
  - Purpose: build TT6 segment plan.
  - When called: Chamber rules.

- `build_tt6a_plan(...)`
  - Purpose: build TT6A segment plan with variable relief depth.
  - When called: Chamber rules.

### `src/dive_stopwatch/engine_v2/modes/chamber/state.py`

- `ChamberPhase`, `ChamberState`
  - Purpose: authoritative Chamber state model.

- `make_initial_state()`
  - Purpose: create clean Chamber startup state.
  - When called: `ChamberEngine.__init__()`.

### `src/dive_stopwatch/engine_v2/modes/chamber/rules.py`

- `build_plan(state)`
  - Purpose: choose the active table plan from current Chamber state.
  - When called: queries and transitions.

- `current_segment(state)`
  - Purpose: return the active chamber segment.
  - When called: queries, transitions, tender view.

- `next_segment(state)`
  - Purpose: return the next chamber segment.
  - When called: queries and transitions.

- `segment_elapsed(state, now)`
  - Purpose: elapsed time in the active chamber segment.
  - When called: queries.

- `segment_remaining(state, now)`
  - Purpose: remaining time in the active chamber segment.
  - When called: queries.

- `can_add_extension(state, now)`
  - Purpose: determine whether Chamber extension action is legal.
  - When called: queries and reducer.

### `src/dive_stopwatch/engine_v2/modes/chamber/queries.py`

- `derive_view(state, now)`
  - Purpose: convert Chamber state into semantic `EngineView`.
  - When called: `ChamberEngine.view()`.

- `_gas_state_name(state, seg)`
  - Purpose: derive chamber gas-state label from state/segment.
  - When called: `derive_view()`.

- `_obligation(state)`
  - Purpose: current required Chamber action.
  - When called: `derive_view()`.

- `_available_actions(state, now)`
  - Purpose: legal Chamber actions for current state.
  - When called: `derive_view()`.

- `_active_timer(state, now, seg)`
  - Purpose: active chamber timer selection.
  - When called: `derive_view()`.

- `state_descent_proxy(state)`
  - Purpose: helper for modeling initial descent to 60 or relief depth.
  - When called: `_display_depth_fsw()`.

- `_display_depth_fsw(state, now)`
  - Purpose: compute live Chamber display depth.
  - When called: `derive_view()`.

### `src/dive_stopwatch/engine_v2/modes/chamber/reducer.py`

- `reduce_action(state, action, now)`
  - Purpose: router from Chamber actions to Chamber transition helpers.
  - When called: `ChamberEngine.dispatch()`.

- `start_chamber(state, now)`
  - Purpose: enter Chamber descent workflow.
  - When called: reducer on `START_CHAMBER`.

- `reach_treatment_depth(state, now)`
  - Purpose: arrive at initial 60 fsw checkpoint or relief depth checkpoint.
  - When called: reducer on `REACH_TREATMENT_DEPTH`.

- `select_tt5(state, now)`
  - Purpose: choose TT5.
  - When called: reducer on `SELECT_TT5`.

- `select_tt6(state, now)`
  - Purpose: choose TT6.
  - When called: reducer on `SELECT_TT6`.

- `select_tt6a(state, now)`
  - Purpose: choose TT6A.
  - When called: reducer on `SELECT_TT6A`.

- `advance_segment(state, now)`
  - Purpose: advance to the next Chamber segment.
  - When called: reducer on `ADVANCE_SEGMENT`.

- `add_extension(state, now)`
  - Purpose: add table extension where legal.
  - When called: reducer on `ADD_EXTENSION`.

- `log_assessment_event(...)`
  - Purpose: emit audit-only 60 fsw assessment events.
  - When called: reducer on the `LOG_*_AT_60` actions.

- `_select_table(state, now, table=...)`
  - Purpose: shared helper for TT5/TT6/TT6A table selection.
  - When called: `select_tt5()`, `select_tt6()`, `select_tt6a()`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid-action event for Chamber.
  - When called: invalid reducer paths.

### `src/dive_stopwatch/engine_v2/modes/chamber/tender.py`

- `ChamberTenderView`
  - Purpose: derived tender obligations model.

- `derive_tender_view(state)`
  - Purpose: compute tender obligations from active Chamber table state.
  - When called: `ChamberEngine.tender_view()`.

## SURD Mode

### `src/dive_stopwatch/engine_v2/modes/surd/engine.py`

- `SurdEngine.__init__(now_provider)`
  - Purpose: SURD mode wrapper.
  - When called: coordinator setup or tests.

- `SurdEngine.start_handoff(handoff)`
  - Purpose: initialize SURD from an AIR handoff.
  - When called: coordinator handoff activation.

- `SurdEngine.dispatch(action)`
  - Purpose: apply one SURD action and persist state/events.
  - When called: coordinator dispatch in SURD mode.

- `SurdEngine.view()`
  - Purpose: build semantic SURD view.
  - When called: coordinator/session render path.

- `SurdEngine.audit_events()`
  - Purpose: expose SURD-local events.
  - When called: tests/debugging.

### `src/dive_stopwatch/engine_v2/modes/surd/invariants.py`

- `validate_state(state)`
  - Purpose: guard SURD state consistency.
  - When called: after SURD transitions.

### `src/dive_stopwatch/engine_v2/modes/surd/plan.py`

- `SurdPenaltyKind`, `SurdChamberSegment`, `SurdChamberPlan`
  - Purpose: SURD chamber-plan model.

- `build_surd_chamber_plan(input_depth_fsw, input_bottom_time_min, penalty_kind)`
  - Purpose: build the SURD chamber segment plan.
  - When called: SURD surface-interval -> chamber transition.

### `src/dive_stopwatch/engine_v2/modes/surd/state.py`

- `SurdPhase`, `SurdState`
  - Purpose: authoritative SURD state model.

- `make_initial_state()`
  - Purpose: create clean SURD startup state.
  - When called: `SurdEngine.__init__()`.

### `src/dive_stopwatch/engine_v2/modes/surd/rules.py`

- `current_segment(state)`
  - Purpose: active SURD chamber segment lookup.
  - When called: SURD queries/transitions.

- `next_segment(state)`
  - Purpose: next SURD chamber segment lookup.
  - When called: SURD queries/transitions.

- `surface_interval_penalty_kind(interval_elapsed_sec)`
  - Purpose: classify SURD surface-interval penalty/exceeded branch.
  - When called: surface interval transitions/queries.

### `src/dive_stopwatch/engine_v2/modes/surd/queries.py`

- `derive_view(state, now)`
  - Purpose: convert SURD state into semantic `EngineView`.
  - When called: `SurdEngine.view()`.

- `_gas_state_name(state)`
  - Purpose: derive SURD gas-state label.
  - When called: `derive_view()`.

- `_obligation(state, now)`
  - Purpose: current required SURD action.
  - When called: `derive_view()`.

- `_available_actions(state, now)`
  - Purpose: legal SURD actions by state.
  - When called: `derive_view()`.

- `_active_timer(state, now, seg)`
  - Purpose: choose the visible SURD timer.
  - When called: `derive_view()`.

- `_current_remaining(state, now, seg)`
  - Purpose: current segment remaining time.
  - When called: `derive_view()`.

- `_warnings(state, now)`
  - Purpose: derive SURD warning flags.
  - When called: `derive_view()`.

- `_display_depth_fsw(state, now, seg)`
  - Purpose: compute live SURD display depth.
  - When called: `derive_view()`.

### `src/dive_stopwatch/engine_v2/modes/surd/reducer.py`

- `reduce_action(state, action, now)`
  - Purpose: route SURD actions to surface/chamber transition helpers.
  - When called: `SurdEngine.dispatch()`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid SURD event.
  - When called: reducer fallback.

### `src/dive_stopwatch/engine_v2/modes/surd/transitions/entry.py`

- `start_from_handoff(state, handoff)`
  - Purpose: initialize SURD state from AIR handoff data.
  - When called: `SurdEngine.start_handoff()` and coordinator activation.

### `src/dive_stopwatch/engine_v2/modes/surd/transitions/surface_interval.py`

- `reach_surface(state, now)`
  - Purpose: leave in-water stop and start surface interval.
  - When called: reducer on `REACH_SURFACE`.

- `leave_surface(state, now)`
  - Purpose: leave undress stage and start chamber transfer.
  - When called: reducer on `LEAVE_SURFACE`.

- `reach_chamber_50(state, now)`
  - Purpose: arrive at chamber 50 and instantiate SURD chamber plan.
  - When called: reducer on `REACH_CHAMBER_50`.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid SURD surface-interval event.
  - When called: invalid paths in this transition family.

### `src/dive_stopwatch/engine_v2/modes/surd/transitions/chamber.py`

- `confirm_on_o2(state, now)`
  - Purpose: start/confirm O2 in SURD chamber treatment.
  - When called: reducer on `CONFIRM_ON_O2`.

- `toggle_off_o2(state, now)`
  - Purpose: enter/exit O2 interruption states.
  - When called: reducer on `TOGGLE_OFF_O2`.

- `move_chamber(state, now)`
  - Purpose: advance chamber depth to the next segment.
  - When called: reducer on `MOVE_CHAMBER`.

- `start_air_break(state, now)`
  - Purpose: begin SURD air break.
  - When called: reducer on `START_AIR_BREAK`.

- `end_air_break(state, now)`
  - Purpose: resume after air break.
  - When called: reducer on `END_AIR_BREAK`.

- `complete_to_surface(state, now)`
  - Purpose: complete SURD treatment to surface.
  - When called: reducer on `COMPLETE_TO_SURFACE`.

- `maybe_finish_clean_time(state, now)`
  - Purpose: auto-finish the clean-time phase when timer expires.
  - When called: chamber transition helpers after relevant actions.

- `invalid_action(now, action_name)`
  - Purpose: standardized invalid SURD chamber event.
  - When called: invalid paths in this transition family.

## Suggested Reading Order

If you need to understand execution quickly, read in this order:

1. `runtime/session.py`
2. `runtime/coordinator.py`
3. `modes/air/engine.py`
4. `modes/air/reducer.py`
5. `modes/air/transitions/*`
6. `modes/air/queries.py`
7. `projection/presentation_builder.py`

Then repeat the same pattern for:
- `modes/surd/*`
- `modes/chamber/*`
