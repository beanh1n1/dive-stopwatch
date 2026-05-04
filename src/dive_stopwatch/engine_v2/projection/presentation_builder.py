from __future__ import annotations

from dataclasses import dataclass

from ..contracts.events import AuditEvent
from ..domain.air_o2_profiles import DecoMode, build_profile, no_decompression_limit
from ..contracts.view import EngineMode, EngineView, TimerRole, WarningKind
from ..domain.depth import depth_label
from ..modes.chamber.tender import ChamberTenderView
from .dive_log import DiveLogEntry, build_dive_log


@dataclass(frozen=True)
class PresentationAction:
    action_name: str
    label: str


@dataclass(frozen=True)
class PresentationLogRow:
    event_kind_name: str
    summary: str
    at_label: str
    tone: str


@dataclass(frozen=True)
class PresentationTenderCard:
    required_o2_at_30_label: str
    oxygen_on_ascent: bool
    stay_near_chamber_label: str
    no_fly_label: str


@dataclass(frozen=True)
class PresentationModel:
    title: str
    mode_name: str
    schedule_label: str
    phase_label: str
    gas_label: str
    status_label: str
    status_value_text: str
    primary_value: str
    depth_inline_text: str | None
    depth_timer_label: str | None
    remaining_label: str | None
    summary_kind: str
    summary_text: str
    detail_text: str
    warning_labels: tuple[str, ...]
    primary_action: PresentationAction | None
    secondary_action: PresentationAction | None
    extra_actions: tuple[PresentationAction, ...]
    utility_actions: tuple[PresentationAction, ...]
    log_rows: tuple[PresentationLogRow, ...]
    selected_table_label: str | None = None
    tender_card: PresentationTenderCard | None = None


def build_presentation_model(
    view: EngineView,
    *,
    audit_events: tuple[AuditEvent, ...] = (),
    log_rows: tuple[DiveLogEntry, ...] = (),
    selected_table_name: str | None = None,
    tender_view: ChamberTenderView | None = None,
    schedule_label: str = "",
) -> PresentationModel:
    if not log_rows and audit_events:
        log_rows = build_dive_log(audit_events, mode=view.mode)
    ordered_actions = _prioritized_actions(view, view.available_actions)
    utility_actions = tuple(_action_view(view, action_name) for action_name in _utility_actions(view.available_actions))
    primary_action = None if not ordered_actions else _action_view(view, ordered_actions[0])
    secondary_action = None if len(ordered_actions) < 2 else _action_view(view, ordered_actions[1])
    extra_actions = tuple(_action_view(view, action_name) for action_name in ordered_actions[2:])
    if view.mode is EngineMode.SURD and view.phase_name == "CHAMBER_AT_50_WAITING_O2" and ordered_actions == ("CONFIRM_ON_O2",):
        primary_action = None
        secondary_action = _action_view(view, "CONFIRM_ON_O2")
        extra_actions = ()
    if view.mode is EngineMode.SURD and view.phase_name in {"CHAMBER_ON_O2", "CHAMBER_OFF_O2", "CHAMBER_READY_TO_MOVE"}:
        primary_name = ""
        if "MOVE_CHAMBER" in view.available_actions:
            primary_name = "MOVE_CHAMBER"
        elif "COMPLETE_TO_SURFACE" in view.available_actions:
            primary_name = "COMPLETE_TO_SURFACE"
        primary_action = PresentationAction(action_name=primary_name, label="Leave Stop")
        secondary_label = "Off O2" if view.phase_name == "CHAMBER_ON_O2" else "On O2"
        secondary_action = PresentationAction(action_name="TOGGLE_OFF_O2", label=secondary_label)
        extra_actions = ()
    if view.mode is EngineMode.SURD and view.phase_name == "CHAMBER_TRAVEL_TO_SURFACE":
        primary_action = _find_action_view(view, "REACH_SURFACE")
        secondary_action = PresentationAction(action_name="", label="")
        extra_actions = ()
    if view.mode is EngineMode.CHAMBER:
        if view.phase_name == "READY":
            primary_action = _find_action_view(view, "LEAVE_SURFACE")
            secondary_action = PresentationAction(action_name="", label="Off/On O2")
            extra_actions = ()
        elif view.phase_name == "DESCENT_TO_60":
            primary_action = _find_action_view(view, "REACH_BOTTOM")
            secondary_action = PresentationAction(action_name="", label="Off/On O2")
            extra_actions = ()
        elif view.phase_name == "AT_STOP" and view.gas_state_name == "WAITING_ON_O2":
            primary_action = PresentationAction(
                action_name="LEAVE_STOP" if "LEAVE_STOP" in view.available_actions else "",
                label="Leave Stop",
            )
            secondary_action = PresentationAction(
                action_name="CONFIRM_ON_O2" if "CONFIRM_ON_O2" in view.available_actions else "",
                label="On O2",
            )
            extra_actions = ()
        elif view.phase_name in {"AT_STOP", "ON_O2"} and view.gas_state_name == "ON_O2":
            primary_action = PresentationAction(
                action_name="LEAVE_STOP" if "LEAVE_STOP" in view.available_actions else "",
                label="Leave Stop",
            )
            secondary_action = PresentationAction(
                action_name="TOGGLE_OFF_O2" if "TOGGLE_OFF_O2" in view.available_actions else "",
                label="Off O2",
            )
            extra_actions = ()
        elif view.phase_name == "AIR_BREAK":
            primary_action = PresentationAction(action_name="", label="Leave Stop")
            secondary_action = PresentationAction(
                action_name="CONFIRM_ON_O2" if "CONFIRM_ON_O2" in view.available_actions else "",
                label="On O2",
            )
            extra_actions = ()
        elif view.phase_name == "TRAVEL_TO_30":
            primary_action = _find_action_view(view, "REACH_STOP")
            secondary_action = PresentationAction(action_name="", label="Off O2")
            extra_actions = ()
        elif view.phase_name == "TRAVEL_TO_SURFACE":
            primary_action = _find_action_view(view, "REACH_SURFACE")
            secondary_action = PresentationAction(action_name="", label="Off O2")
            extra_actions = ()
    primary_action, secondary_action, extra_actions = _enforce_o2_actions_secondary(
        primary_action, secondary_action, extra_actions
    )
    return PresentationModel(
        title=_title(view.mode),
        mode_name=view.mode.name,
        schedule_label=schedule_label,
        phase_label=_phase_label(view),
        gas_label=view.gas_state_name.replace("_", " ").title(),
        status_label=_status_label(view),
        status_value_text=_status_value_text(view),
        primary_value=_primary_value(view),
        depth_inline_text=_depth_inline_text(view, schedule_label=schedule_label),
        depth_timer_label=_depth_timer_label(view),
        remaining_label=_remaining_label(view),
        summary_kind=_summary_kind(view),
        summary_text=_summary_text(view, schedule_label=schedule_label),
        detail_text=_detail_text(view, selected_table_name=selected_table_name, schedule_label=schedule_label),
        warning_labels=_warning_labels(view.warnings),
        primary_action=primary_action,
        secondary_action=secondary_action,
        extra_actions=extra_actions,
        utility_actions=utility_actions,
        log_rows=tuple(PresentationLogRow(**entry.__dict__) for entry in log_rows),
        selected_table_label=None if selected_table_name is None else selected_table_name.replace("_", " "),
        tender_card=None if tender_view is None else _tender_card(tender_view),
    )


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def _surd_leave_stop_action_name(view: EngineView) -> str:
    if view.pending_action_text == "Air Break for 5 min":
        return "START_AIR_BREAK"
    if view.next_stop_depth_fsw is None:
        return "COMPLETE_TO_SURFACE"
    return "MOVE_CHAMBER"


def _is_air_mode(mode: EngineMode) -> bool:
    return mode in {EngineMode.AIR, EngineMode.AIR_O2}


def _is_mixed_gas_mode(mode: EngineMode) -> bool:
    return mode is EngineMode.MIXED_GAS


def _is_air_travel_phase(view: EngineView) -> bool:
    return _is_air_mode(view.mode) and view.phase_name in {"TRAVEL_TO_FIRST_STOP", "TRAVEL_TO_SURFACE"}


def _is_mixed_gas_travel_phase(view: EngineView) -> bool:
    return view.mode is EngineMode.MIXED_GAS and view.phase_name in {"TRAVEL_TO_FIRST_STOP", "TRAVEL_TO_SURFACE"}


def _title(mode: EngineMode) -> str:
    return {
        EngineMode.AIR: "CAISSON Active",
        EngineMode.AIR_O2: "CAISSON Active",
        EngineMode.MIXED_GAS: "CAISSON Active",
        EngineMode.SURD: "CAISSON Active",
        EngineMode.CHAMBER: "CAISSON Chamber",
    }[mode]


def _phase_or_status_label(view: EngineView) -> str:
    if view.delay_active and view.mode in {EngineMode.AIR, EngineMode.AIR_O2, EngineMode.MIXED_GAS}:
        return "Delay"
    if view.gas_state_name == "CLEAN_TIME":
        return "Clean Time"
    return _humanize(view.phase_name)


def _phase_label(view: EngineView) -> str:
    return _phase_or_status_label(view)


def _status_label(view: EngineView) -> str:
    return _phase_or_status_label(view)


def _status_value_text(view: EngineView) -> str:
    if view.delay_active and view.mode in {EngineMode.AIR, EngineMode.AIR_O2, EngineMode.MIXED_GAS}:
        return "Delay"
    if view.gas_state_name == "CLEAN_TIME":
        return "Clean Time"
    if WarningKind.UNSUPPORTED_DEPTH in view.warnings or WarningKind.UNSUPPORTED_BOTTOM_MIX in view.warnings:
        return "Warning"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name in {"DESCENT_TO_20_ON_AIR", "DESCENT_TO_BOTTOM"}:
        return "Descent"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT":
        return "At Stop"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "BOTTOM":
        return "Bottom"
    if view.mode is EngineMode.MIXED_GAS and view.traveling_on_o2:
        return "On O2/ Traveling"
    if _is_mixed_gas_travel_phase(view):
        return "Traveling"
    if view.mode is EngineMode.AIR_O2 and view.traveling_on_o2:
        return "On O2/ Traveling"
    if view.mode is EngineMode.MIXED_GAS and view.gas_state_name == "BOTTOM_MIX":
        return "Bottom Mix"
    if view.mode is EngineMode.MIXED_GAS:
        if view.gas_state_name == "ON_O2":
            return "On O2"
        if view.gas_state_name == "WAITING_ON_O2":
            return "At Stop"
        if view.gas_state_name == "INTERRUPTED_O2":
            return "Off O2"
        if view.gas_state_name == "AIR_BREAK":
            return "Air Break"
        if view.phase_name == "AT_STOP":
            return "At Stop"
    if _is_air_travel_phase(view):
        return "Traveling"
    if view.mode is EngineMode.AIR_O2:
        if view.gas_state_name == "ON_O2":
            return "On O2"
        if view.gas_state_name == "WAITING_ON_O2":
            return "TSV"
        if view.gas_state_name == "INTERRUPTED_O2":
            return "Off O2"
        if view.gas_state_name == "AIR_BREAK":
            return "Air Break"
    if view.mode is EngineMode.SURD:
        if view.phase_name == "SURFACE_ASCENT_FROM_WATER_STOP":
            return "40 -> Surface"
        if view.phase_name == "CHAMBER_AT_50_WAITING_O2":
            return "At Stop"
        if view.phase_name == "CHAMBER_TRAVEL_TO_STOP":
            return "Traveling"
        if view.phase_name == "CHAMBER_TRAVEL_TO_SURFACE":
            return "Traveling"
        if view.gas_state_name == "ON_O2":
            return "On O2"
        if view.gas_state_name == "OFF_O2":
            return "Off O2"
        if view.gas_state_name == "AIR_BREAK":
            return "Air Break"
        if view.phase_name == "SURFACE_UNDRESS":
            return "Undress"
        if view.phase_name == "SURFACE_TO_CHAMBER_50":
            return "Surface -> 50 fsw"
        if view.phase_name == "SURFACE_INTERVAL_EXCEEDED":
            return "Surface Interval Exceeded"
    if view.mode is EngineMode.CHAMBER:
        if view.phase_name == "DESCENT_TO_60":
            return "Descent"
        if view.phase_name == "AT_STOP":
            return "At Stop"
        if view.phase_name == "ON_O2":
            return "On O2"
        if view.phase_name == "AIR_BREAK":
            return "Air Break"
        if view.phase_name in {"TRAVEL_TO_30", "TRAVEL_TO_SURFACE"}:
            return "Traveling"
        if view.phase_name == "COMPLETE_DONE":
            return "Complete"
    return _humanize(view.phase_name)


def _primary_value(view: EngineView) -> str:
    if view.active_timer is not None:
        if view.active_timer.role is TimerRole.CLEAN_TIME and view.active_timer.remaining_sec is not None:
            return _format_mmss(view.active_timer.remaining_sec)
        if view.phase_name == "READY":
            return "00:00.0"
        return _format_tenths(view.active_timer.elapsed_sec)
    if view.phase_name == "READY":
        return "00:00.0"
    if view.current_stop_depth_fsw is not None:
        return f"{view.current_stop_depth_fsw} fsw"
    if view.committed_depth_fsw is not None:
        return f"{view.committed_depth_fsw} fsw"
    return _humanize(view.gas_state_name)

def _depth_inline_text(view: EngineView, *, schedule_label: str) -> str | None:
    if view.gas_state_name == "CLEAN_TIME":
        return "Surface"
    depth_fsw = view.display_depth_fsw if view.display_depth_fsw is not None else view.committed_depth_fsw
    if depth_fsw == 0 and view.phase_name != "COMPLETE":
        return "0 fsw"
    return depth_label(depth_fsw)


def _remaining_label(view: EngineView) -> str | None:
    if view.gas_state_name == "CLEAN_TIME":
        return None
    if view.active_timer is not None and view.active_timer.role is TimerRole.CLEAN_TIME and view.active_timer.remaining_sec is not None:
        return f"Remaining: {_format_mmss(view.active_timer.remaining_sec)}"
    return None

def _depth_timer_label(view: EngineView) -> str | None:
    if view.gas_state_name == "CLEAN_TIME":
        return None
    if view.active_hold_label is not None:
        return view.active_hold_label
    if view.gas_state_name == "AIR_BREAK" and view.active_timer is not None and view.active_timer.remaining_sec is not None:
        return f"{_format_mmss(view.active_timer.remaining_sec)} left"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name in {"DESCENT_TO_20_ON_AIR", "AT_20_PREBOTTOM_SHIFT"} and view.active_timer is not None and view.active_timer.remaining_sec is not None:
        return _format_compact_mmss(view.active_timer.remaining_sec)
    if view.travel_overtime_sec is not None:
        return f"+{_format_mmss(view.travel_overtime_sec)}"
    if view.mode is EngineMode.AIR and view.phase_name == "BOTTOM" and view.bottom_next_stop_depth_fsw is None:
        if view.active_timer is not None and view.committed_depth_fsw is not None:
            if view.bottom_table_bottom_time_min is not None:
                remaining_sec = max((view.bottom_table_bottom_time_min * 60) - view.active_timer.elapsed_sec, 0.0)
                return f"{_format_mmss(remaining_sec)} remaining"
            limit_min = no_decompression_limit(_deco_mode(view.mode), view.committed_depth_fsw)
            if limit_min is not None:
                remaining_sec = max((limit_min * 60) - view.active_timer.elapsed_sec, 0.0)
                return f"{_format_mmss(remaining_sec)} remaining"
    if view.current_stop_remaining_sec is not None:
        return f"{_format_mmss(view.current_stop_remaining_sec)} left"
    if view.active_timer is not None and view.active_timer.remaining_sec is not None:
        return f"{_format_mmss(view.active_timer.remaining_sec)} left"
    return None


def _summary_text(view: EngineView, *, schedule_label: str) -> str:
    if view.gas_state_name == "CLEAN_TIME":
        return schedule_label
    if view.phase_name == "TRAVEL_TO_SURFACE":
        return "Next: Reach Surface"
    if view.mode is EngineMode.MIXED_GAS and view.gas_state_name == "AIR_BREAK":
        return "Next: On O2"
    if view.mode is EngineMode.MIXED_GAS and view.gas_state_name == "INTERRUPTED_O2":
        return "Next: On O2"
    if view.mode is EngineMode.AIR_O2 and view.gas_state_name == "INTERRUPTED_O2":
        return "Next: On O2"
    if view.air_break_due_remaining_sec is not None and view.current_stop_remaining_sec is not None and view.current_stop_remaining_sec > view.air_break_due_remaining_sec:
        return f"Next: Air break in {_format_mmss(view.air_break_due_remaining_sec)}"
    if view.phase_name == "DESCENT":
        return "Next: --"
    if _is_air_mode(view.mode) and view.phase_name == "BOTTOM":
        if view.bottom_next_stop_depth_fsw is not None and view.bottom_next_stop_duration_min is not None:
            return f"Next: {view.bottom_next_stop_depth_fsw} fsw for {view.bottom_next_stop_duration_min} min"
        surface_period_label = _surface_period_label(view)
        if surface_period_label is not None:
            return f"Next: Surface | {surface_period_label}"
        return "Next: Surface"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "BOTTOM":
        if view.bottom_next_stop_depth_fsw is not None and view.bottom_next_stop_duration_min is not None:
            return f"Next: {view.bottom_next_stop_depth_fsw} fsw for {view.bottom_next_stop_duration_min} min"
        surface_period_label = _surface_period_label(view)
        if surface_period_label is not None:
            return f"Next: Surface | {surface_period_label}"
        return "Next: Surface"
    if view.mode is EngineMode.SURD:
        if view.phase_name == "SURFACE_ASCENT_FROM_WATER_STOP":
            return "Next: Undress"
        if view.phase_name == "SURFACE_UNDRESS":
            return "Next: Surface -> 50 fsw"
        if view.phase_name == "SURFACE_TO_CHAMBER_50":
            if WarningKind.SURFACE_INTERVAL_EXCEEDED in view.warnings:
                return "Surface interval exceeded"
            if WarningKind.SURFACE_INTERVAL_PENALTY in view.warnings:
                return "Next: Chamber 50 with penalty"
            return "Next: 50 fsw"
        if view.phase_name == "CHAMBER_AT_50_WAITING_O2":
            return "Next: On O2"
        if view.phase_name == "CHAMBER_TRAVEL_TO_STOP":
            return "Next: Reach Stop"
        if view.phase_name == "CHAMBER_TRAVEL_TO_SURFACE":
            return "Next: Reach Surface"
        if view.phase_name == "CHAMBER_ON_O2":
            if view.pending_action_text is not None:
                return f"Next: {view.pending_action_text}"
            if view.next_stop_depth_fsw is not None and view.next_stop_duration_min is not None:
                return f"Next: {view.next_stop_depth_fsw} fsw for {view.next_stop_duration_min} min"
            if view.current_stop_depth_fsw == 40:
                return "Next: Air Break for 5 min"
    if view.mode is EngineMode.CHAMBER:
        if view.phase_name == "READY":
            return "Next: Leave Surface"
        if view.phase_name == "DESCENT_TO_60":
            return "Next: Reach Bottom"
        if view.pending_action_text is not None:
            return f"Next: {view.pending_action_text}"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "DESCENT_TO_20_ON_AIR":
        return "Next: 20 fsw"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT" and view.obligation.name == "LEAVE_BOTTOM":
        return "Next: Leave Bottom"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT" and view.obligation.name == "CONFIRM_BOTTOM_MIX":
        return "Next: Confirm bottom-mix"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT":
        return "Next: Leave Stop"
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "DESCENT_TO_BOTTOM":
        return "Next: --"
    if view.pending_action_text is not None:
        if view.pending_action_text == "Surface":
            surface_period_label = _surface_period_label(view)
            if surface_period_label is not None:
                return f"Next: Surface | {surface_period_label}"
        return f"Next: {view.pending_action_text}"
    if view.next_stop_depth_fsw is not None and view.next_stop_duration_min is not None:
        return f"Next: {view.next_stop_depth_fsw} fsw for {view.next_stop_duration_min} min"
    if view.current_stop_depth_fsw is not None:
        return "Next: Surface"
    if view.phase_name == "READY":
        return "Next: --"
    return _humanize(view.phase_name)


def _surface_period_label(view: EngineView) -> str | None:
    half_periods = view.surd_surface_half_periods
    if half_periods is None or half_periods <= 0:
        return None
    if view.mode is EngineMode.MIXED_GAS:
        periods = half_periods / 2
        if periods.is_integer():
            period_text = str(int(periods))
        else:
            period_text = str(periods).rstrip("0").rstrip(".")
        noun = "period" if periods == 1 else "periods"
        return f"{period_text} {noun} at 50"
    periods = half_periods / 2
    if periods.is_integer():
        period_text = str(int(periods))
    else:
        period_text = f"{periods:.1f}".lstrip("0").rstrip("0").rstrip(".")
    noun = "period" if periods == 1 else "periods"
    return f"{period_text} {noun} at 50"


def _is_air_break_next(view: EngineView) -> bool:
    if view.pending_action_text in {"Air Break for 5 min", "Air Break for 15 min"}:
        return True
    if view.mode is EngineMode.SURD and view.phase_name == "CHAMBER_ON_O2" and view.current_stop_depth_fsw == 40:
        return view.next_stop_depth_fsw is None or view.next_stop_depth_fsw == 40
    return False


def _detail_text(view: EngineView, *, selected_table_name: str | None, schedule_label: str) -> str:
    if view.gas_state_name == "CLEAN_TIME":
        return ""
    if view.mode is EngineMode.CHAMBER and selected_table_name is None:
        return ""
    if view.phase_name == "TRAVEL_TO_SURFACE":
        return ""
    details: list[str] = []
    if selected_table_name is not None:
        details.append(selected_table_name.replace("_", " "))
    if _is_air_mode(view.mode) and view.phase_name == "READY":
        preview = _ready_no_decompression_preview(view)
        if preview is not None:
            details.append(preview)
    if view.gas_mix_label is not None and view.mode is not EngineMode.MIXED_GAS:
        details.append(view.gas_mix_label)
    if view.profile_preview_label is not None and (view.mode is not EngineMode.MIXED_GAS or view.phase_name == "READY"):
        details.append(view.profile_preview_label)
    chamber_detail = _chamber_detail_text(view, selected_table_name=selected_table_name)
    surd_detail = _surd_detail_text(view)
    if chamber_detail is not None:
        details.append(chamber_detail)
    elif surd_detail is not None:
        details.append(surd_detail)
    elif _should_show_gas_detail(view):
        details.append(_humanize(view.gas_state_name))
    if view.obligation.name != "NONE" and not _summary_text(view, schedule_label=schedule_label).startswith("Next: "):
        details.append(f"Next action: {_action_label(view, view.obligation.name)}")
    return " | ".join(details)


def _chamber_detail_text(view: EngineView, *, selected_table_name: str | None) -> str | None:
    if view.mode is not EngineMode.CHAMBER or selected_table_name is None:
        return None
    if (
        view.phase_name == "AT_STOP"
        and view.current_stop_depth_fsw == 30
        and view.gas_state_name == "ON_O2"
        and view.pending_action_text in {"Air Break for 5 min", "Air Break for 15 min"}
    ):
        return "Break Pending"
    if (
        view.phase_name == "ON_O2"
        and view.current_stop_depth_fsw == 30
        and selected_table_name == "TT5"
        and view.pending_action_text == "Surface"
    ):
        return "Final On O2"
    return None


def _should_show_gas_detail(view: EngineView) -> bool:
    if view.gas_state_name in {"NONE", "", "AIR", "SURFACE"}:
        return False
    if view.gas_state_name == "COMPLETE":
        return False
    if view.mode is EngineMode.SURD and view.phase_name in {
        "CHAMBER_AT_50_WAITING_O2",
        "CHAMBER_READY_TO_MOVE",
        "CHAMBER_TRAVEL_TO_STOP",
        "CHAMBER_TRAVEL_TO_SURFACE",
        "CHAMBER_ON_O2",
        "CHAMBER_OFF_O2",
        "CHAMBER_AIR_BREAK",
    }:
        return False
    if view.gas_mix_label is not None:
        return False
    if _is_air_mode(view.mode):
        return False
    return True


def _surd_detail_text(view: EngineView) -> str | None:
    if view.mode is not EngineMode.SURD or view.active_timer is None:
        return None
    if view.phase_name in {
        "CHAMBER_AT_50_WAITING_O2",
        "CHAMBER_READY_TO_MOVE",
        "CHAMBER_TRAVEL_TO_STOP",
        "CHAMBER_TRAVEL_TO_SURFACE",
        "CHAMBER_ON_O2",
        "CHAMBER_OFF_O2",
        "CHAMBER_AIR_BREAK",
    }:
        return None
    if view.phase_name == "SURFACE_TO_CHAMBER_50" and WarningKind.SURFACE_INTERVAL_PENALTY in view.warnings:
        return "05:00-07:00 adds 15 min O2 at 50"
    if view.phase_name == "SURFACE_TO_CHAMBER_50" and WarningKind.SURFACE_INTERVAL_EXCEEDED in view.warnings:
        return "Apply >07:00 penalty path"
    if view.gas_state_name == "ON_O2" and view.current_stop_remaining_sec is not None:
        return f"O2 {_format_mmss(view.active_timer.elapsed_sec)} | {_format_mmss(view.current_stop_remaining_sec)} left"
    if view.gas_state_name == "OFF_O2" and view.current_stop_remaining_sec is not None:
        return f"Off O2 {_format_mmss(view.active_timer.elapsed_sec)} | {_format_mmss(view.current_stop_remaining_sec)} left"
    if view.gas_state_name == "AIR_BREAK" and view.active_timer.remaining_sec is not None:
        return f"Air {_format_mmss(view.active_timer.elapsed_sec)} | {_format_mmss(view.active_timer.remaining_sec)} left"
    return None


def _warning_labels(warnings: tuple[WarningKind, ...]) -> tuple[str, ...]:
    return tuple(warning.name.replace("_", " ").title() for warning in warnings if warning is not WarningKind.NONE)


def _summary_kind(view: EngineView) -> str:
    if view.gas_state_name == "CLEAN_TIME":
        return "default"
    if view.mode is EngineMode.CHAMBER and view.pending_action_text in {
        "5 min air break",
        "15 min air break",
        "Air Break for 5 min",
        "Air Break for 15 min",
    }:
        return "default"
    if _is_air_break_next(view):
        return "air_break"
    if (
        view.pending_action_text == "Surface"
        and view.mode is EngineMode.MIXED_GAS
        and view.current_stop_depth_fsw == 40
    ):
        return "surd_travel"
    if (
        view.pending_action_text == "Surface"
        and view.mode in {EngineMode.AIR, EngineMode.MIXED_GAS}
        and view.surface_deco_required
    ):
        return "surd_travel"
    if WarningKind.UNSUPPORTED_DEPTH in view.warnings or WarningKind.UNSUPPORTED_BOTTOM_MIX in view.warnings:
        return "error"
    if view.mode is EngineMode.MIXED_GAS and view.gas_state_name in {"INTERRUPTED_O2", "AIR_BREAK"}:
        return "o2"
    if view.air_break_due_remaining_sec is not None or WarningKind.AIR_BREAK_DUE in view.warnings:
        return "air_break"
    if view.gas_state_name in {"ON_O2", "WAITING_ON_O2", "INTERRUPTED_O2"}:
        return "o2"
    if view.mode in {EngineMode.AIR, EngineMode.AIR_O2} and view.phase_name == "BOTTOM":
        if view.bottom_next_stop_gas_name == "o2":
            return "o2"
    if view.current_stop_gas_name == "o2" or view.next_stop_gas_name == "o2":
        return "o2"
    return "default"


def _action_view(view: EngineView, action_name: str) -> PresentationAction:
    return PresentationAction(action_name=action_name, label=_action_label(view, action_name))


def _find_action_view(view: EngineView, action_name: str) -> PresentationAction | None:
    if action_name not in view.available_actions:
        return None
    return _action_view(view, action_name)


def _is_o2_semantic_action(action: PresentationAction | None) -> bool:
    return action is not None and action.action_name in {"CONFIRM_ON_O2", "TOGGLE_OFF_O2"}


def _enforce_o2_actions_secondary(
    primary_action: PresentationAction | None,
    secondary_action: PresentationAction | None,
    extra_actions: tuple[PresentationAction, ...],
) -> tuple[PresentationAction | None, PresentationAction | None, tuple[PresentationAction, ...]]:
    if not _is_o2_semantic_action(primary_action):
        return primary_action, secondary_action, extra_actions
    if secondary_action is not None and not _is_o2_semantic_action(secondary_action):
        return secondary_action, primary_action, extra_actions
    for idx, action in enumerate(extra_actions):
        if not _is_o2_semantic_action(action):
            reordered_extra = list(extra_actions)
            replacement = reordered_extra.pop(idx)
            if secondary_action is not None:
                reordered_extra.insert(0, secondary_action)
            return replacement, primary_action, tuple(reordered_extra)
    return None, primary_action, extra_actions


def _action_label(view: EngineView, action_name: str) -> str:
    special = {
        "SELECT_TT5": "TT5",
        "SELECT_TT6": "TT6",
        "SELECT_TT6A": "TT6A",
        "LOG_COMPLETE_RELIEF_AT_60": "Relief @ 60",
        "LOG_NO_COMPLETE_RELIEF_AT_60": "No Relief @ 60",
        "LOG_WORSENING_AT_60": "Worse @ 60",
        "START_CHAMBER": "Start Chamber",
        "START_HOLD": "Hold",
        "END_HOLD": "Stop Hold",
        "REACH_TREATMENT_DEPTH": "Reach Depth",
        "ADVANCE_SEGMENT": "Advance",
        "ADD_EXTENSION": "Add Extension",
        "START_DELAY": "Delay",
        "END_DELAY": "Stop Delay",
        "REACH_CHAMBER_50": "Reach Chamber 50",
        "COMPLETE_TO_SURFACE": "Complete To Surface",
        "START_AIR_BREAK": "Start Air Break",
        "END_AIR_BREAK": "End Air Break",
    }
    if action_name == "TOGGLE_OFF_O2":
        if view.gas_state_name == "ON_O2":
            return "Off O2"
        if view.gas_state_name in {"INTERRUPTED_O2", "AIR_BREAK"}:
            return "On O2"
        return "Off/On O2"
    if action_name == "CONFIRM_ON_O2" and view.mode is EngineMode.AIR_O2:
        return "On O2"
    if action_name == "CONFIRM_ON_O2" and view.mode is EngineMode.MIXED_GAS:
        return "On O2"
    if action_name == "CONFIRM_ON_O2" and view.mode is EngineMode.SURD:
        return "On O2"
    if action_name == "CONFIRM_ON_O2" and view.mode is EngineMode.CHAMBER:
        return "On O2"
    if action_name == "CONFIRM_BOTTOM_MIX":
        return "On Bottom-mix"
    if action_name == "CONVERT_TO_AIR" and view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT":
        return "Shift to Air"
    if action_name == "CONFIRM_50_50":
        return "Confirm 50/50"
    if action_name in {"MOVE_CHAMBER", "START_AIR_BREAK", "COMPLETE_TO_SURFACE"} and view.mode is EngineMode.SURD:
        return "Leave Stop"
    if action_name == "LEAVE_STOP" and view.mode is EngineMode.CHAMBER:
        if view.current_stop_depth_fsw == 60:
            return "Next Stop"
        if view.current_stop_depth_fsw == 30:
            return "Leave Stop"
    if action_name == "REACH_BOTTOM" and view.mode is EngineMode.CHAMBER:
        return "Reach Bottom"
    if action_name == "SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION":
        return "Surface Decompression"
    if action_name in special:
        return special[action_name]
    return action_name.replace("_", " ").title()


def _prioritized_actions(view: EngineView, available_actions: tuple[str, ...]) -> tuple[str, ...]:
    mode = view.mode
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_20_PREBOTTOM_SHIFT":
        if view.obligation.name == "LEAVE_BOTTOM":
            desired = ("LEAVE_BOTTOM", "CONFIRM_BOTTOM_MIX")
        elif view.obligation.name == "CONFIRM_BOTTOM_MIX":
            desired = ("LEAVE_STOP", "CONFIRM_BOTTOM_MIX")
        else:
            desired = ("LEAVE_STOP", "CONVERT_TO_AIR")
        return tuple(name for name in desired if name in available_actions)
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_STOP" and view.obligation.name == "CONFIRM_50_50":
        desired = ("LEAVE_STOP", "CONFIRM_50_50", "START_DELAY")
        return tuple(name for name in desired if name in available_actions)
    if view.mode is EngineMode.MIXED_GAS and view.phase_name == "AT_STOP" and view.obligation.name == "CONFIRM_ON_O2":
        desired = ("LEAVE_STOP", "CONFIRM_ON_O2", "START_DELAY")
        return tuple(name for name in desired if name in available_actions)
    if view.mode is EngineMode.AIR_O2 and view.phase_name == "AT_STOP" and view.gas_state_name == "INTERRUPTED_O2":
        desired = ("CONVERT_TO_AIR", "TOGGLE_OFF_O2", "LEAVE_STOP")
        return tuple(name for name in desired if name in available_actions)
    if view.mode in {EngineMode.AIR, EngineMode.AIR_O2, EngineMode.MIXED_GAS} and view.phase_name == "AT_STOP" and view.gas_state_name in {"ON_O2", "INTERRUPTED_O2", "AIR_BREAK"}:
        desired = ("LEAVE_STOP", "TOGGLE_OFF_O2", "CONVERT_TO_AIR")
        return tuple(name for name in desired if name in available_actions)
    priorities = {
        EngineMode.AIR: (
            "LEAVE_SURFACE",
            "REACH_BOTTOM",
            "LEAVE_BOTTOM",
            "REACH_STOP",
            "LEAVE_STOP",
            "CONFIRM_ON_O2",
            "TOGGLE_OFF_O2",
            "START_AIR_BREAK",
            "END_AIR_BREAK",
            "START_DELAY",
            "END_DELAY",
            "CONVERT_TO_AIR",
            "REACH_SURFACE",
            "RESET",
        ),
        EngineMode.AIR_O2: (
            "LEAVE_SURFACE",
            "REACH_BOTTOM",
            "LEAVE_BOTTOM",
            "REACH_STOP",
            "LEAVE_STOP",
            "CONFIRM_ON_O2",
            "TOGGLE_OFF_O2",
            "START_AIR_BREAK",
            "END_AIR_BREAK",
            "START_DELAY",
            "END_DELAY",
            "CONVERT_TO_AIR",
            "REACH_SURFACE",
            "RESET",
        ),
        EngineMode.MIXED_GAS: (
            "LEAVE_SURFACE",
            "REACH_BOTTOM",
            "REACH_STOP",
            "START_HOLD",
            "END_HOLD",
            "CONFIRM_BOTTOM_MIX",
            "CONFIRM_50_50",
            "LEAVE_STOP",
            "START_DELAY",
            "END_DELAY",
            "CONFIRM_ON_O2",
            "TOGGLE_OFF_O2",
            "LEAVE_BOTTOM",
            "REACH_SURFACE",
            "SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION",
            "RESET",
        ),
        EngineMode.SURD: (
            "REACH_SURFACE",
            "LEAVE_SURFACE",
            "REACH_CHAMBER_50",
            "CONFIRM_ON_O2",
            "MOVE_CHAMBER",
            "START_AIR_BREAK",
            "END_AIR_BREAK",
            "TOGGLE_OFF_O2",
            "COMPLETE_TO_SURFACE",
            "RESET",
        ),
        EngineMode.CHAMBER: (
            "LEAVE_SURFACE",
            "REACH_TREATMENT_DEPTH",
            "REACH_BOTTOM",
            "LEAVE_STOP",
            "CONFIRM_ON_O2",
            "TOGGLE_OFF_O2",
            "REACH_STOP",
            "REACH_SURFACE",
            "RESET",
        ),
    }[mode]
    priority_rank = {name: idx for idx, name in enumerate(priorities)}
    action_names = tuple(name for name in available_actions if name not in {"RESET"})
    if (
        view.mode in {EngineMode.AIR, EngineMode.AIR_O2, EngineMode.MIXED_GAS}
        and (
            view.phase_name == "TRAVEL_TO_SURFACE"
            or (view.phase_name == "TRAVEL_TO_FIRST_STOP" and view.pending_action_text == "Surface")
        )
        and "REACH_SURFACE" in action_names
        and "START_DELAY" in action_names
    ):
        overrides = {"REACH_SURFACE": -2, "START_DELAY": -1}
        return tuple(sorted(action_names, key=lambda name: (overrides.get(name, priority_rank.get(name, 10_000)), name)))
    return tuple(sorted(action_names, key=lambda name: (priority_rank.get(name, 10_000), name)))


def _utility_actions(available_actions: tuple[str, ...]) -> tuple[str, ...]:
    ordered = []
    if "RESET" in available_actions:
        ordered.append("RESET")
    return tuple(ordered)


def _tender_card(tender_view: ChamberTenderView) -> PresentationTenderCard:
    return PresentationTenderCard(
        required_o2_at_30_label=_format_mmss(tender_view.required_o2_at_30_sec),
        oxygen_on_ascent=tender_view.oxygen_on_ascent,
        stay_near_chamber_label=_format_duration_label(tender_view.stay_near_chamber_sec),
        no_fly_label=_format_duration_label(tender_view.no_fly_surface_interval_sec),
    )


def _format_mmss(total_sec: float) -> str:
    rounded = max(int(round(total_sec)), 0)
    minutes, seconds = divmod(rounded, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_compact_mmss(total_sec: float) -> str:
    rounded = max(int(round(total_sec)), 0)
    minutes, seconds = divmod(rounded, 60)
    return f"{minutes}:{seconds:02d}"


def _format_tenths(total_sec: float) -> str:
    tenths = max(int(total_sec * 10), 0)
    whole_seconds, tenths_part = divmod(tenths, 10)
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{tenths_part}"


def _format_duration_label(total_sec: float) -> str:
    rounded = max(int(round(total_sec)), 0)
    hours, remainder = divmod(rounded, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _deco_mode(mode: EngineMode) -> DecoMode:
    return DecoMode.AIR if mode is EngineMode.AIR else DecoMode.AIR_O2


def _ready_no_decompression_preview(view: EngineView) -> str | None:
    if view.committed_depth_fsw is None or view.mode not in {EngineMode.AIR, EngineMode.AIR_O2}:
        return None
    try:
        limit_min = no_decompression_limit(_deco_mode(view.mode), view.committed_depth_fsw)
    except KeyError:
        return None
    if limit_min is None:
        return None
    preview_profile = build_profile(_deco_mode(view.mode), view.committed_depth_fsw, limit_min)
    repeat_group = f" {preview_profile.repeat_group}" if preview_profile.repeat_group else ""
    return f"No-D Limit: {preview_profile.table_depth_fsw} / {preview_profile.table_bottom_time_min}{repeat_group}"
