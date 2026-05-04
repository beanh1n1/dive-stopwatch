from __future__ import annotations

from dataclasses import dataclass

from .queries import AirV2SemanticView


@dataclass(frozen=True)
class AirV2ViewModel:
    phase_name: str
    obligation_name: str
    timer_role_name: str | None
    schedule_mode_text: str | None


def build_view_model(view: AirV2SemanticView) -> AirV2ViewModel:
    return AirV2ViewModel(
        phase_name=view.phase.name,
        obligation_name=view.obligation.name,
        timer_role_name=None if view.active_timer_kind is None else view.active_timer_kind.name,
        schedule_mode_text=view.schedule_mode_text,
    )
