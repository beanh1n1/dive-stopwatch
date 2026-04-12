from __future__ import annotations

from datetime import datetime
from typing import Any

from .procedure_engine import ProcedureDecision, ProcedureEngine


class DecisionResolver:
    def __init__(self, procedure_engine: ProcedureEngine | None = None) -> None:
        self._procedure_engine = procedure_engine or ProcedureEngine()
        self._cached_key: tuple[Any, ...] | None = None
        self._cached_decision: ProcedureDecision | None = None

    def invalidate(self) -> None:
        self._cached_key = None
        self._cached_decision = None

    def resolve(
        self,
        *,
        state,
        now: datetime,
        profile,
        at_o2_stop: bool,
        active_air_break,
        active_air_break_elapsed_seconds: float,
        can_start_air_break: bool,
        awaiting_first_o2_confirmation: bool,
        active_o2_display_mode: bool,
        air_break_due_in_seconds: float | None,
        show_tsv: bool,
        start_reaches_surface: bool,
    ) -> ProcedureDecision:
        key = (
            int(now.timestamp()),
            state.mode,
            state.deco_mode,
            state.stopwatch.running,
            state.dive.phase,
            state.dive._at_stop,
            state.dive._awaiting_leave_stop,
            state.dive.latest_arrival_event().stop_number if state.dive.latest_arrival_event() is not None else None,
            (
                state.dive.latest_ascent_delay_event().kind,
                state.dive.latest_ascent_delay_event().index,
            )
            if state.dive.latest_ascent_delay_event() is not None
            else None,
            id(profile) if profile is not None else None,
            at_o2_stop,
            active_air_break.index if active_air_break is not None else None,
            active_air_break.kind if active_air_break is not None else None,
            int(active_air_break_elapsed_seconds),
            can_start_air_break,
            awaiting_first_o2_confirmation,
            active_o2_display_mode,
            int(air_break_due_in_seconds) if air_break_due_in_seconds is not None else None,
            show_tsv,
            start_reaches_surface,
        )
        if key == self._cached_key and self._cached_decision is not None:
            return self._cached_decision

        decision = self._procedure_engine.decide(
            state=state,
            now=now,
            profile=profile,
            at_o2_stop=at_o2_stop,
            active_air_break=active_air_break,
            active_air_break_elapsed_seconds=active_air_break_elapsed_seconds,
            can_start_air_break=can_start_air_break,
            awaiting_first_o2_confirmation=awaiting_first_o2_confirmation,
            active_o2_display_mode=active_o2_display_mode,
            air_break_due_in_seconds=air_break_due_in_seconds,
            show_tsv=show_tsv,
            start_reaches_surface=start_reaches_surface,
        )
        self._cached_key = key
        self._cached_decision = decision
        return decision
