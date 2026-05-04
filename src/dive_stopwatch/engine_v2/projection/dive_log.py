from __future__ import annotations

from dataclasses import dataclass

from ..contracts.events import AuditEvent, AuditEventKind
from ..contracts.view import EngineMode


@dataclass(frozen=True)
class DiveLogEntry:
    event_kind_name: str
    summary: str
    at_label: str
    tone: str = "default"


def build_dive_log(events: tuple[AuditEvent, ...], *, mode: EngineMode) -> tuple[DiveLogEntry, ...]:
    entries = tuple(
        _entry_for_event(event, mode=mode)
        for event in events
    )
    return tuple(entry for entry in entries if entry is not None)[-20:]


def _entry_for_event(event: AuditEvent, *, mode: EngineMode) -> DiveLogEntry | None:
    if event.kind in {
        AuditEventKind.MODE_LAUNCHED,
        AuditEventKind.INPUT_UPDATED,
        AuditEventKind.ACTION_DISPATCHED,
        AuditEventKind.TEST_TIME_ADVANCED,
        AuditEventKind.TEST_TIME_RESET,
        AuditEventKind.INVALID_ACTION,
    }:
        return None

    summary = _summary_for_event(event, mode=mode)
    if summary is None:
        return None
    return DiveLogEntry(
        event_kind_name=event.kind.name,
        summary=summary,
        at_label=event.at.strftime("%H:%M:%S"),
        tone=_tone_for_event(event),
    )


def _summary_for_event(event: AuditEvent, *, mode: EngineMode) -> str | None:
    payload = event.payload

    if event.kind is AuditEventKind.LEFT_SURFACE:
        return "LS"
    if event.kind is AuditEventKind.REACHED_BOTTOM:
        return "RB"
    if event.kind is AuditEventKind.LEFT_BOTTOM:
        schedule = payload.get("table_schedule")
        depth_fsw = payload.get("depth_fsw")
        if schedule is not None and depth_fsw is not None:
            return f"LB | {depth_fsw} fsw | {schedule}"
        if schedule is not None:
            return f"LB | {schedule}"
        return "LB"
    if event.kind is AuditEventKind.REACHED_STOP:
        confirmation = payload.get("confirmation")
        if confirmation == "bottom_mix":
            return "On Bottom-mix"
        if confirmation == "50_50":
            return "On 50/50"
        if confirmation == "on_o2":
            return "On O2"
        if confirmation == "resume_o2":
            return "Resume O2"
        if confirmation == "resume_after_break":
            return "End Air Break"
        depth_fsw = payload.get("chamber_depth_fsw", payload.get("depth_fsw"))
        penalty_kind = payload.get("penalty_kind")
        stop_index = payload.get("stop_index")
        gas = payload.get("gas")
        if depth_fsw is None and stop_index is not None:
            return f"Reached Stop {stop_index}"
        if depth_fsw is not None and penalty_kind == "PLUS_15_AT_50":
            return f"Arrive {depth_fsw} fsw | SI Penalty +15 min O2"
        if depth_fsw is not None and penalty_kind == "EXCEEDED":
            return f"Arrive {depth_fsw} fsw | SI Exceeded"
        if depth_fsw is not None and gas == "o2_waiting":
            return f"Arrive {depth_fsw} fsw | TSV"
        if depth_fsw is not None:
            return f"Arrive {depth_fsw} fsw"
        return "Reached Stop"
    if event.kind is AuditEventKind.LEFT_STOP:
        if payload.get("conversion") == "to_air":
            converted = payload.get("converted_stop_index")
            return "Convert to Air" if converted is None else f"Convert to Air | stop {converted}"
        depth_fsw = payload.get("depth_fsw")
        if depth_fsw == 20 and payload.get("bottom_time_anchor") == "grace_5_min":
            return "Leave 20 fsw | BT @ 5:00"
        return "Leave Stop" if depth_fsw is None else f"Leave {depth_fsw} fsw"
    if event.kind is AuditEventKind.REACHED_SURFACE:
        if payload.get("completion") == "to_surface":
            return "Complete To Surface"
        return "RS"
    if event.kind is AuditEventKind.HOLD_STARTED:
        hold_index = payload.get("hold_index")
        return "Hold Start" if hold_index is None else f"H{hold_index} Start"
    if event.kind is AuditEventKind.HOLD_ENDED:
        hold_index = payload.get("hold_index")
        return "Hold End" if hold_index is None else f"H{hold_index} End"
    if event.kind is AuditEventKind.GAS_INTERRUPTED:
        kind = payload.get("kind")
        depth_fsw = payload.get("depth_fsw")
        if kind == "air_break_start":
            return "Air Break Start" if depth_fsw is None else f"Air Break Start | {depth_fsw} fsw"
        if kind == "off_o2":
            return "Off O2" if depth_fsw is None else f"Off O2 | {depth_fsw} fsw"
        return "Gas Interrupted"
    if event.kind is AuditEventKind.DELAY_STARTED:
        depth_fsw = payload.get("depth_fsw")
        return "Delay Start" if depth_fsw is None else f"Delay Start | {depth_fsw} fsw"
    if event.kind is AuditEventKind.DELAY_RESOLVED:
        previous_schedule = payload.get("previous_schedule")
        updated_schedule = payload.get("updated_schedule")
        outcome = payload.get("outcome")
        branch = payload.get("branch")
        if previous_schedule is not None and updated_schedule is not None and previous_schedule != updated_schedule:
            return f"Delay Recompute | {branch} | {previous_schedule} -> {updated_schedule}" if branch is not None else f"Delay Recompute | {previous_schedule} -> {updated_schedule}"
        if previous_schedule is not None and updated_schedule is not None:
            return f"Delay Review | {branch} | {previous_schedule} unchanged" if branch is not None else f"Delay Review | {previous_schedule} unchanged"
        if outcome is not None:
            return f"Delay Resolved | {outcome}"
        if branch is not None:
            return f"Delay Resolved | {branch}"
        return "Delay Resolved"
    if event.kind is AuditEventKind.HANDOFF_CREATED:
        return "SURD Handoff Ready"
    if event.kind is AuditEventKind.CHAMBER_COMPLETE_RELIEF_AT_60:
        return "Relief @ 60"
    if event.kind is AuditEventKind.CHAMBER_NO_COMPLETE_RELIEF_AT_60:
        return "No Relief @ 60"
    if event.kind is AuditEventKind.CHAMBER_WORSENING_AT_60:
        return "Worse @ 60"

    if not payload:
        return event.kind.name.replace("_", " ").title()
    return " | ".join(
        [event.kind.name.replace("_", " ").title()]
        + [f"{key}={value}" for key, value in payload.items()]
    )


def _tone_for_event(event: AuditEvent) -> str:
    if event.kind in {AuditEventKind.GAS_INTERRUPTED, AuditEventKind.DELAY_STARTED, AuditEventKind.DELAY_RESOLVED}:
        return "warning"
    if event.kind in {
        AuditEventKind.CHAMBER_COMPLETE_RELIEF_AT_60,
        AuditEventKind.CHAMBER_NO_COMPLETE_RELIEF_AT_60,
        AuditEventKind.CHAMBER_WORSENING_AT_60,
    }:
        return "note"
    return "default"
