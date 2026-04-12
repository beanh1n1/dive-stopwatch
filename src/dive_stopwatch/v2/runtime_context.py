from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .facts import DiveFacts
from .models import AirBreakEventV2


@dataclass(frozen=True)
class DecisionInputs:
    at_o2_stop: bool
    active_air_break: AirBreakEventV2 | None
    active_air_break_elapsed_seconds: float
    can_start_air_break: bool
    awaiting_first_o2_confirmation: bool
    active_o2_display_mode: bool
    air_break_due_in_seconds: float | None
    show_tsv: bool
    start_reaches_surface: bool


@dataclass(frozen=True)
class KernelContext:
    now: datetime
    facts: DiveFacts
    profile: Any
    decision_inputs: DecisionInputs


class _EngineDecisionOps(Protocol):
    def _is_at_o2_stop(self, profile) -> bool: ...
    def _active_air_break(self) -> AirBreakEventV2 | None: ...
    def _active_air_break_elapsed(self) -> float: ...
    def _can_start_air_break(self, profile) -> bool: ...
    def _awaiting_first_o2_confirmation(self, profile) -> bool: ...
    def _active_o2_display_mode(self, profile) -> bool: ...
    def _air_break_due_in_seconds(self) -> float | None: ...
    def _show_tsv(self, profile) -> bool: ...
    def _start_reaches_surface(self, now: datetime) -> bool: ...


class RuntimeContextBuilder:
    def build(
        self,
        engine: _EngineDecisionOps,
        *,
        now: datetime,
        facts: DiveFacts,
        profile,
    ) -> KernelContext:
        at_o2_stop = engine._is_at_o2_stop(profile)
        active_air_break = engine._active_air_break()
        decision_inputs = DecisionInputs(
            at_o2_stop=at_o2_stop,
            active_air_break=active_air_break,
            active_air_break_elapsed_seconds=engine._active_air_break_elapsed(),
            can_start_air_break=engine._can_start_air_break(profile),
            awaiting_first_o2_confirmation=engine._awaiting_first_o2_confirmation(profile),
            active_o2_display_mode=engine._active_o2_display_mode(profile),
            air_break_due_in_seconds=engine._air_break_due_in_seconds(),
            show_tsv=engine._show_tsv(profile),
            start_reaches_surface=engine._start_reaches_surface(now),
        )
        return KernelContext(
            now=now,
            facts=facts,
            profile=profile,
            decision_inputs=decision_inputs,
        )
