from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent
from ...contracts.surd_handoff import InWaterToSurdHandoff
from ...contracts.view import EngineView
from .queries import derive_view
from .reducer import reduce_action
from .surd_handoff_builder import (
    build_normal_surd_handoff,
    build_surface_surd_handoff,
    can_build_normal_surd_handoff,
    can_build_surface_surd_handoff,
)
from .state import MixedGasPlan, MixedGasState, make_initial_state
from .state import MixedGasPhase
from .rules import MIXED_GAS_CLEAN_TIME_SEC, elapsed


class MixedGasEngine:
    def __init__(self, *, selected_surd: bool = False, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self.state = replace(make_initial_state(), selected_surd=selected_surd)
        self._events: tuple[AuditEvent, ...] = ()

    def set_depth(self, *, raw_text: str, depth_fsw: int | None) -> None:
        self.state = replace(self.state, depth_text=raw_text, depth_fsw=depth_fsw)

    def set_bottom_mix(self, *, raw_text: str, bottom_mix_o2_percent: float | None) -> None:
        self.state = replace(
            self.state,
            bottom_mix_o2_text=raw_text,
            bottom_mix_o2_percent=bottom_mix_o2_percent,
        )

    def set_plan(self, plan: MixedGasPlan | None) -> None:
        self.state = replace(self.state, plan=plan)

    def dispatch(self, action: EngineAction) -> tuple[AuditEvent, ...]:
        self.tick()
        state, events = reduce_action(self.state, action, self._now_provider())
        self.state = state
        self._events = self._events + events
        return events

    def view(self) -> EngineView:
        self.tick()
        return derive_view(self.state, self._now_provider())

    def tick(self) -> None:
        if self.state.phase is not MixedGasPhase.COMPLETE or self.state.clean_time_timer is None:
            return
        if elapsed(self.state.clean_time_timer.timer, self._now_provider()) < MIXED_GAS_CLEAN_TIME_SEC:
            return
        self.state = MixedGasState(
            selected_surd=self.state.selected_surd,
            depth_text=self.state.depth_text,
            depth_fsw=self.state.depth_fsw,
            bottom_mix_o2_text=self.state.bottom_mix_o2_text,
            bottom_mix_o2_percent=self.state.bottom_mix_o2_percent,
        )

    def schedule_label(self) -> str:
        plan = self.state.plan
        if plan is None or plan.table_depth_fsw is None or plan.table_bottom_time_min is None:
            return ""
        return f"{plan.table_depth_fsw} / {plan.table_bottom_time_min}"

    def audit_events(self) -> tuple[AuditEvent, ...]:
        return self._events

    def can_start_normal_surd_handoff(self) -> bool:
        return can_build_normal_surd_handoff(self.state)

    def build_normal_surd_handoff(self) -> InWaterToSurdHandoff:
        return build_normal_surd_handoff(self.state, now=self._now_provider(), audit_tail=self._events)

    def can_start_surface_surd_handoff(self) -> bool:
        return can_build_surface_surd_handoff(self.state)

    def build_surface_surd_handoff(self) -> InWaterToSurdHandoff:
        return build_surface_surd_handoff(self.state, now=self._now_provider(), audit_tail=self._events)
