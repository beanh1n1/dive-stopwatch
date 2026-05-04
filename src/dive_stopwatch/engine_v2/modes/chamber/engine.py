from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ...contracts.actions import EngineAction
from ...contracts.chamber_handoff import SurdToChamberHandoff
from ...contracts.events import AuditEvent
from ...contracts.timers import TimerState
from ...contracts.view import EngineView
from .queries import derive_view
from .reducer import maybe_finish_clean_time, reduce_action
from .state import ChamberPhase, ChamberState, make_initial_state


class ChamberEngine:
    def __init__(self, *, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self.state = make_initial_state()
        self._events: tuple[AuditEvent, ...] = ()

    def set_relief_depth(self, depth_fsw: int | None) -> None:
        return

    def set_depth(self, *, raw_text: str, depth_fsw: int | None) -> None:
        return

    def start_treatment(self, handoff: SurdToChamberHandoff) -> None:
        self.state = replace(
            self.state,
            treatment_handoff=handoff,
            phase=ChamberPhase.DESCENT_TO_60,
            current_depth_fsw=handoff.entry_depth_fsw,
            descent_timer=TimerState(started_at=handoff.handed_off_at),
        )

    def dispatch(self, action: EngineAction) -> tuple[AuditEvent, ...]:
        state, events = reduce_action(self.state, action, self._now_provider())
        self.state = state
        self._events = self._events + events
        return events

    def tick(self) -> None:
        self.state = maybe_finish_clean_time(self.state, self._now_provider())

    def view(self) -> EngineView:
        self.tick()
        return derive_view(self.state, self._now_provider())

    def tender_view(self):
        return None

    def selected_table_name(self) -> str | None:
        return self.state.selected_table

    def schedule_label(self) -> str:
        return self.selected_table_name() or ""

    def depth_input_text(self) -> str:
        return ""

    def bottom_mix_input_text(self) -> str:
        return ""

    def relief_depth_input_text(self) -> str:
        return ""

    def audit_events(self) -> tuple[AuditEvent, ...]:
        return self._events
