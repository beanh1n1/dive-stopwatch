from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ...domain.air_o2_profiles import DecoMode
from ...contracts.actions import EngineAction
from ...contracts.events import AuditEvent
from ...contracts.surd_handoff import InWaterToSurdHandoff
from ...contracts.view import EngineView
from .surd_handoff_builder import (
    build_normal_surd_handoff,
    build_surface_surd_handoff,
    can_build_normal_surd_handoff,
    can_build_surface_surd_handoff,
)
from .queries import derive_view
from .reducer import reduce_action
from .state import AirState, make_initial_state
from .state import AirPhase
from .rules import AIR_CLEAN_TIME_SEC, elapsed


class AirEngine:
    def __init__(self, *, mode: DecoMode, selected_surd: bool = False, now_provider=None) -> None:
        if mode not in {DecoMode.AIR, DecoMode.AIR_O2}:
            raise ValueError(f"Unsupported AIR engine mode: {mode}")
        self._now_provider = now_provider or datetime.now
        self.state = make_initial_state(mode=mode, selected_surd=selected_surd)
        self._events: tuple[AuditEvent, ...] = ()

    def set_depth(self, *, raw_text: str, depth_fsw: int | None) -> None:
        self.state = replace(self.state, depth_text=raw_text, depth_fsw=depth_fsw)

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
        if self.state.phase is not AirPhase.COMPLETE or self.state.clean_time_timer is None:
            return
        if elapsed(self.state.clean_time_timer, self._now_provider()) < AIR_CLEAN_TIME_SEC:
            return
        self.state = make_initial_state(
            mode=self.state.mode,
            selected_surd=self.state.selected_surd,
            depth_text=self.state.depth_text,
            depth_fsw=self.state.depth_fsw,
        )

    def schedule_label(self) -> str:
        profile = self.state.plan.profile if self.state.plan is not None else None
        if profile is None or profile.table_bottom_time_min is None:
            return ""
        repeat_group = f" {profile.repeat_group}" if profile.repeat_group else ""
        return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}{repeat_group}"

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
