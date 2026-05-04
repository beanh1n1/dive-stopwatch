from __future__ import annotations

from datetime import datetime

from ...air_o2_snapshot import Snapshot
from .queries import derive_semantic_view
from .state import AirV2Phase, AirV2State


def project_legacy_snapshot(state: AirV2State, now: datetime) -> Snapshot:
    """Temporary compatibility adapter.

    This is intentionally narrow. It exists so the new scaffold can be exercised
    without dragging legacy snapshot concepts into the reducer or state model.
    """

    view = derive_semantic_view(state, now)
    status_text = {
        AirV2Phase.READY: "READY",
        AirV2Phase.DESCENT: "DESCENT",
        AirV2Phase.BOTTOM: "BOTTOM",
        AirV2Phase.TRAVEL_TO_FIRST_STOP: "TRAVELING",
        AirV2Phase.TRAVEL_TO_SURFACE: "TRAVELING",
        AirV2Phase.AT_STOP: "AT STOP",
        AirV2Phase.COMPLETE: "SURFACE",
    }[view.phase]
    summary_text = "Next: --"
    if view.phase is AirV2Phase.TRAVEL_TO_SURFACE:
        summary_text = "Next: Surface"
    elif view.next_stop_depth_fsw is not None and view.next_stop_duration_min is not None:
        summary_text = f"Next: {view.next_stop_depth_fsw} fsw for {view.next_stop_duration_min} min"
    return Snapshot(
        mode_text=state.mode.value,
        profile_schedule_text="",
        status_text=status_text,
        status_value_text=status_text.title(),
        status_value_kind="default",
        primary_text="00:00.0" if view.active_timer_elapsed_sec is None else _format_tenths(view.active_timer_elapsed_sec),
        primary_value_text="00:00.0" if view.active_timer_elapsed_sec is None else _format_tenths(view.active_timer_elapsed_sec),
        primary_value_kind="default",
        depth_text="Max -- fsw" if state.depth_fsw is None else f"{state.depth_fsw} fsw",
        depth_timer_text="",
        depth_timer_kind="default",
        remaining_text="",
        summary_text=summary_text,
        summary_value_kind="default",
        detail_text="",
        primary_button_label=view.obligation.name.replace("_", " ").title(),
        secondary_button_label="",
        primary_button_enabled=True,
        secondary_button_enabled=False,
    )


def _format_tenths(seconds: float) -> str:
    total_tenths = max(int(seconds * 10), 0)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"
