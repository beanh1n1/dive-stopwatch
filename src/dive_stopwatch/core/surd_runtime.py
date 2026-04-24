from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from .air_o2_engine import (
    DiveEngine,
    DivePhase,
    EngineState,
    Intent,
    Snapshot,
)
from .air_o2_profiles import DecoMode, stop_by_index
from .air_o2_snapshot import _final_table_schedule
from .surd_engine import (
    CLEAN_TIME_SEC as SURD_CLEAN_TIME_SEC,
    L40_TO_SURFACE_SEC as SURD_L40_TO_SURFACE_SEC,
    MAX_SURFACE_INTERVAL_SEC as SURD_MAX_SURFACE_INTERVAL_SEC,
    SURFACE_INTERVAL_PENALTY_MAX_SEC as SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC,
    UNDRESS_SEC as SURD_UNDRESS_SEC,
    SurfaceEngine,
    SurfaceIntent,
    SurfaceIntervalSubphase,
    SurfacePhase,
    build_l40_surface_handoff,
    format_mmss,
)


class SurdRuntime:
    def __init__(self, now_provider=None) -> None:
        self._now_provider = now_provider
        self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
        self._surface = SurfaceEngine(now_provider=self._now_provider)
        self._surface_active = False

    @property
    def state(self) -> EngineState:
        return replace(self._air.state, deco_mode=DecoMode.SURD)

    def dispatch(self, intent: Intent) -> None:
        if intent is Intent.RESET:
            offset = self._air.state.test_time_offset_sec
            self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
            self._surface = SurfaceEngine(now_provider=self._now_provider)
            self._air.state = replace(self._air.state, test_time_offset_sec=offset)
            self._surface.state = replace(self._surface.state, test_time_offset_sec=offset)
            self._surface_active = False
            return
        if not self._surface_active:
            if intent is Intent.PRIMARY and self._should_start_surface_handoff():
                self._start_surface_handoff()
                return
            self._air.dispatch(intent)
            return
        mapped_intent = {
            Intent.PRIMARY: SurfaceIntent.PRIMARY,
            Intent.SECONDARY: SurfaceIntent.SECONDARY,
            Intent.MODE: SurfaceIntent.MODE,
            Intent.RESET: SurfaceIntent.RESET,
        }[intent]
        self._surface.dispatch(mapped_intent)

    def snapshot(self) -> Snapshot:
        if not self._surface_active:
            snap = replace(self._air.snapshot(), mode_text=DecoMode.SURD.value)
            state = self._air.state
            if state.dive.phase is DivePhase.AT_STOP and state.dive.profile is not None:
                stop = stop_by_index(state.dive.profile, state.dive.current_stop_index) if state.dive.current_stop_index is not None else None
                if stop is not None and stop.depth_fsw == 40 and stop.gas == "air":
                    snap = replace(snap, summary_text="Next: 40 fsw -> Surface", summary_value_kind="surd_travel")
            return snap
        return self._adapt_surface_snapshot()

    def recall_lines(self) -> tuple[str, ...]:
        if not self._surface_active:
            return self._air.recall_lines()
        handoff_log = () if self._surface.state.handoff is None else self._surface.state.handoff.event_log
        combined = handoff_log + self._surface.recall_lines()
        return combined[-30:]

    def set_depth_text(self, raw: str) -> None:
        self._air.set_depth_text(raw)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._air.advance_test_time(delta_seconds)
        self._surface.advance_test_time(delta_seconds)

    def reset_test_time(self) -> None:
        self._air.reset_test_time()
        self._surface.reset_test_time()

    def test_time_label(self) -> str:
        return self._air.test_time_label()

    def _should_start_surface_handoff(self) -> bool:
        state = self._air.state
        if state.dive.phase is not DivePhase.AT_STOP or state.dive.profile is None:
            return False
        stop = stop_by_index(state.dive.profile, state.dive.current_stop_index) if state.dive.current_stop_index is not None else None
        return stop is not None and stop.depth_fsw == 40 and stop.gas == "air"

    def _start_surface_handoff(self) -> None:
        profile = self._air.state.dive.profile
        if profile is None:
            return
        now = self._now_provider() + timedelta(seconds=self._air.state.test_time_offset_sec)
        handoff = build_l40_surface_handoff(
            source_mode=DecoMode.SURD.value,
            input_depth_fsw=profile.input_depth_fsw,
            input_bottom_time_min=profile.input_bottom_time_min,
            source_profile_schedule_text=_final_table_schedule(profile),
            event_log=self._air.recall_lines(),
            handed_off_at=now,
        )
        self._surface.start_handoff(handoff)
        self._surface_active = True

    def _adapt_surface_snapshot(self) -> Snapshot:
        surface_snap = self._surface.snapshot()
        state = self._surface.state
        now = self._now_provider() + timedelta(seconds=state.test_time_offset_sec)
        elapsed_sec = max((now - state.phase_started_at).total_seconds(), 0.0) if state.phase_started_at is not None else 0.0
        subphase_elapsed_sec = max((now - state.interval_subphase_started_at).total_seconds(), 0.0) if state.interval_subphase_started_at is not None else elapsed_sec
        status_text = surface_snap.status_text
        status_value_text = surface_snap.status_text
        depth_text = surface_snap.depth_text
        depth_timer_text = ""
        depth_timer_kind = "default"
        detail_text = ""

        if state.phase is SurfacePhase.SURFACE_INTERVAL:
            overdue_sec = max(elapsed_sec - SURD_MAX_SURFACE_INTERVAL_SEC, 0.0)
            if overdue_sec > 0:
                surface_interval_timer_text = f"+{format_mmss(overdue_sec)}"
                depth_timer_kind = "warning" if elapsed_sec <= SURD_SURFACE_INTERVAL_PENALTY_MAX_SEC else "air_break"
            else:
                surface_interval_timer_text = f"{format_mmss(max(SURD_MAX_SURFACE_INTERVAL_SEC - elapsed_sec, 0.0))} left"
                depth_timer_kind = "surd_travel"
            if state.interval_subphase is SurfaceIntervalSubphase.ASCENT_TO_SURFACE:
                status_text = "40 -> Surface"
                status_value_text = "40 -> Surface"
                current_depth = max(int(round(40 - ((40 / max(SURD_L40_TO_SURFACE_SEC, 1)) * min(subphase_elapsed_sec, SURD_L40_TO_SURFACE_SEC)))), 0)
                depth_text = "Surface" if current_depth <= 0 else f"{current_depth} fsw"
                depth_timer_text = surface_interval_timer_text
            elif state.interval_subphase is SurfaceIntervalSubphase.UNDRESS:
                status_text = "Undress"
                status_value_text = "Undress"
                depth_text = "Surface"
                depth_timer_text = surface_interval_timer_text
            else:
                status_text = "Surface -> 50 fsw"
                status_value_text = "Surface -> 50 fsw"
                depth_text = "50 fsw"
                depth_timer_text = surface_interval_timer_text
            if elapsed_sec > 5 * 60:
                detail_text = surface_snap.detail_text
        elif state.phase is SurfacePhase.CHAMBER_OXYGEN:
            current_segment = _current_surd_segment(state)
            depth_fsw = state.current_chamber_depth_fsw or (current_segment.depth_fsw if current_segment is not None else 50)
            depth_text = f"{depth_fsw} fsw"
            if state.off_o2_started_at is not None:
                status_text = "OFF O2"
                status_value_text = "OFF O2"
            elif current_segment is not None and state.current_o2_segment_started_at is not None:
                status_text = f"{current_segment.depth_fsw} fsw O2"
                status_value_text = f"{current_segment.depth_fsw} fsw O2"
            else:
                status_text = f"{depth_fsw} fsw"
                status_value_text = f"{depth_fsw} fsw"
            depth_timer_text = _right_of_pipe(surface_snap.detail_text)
            depth_timer_kind = surface_snap.detail_kind
        elif state.phase is SurfacePhase.CHAMBER_AIR_BREAK:
            chamber_depth = state.current_chamber_depth_fsw or 40
            status_text = f"{chamber_depth} fsw Air Break"
            status_value_text = f"{chamber_depth} fsw Air Break"
            depth_text = f"{chamber_depth} fsw"
            depth_timer_text = _right_of_pipe(surface_snap.detail_text)
            depth_timer_kind = surface_snap.detail_kind
        elif state.phase is SurfacePhase.COMPLETE:
            status_text = "CLEAN TIME"
            status_value_text = "CLEAN TIME"
            depth_text = "Surface"
            depth_timer_text = f"{format_mmss(max(SURD_CLEAN_TIME_SEC - elapsed_sec, 0.0))} left"
            depth_timer_kind = "air_break"

        return Snapshot(
            mode_text=DecoMode.SURD.value,
            profile_schedule_text="" if state.handoff is None else state.handoff.source_profile_schedule_text,
            status_text=status_text,
            status_value_text=status_value_text,
            status_value_kind=surface_snap.status_value_kind,
            primary_text=surface_snap.primary_text,
            primary_value_text=surface_snap.primary_text,
            primary_value_kind=surface_snap.primary_value_kind,
            depth_text=depth_text,
            depth_timer_text=depth_timer_text,
            depth_timer_kind=depth_timer_kind,
            remaining_text="",
            summary_text=surface_snap.summary_text,
            summary_value_kind=surface_snap.summary_value_kind,
            detail_text=detail_text,
            primary_button_label=surface_snap.primary_button_label,
            secondary_button_label=surface_snap.secondary_button_label,
            primary_button_enabled=surface_snap.primary_button_enabled,
            secondary_button_enabled=surface_snap.secondary_button_enabled,
        )


def _right_of_pipe(text: str) -> str:
    if "|" not in text:
        return ""
    return text.split("|", 1)[1].strip()


def _current_surd_segment(state) -> object | None:
    plan = getattr(state, "surd_chamber_plan", None)
    index = getattr(state, "current_o2_segment_index", None)
    if plan is None or index is None or index < 0 or index >= len(plan.segments):
        return None
    return plan.segments[index]
