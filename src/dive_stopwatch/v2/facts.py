from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .dive_controller import DiveController, DivePhase
from .models import ModeV2, StateV2
from .tables import DecompressionMode


@dataclass(frozen=True)
class DiveFacts:
    now: datetime
    mode: ModeV2
    deco_mode: DecompressionMode
    dive: DiveController
    phase: DivePhase
    parsed_depth_fsw: int | None
    at_stop: bool
    awaiting_leave_stop: bool
    latest_arrival_stop_number: int | None
    latest_departure_stop_number: int | None
    first_stop_arrival_stop_number: int | None
    first_o2_confirmed_at: datetime | None
    first_o2_confirmed_stop_number: int | None
    oxygen_segment_started_at: datetime | None


class FactsBuilder:
    def build(self, state: StateV2, *, now: datetime) -> DiveFacts:
        dive = state.dive
        latest_arrival = dive.latest_arrival_event()
        latest_departure = dive.latest_stop_departure_event()
        first_arrival = dive.first_stop_arrival_event()
        return DiveFacts(
            now=now,
            mode=state.mode,
            deco_mode=state.deco_mode,
            dive=dive,
            phase=dive.phase,
            parsed_depth_fsw=state.parsed_depth(),
            at_stop=dive._at_stop,
            awaiting_leave_stop=dive._awaiting_leave_stop,
            latest_arrival_stop_number=latest_arrival.stop_number if latest_arrival is not None else None,
            latest_departure_stop_number=latest_departure.stop_number if latest_departure is not None else None,
            first_stop_arrival_stop_number=first_arrival.stop_number if first_arrival is not None else None,
            first_o2_confirmed_at=state.first_o2_confirmed_at,
            first_o2_confirmed_stop_number=state.first_o2_confirmed_stop_number,
            oxygen_segment_started_at=state.oxygen_segment_started_at,
        )
