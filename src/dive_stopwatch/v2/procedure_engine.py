from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .dive_controller import DivePhase
from .dive_session import format_minutes_seconds
from .models import AirBreakEventV2, ModeV2, StateV2, StatusV2
from .presenter import status_from_state
from .profile_helpers import next_stop_instruction


@dataclass(frozen=True)
class ProcedureDecision:
    status: StatusV2
    timer_kind: str
    summary_text: str
    summary_targets_oxygen_stop: bool
    start_label: str
    secondary_label: str
    start_enabled: bool
    secondary_enabled: bool


class ProcedureEngine:
    def decide(
        self,
        *,
        state: StateV2,
        now: datetime,
        profile,
        at_o2_stop: bool,
        active_air_break: AirBreakEventV2 | None,
        active_air_break_elapsed_seconds: float,
        can_start_air_break: bool,
        awaiting_first_o2_confirmation: bool,
        active_o2_display_mode: bool,
        air_break_due_in_seconds: float | None,
        show_tsv: bool,
        start_reaches_surface: bool,
    ) -> ProcedureDecision:
        # Decision output controls:
        # - status vocabulary
        # - timer kind metadata
        # - summary instruction text
        # - dynamic button labels/enabled states
        status = status_from_state(state, now=now, at_o2_stop=at_o2_stop)
        timer_kind = self._timer_kind(
            state=state,
            profile=profile,
            active_air_break=active_air_break,
            awaiting_first_o2_confirmation=awaiting_first_o2_confirmation,
            show_tsv=show_tsv,
        )
        summary_text = self._summary_text(
            state=state,
            profile=profile,
            active_air_break=active_air_break,
            active_air_break_elapsed_seconds=active_air_break_elapsed_seconds,
            can_start_air_break=can_start_air_break,
            active_o2_display_mode=active_o2_display_mode,
            air_break_due_in_seconds=air_break_due_in_seconds,
        )
        start_label, secondary_label, start_enabled, secondary_enabled = self._button_labels(
            state=state,
            status=status,
            profile=profile,
            awaiting_first_o2_confirmation=awaiting_first_o2_confirmation,
            active_air_break=active_air_break,
            active_o2_display_mode=active_o2_display_mode,
            can_start_air_break=can_start_air_break,
            start_reaches_surface=start_reaches_surface,
        )
        return ProcedureDecision(
            status=status,
            timer_kind=timer_kind,
            summary_text=summary_text,
            summary_targets_oxygen_stop=self._summary_targets_oxygen_stop(summary_text),
            start_label=start_label,
            secondary_label=secondary_label,
            start_enabled=start_enabled,
            secondary_enabled=secondary_enabled,
        )

    @staticmethod
    def _summary_targets_oxygen_stop(summary_text: str) -> bool:
        return summary_text.startswith("Next: 20 fsw for ") or summary_text.startswith("Next: 30 fsw for ")

    def _summary_text(
        self,
        *,
        state: StateV2,
        profile,
        active_air_break: AirBreakEventV2 | None,
        active_air_break_elapsed_seconds: float,
        can_start_air_break: bool,
        active_o2_display_mode: bool,
        air_break_due_in_seconds: float | None,
    ) -> str:
        # Summary line always answers: "What should the diver do next?"
        if state.mode is ModeV2.STOPWATCH:
            return ""
        if state.dive.phase is DivePhase.CLEAN_TIME:
            return "Next: Surface"
        if profile is None:
            return "Next: --"
        if profile.section == "no_decompression":
            return "Next: Surface"
        if state.dive.phase is DivePhase.ASCENT:
            if active_air_break is not None:
                left = max(300.0 - active_air_break_elapsed_seconds, 0.0)
                return f"Next: Back on O2 in {format_minutes_seconds(left)}"
            if can_start_air_break:
                return "Next: 5 min Air break in 00:00"
            if active_o2_display_mode and air_break_due_in_seconds is not None:
                return f"Next: 5 min Air break in {format_minutes_seconds(air_break_due_in_seconds)}"
        latest = state.dive.latest_arrival_event()
        return next_stop_instruction(
            profile,
            latest_arrival_stop_number=latest.stop_number if latest else None,
        )

    def _timer_kind(
        self,
        *,
        state: StateV2,
        profile,
        active_air_break: AirBreakEventV2 | None,
        awaiting_first_o2_confirmation: bool,
        show_tsv: bool,
    ) -> str:
        # Timer kind is a semantic tag for parity/testing and future UI behavior.
        if state.mode is ModeV2.STOPWATCH:
            return "STOPWATCH"
        dive = state.dive
        if dive.phase is DivePhase.READY:
            return "READY_ZERO"
        if dive.phase is DivePhase.DESCENT:
            return "DESCENT_HOLD" if dive._awaiting_leave_stop else "DESCENT_TOTAL"
        if dive.phase is DivePhase.BOTTOM:
            return (
                "BOTTOM_ELAPSED"
                if profile is not None and profile.section != "no_decompression"
                else "BOTTOM_NO_DECO_REMAINING"
            )
        if dive.phase is DivePhase.ASCENT:
            if dive._at_stop:
                if active_air_break is not None:
                    return "AIR_BREAK"
                if awaiting_first_o2_confirmation:
                    return "TSV"
                return "STOP_TIMER"
            if show_tsv:
                return "TSV"
            return "ASCENT_TRAVEL"
        if dive.phase is DivePhase.CLEAN_TIME:
            return "CLEAN_TIME"
        return "READY_ZERO"

    def _button_labels(
        self,
        *,
        state: StateV2,
        status: StatusV2,
        profile,
        awaiting_first_o2_confirmation: bool,
        active_air_break: AirBreakEventV2 | None,
        active_o2_display_mode: bool,
        can_start_air_break: bool,
        start_reaches_surface: bool,
    ) -> tuple[str, str, bool, bool]:
        # Dynamic labels mirror legacy procedural behavior by phase/state.
        if state.mode is ModeV2.STOPWATCH:
            return ("Start/Stop", "Lap/Reset", True, True)

        dive = state.dive
        if status.name == "READY":
            return ("Leave Surface", "", True, False)
        if status.name == "DESCENT":
            return ("Reach Bottom", "Hold", True, True)
        if status.name == "BOTTOM":
            bottom_is_deco = profile is not None and profile.section != "no_decompression"
            return ("Leave Bottom", "Delay" if bottom_is_deco else "", True, bottom_is_deco)
        if status.name in {"AT_STOP", "AT_O2_STOP"}:
            if awaiting_first_o2_confirmation:
                return ("Leave Stop", "On O2", True, True)
            if active_air_break is not None:
                return ("Leave Stop", "On O2", True, True)
            if active_o2_display_mode or can_start_air_break:
                return ("Leave Stop", "Off O2", True, True)
            return ("Leave Stop", "", True, False)
        if status.name == "SURFACE":
            return ("", "Reset", False, True)

        latest_delay = dive.latest_ascent_delay_event()
        has_active_delay = latest_delay is not None and latest_delay.kind == "start"
        can_flag_delay = dive.phase is DivePhase.ASCENT and not dive._at_stop and profile is not None
        return (
            "Reach Surface" if start_reaches_surface else "Reach Stop",
            "Stop Delay" if has_active_delay else ("Delay" if can_flag_delay else ""),
            True,
            can_flag_delay,
        )
