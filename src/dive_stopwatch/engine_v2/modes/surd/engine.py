from __future__ import annotations

from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.chamber_handoff import SurdToChamberHandoff
from ...contracts.events import AuditEvent
from ...contracts.surd_handoff import InWaterToSurdHandoff
from ...contracts.view import EngineView
from .chamber_handoff_builder import build_chamber_handoff, can_build_chamber_handoff
from .queries import derive_view
from .reducer import reduce_action, start_from_handoff
from .transitions.chamber import maybe_finish_clean_time
from .state import SurdState, make_initial_state


class SurdEngine:
    def __init__(self, *, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self.state = make_initial_state()
        self._events: tuple[AuditEvent, ...] = ()

    def start_handoff(self, handoff: InWaterToSurdHandoff) -> None:
        self.state = start_from_handoff(self.state, handoff)

    def tick(self) -> None:
        self.state = maybe_finish_clean_time(self.state, self._now_provider())

    def dispatch(self, action: EngineAction) -> tuple[AuditEvent, ...]:
        self.tick()
        state, events = reduce_action(self.state, action, self._now_provider())
        self.state = state
        self._events = self._events + events
        return events

    def view(self) -> EngineView:
        self.tick()
        return derive_view(self.state, self._now_provider())

    def schedule_label(self) -> str:
        handoff = self.state.handoff
        if handoff is None:
            return ""
        if handoff.source_table_depth_fsw is None or handoff.source_table_bottom_time_min is None:
            return ""
        return f"{handoff.source_table_depth_fsw} / {handoff.source_table_bottom_time_min}"

    def audit_events(self) -> tuple[AuditEvent, ...]:
        return self._events

    def can_handoff_to_chamber(self) -> bool:
        return can_build_chamber_handoff(self.state, now=self._now_provider())

    def build_chamber_handoff(self) -> SurdToChamberHandoff:
        return build_chamber_handoff(self.state, now=self._now_provider(), audit_tail=self._events)
