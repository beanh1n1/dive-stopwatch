from __future__ import annotations

from datetime import datetime

from ..air_o2_profiles import DecoMode
from ..air_o2_snapshot import Snapshot
from .air_runtime import RedesignDiveEngine
from .protocol import OperatorAction, RuntimeStateView
from .surd_runtime import RedesignSURDEngine, RedesignSURDEntryKind, RedesignSURDHandoff
from .snapshot_projection import replace_snapshot


class RedesignRuntime:
    """Unified redesign runtime entry point.

    This is the explicit seam between fixed-mode runtime ownership and the
    AIR->SURD handoff. Tests and future UI work should talk to this adapter,
    not stitch the redesign engines together ad hoc.
    """

    def __init__(self, *, mode: DecoMode, now_provider=None) -> None:
        if mode not in {DecoMode.AIR, DecoMode.AIR_O2, DecoMode.SURD}:
            raise ValueError(f"Unsupported redesign mode: {mode}")
        self._mode = mode
        self._now_provider = now_provider or datetime.now
        self._air = RedesignDiveEngine(mode=DecoMode.AIR if mode is DecoMode.SURD else mode, now_provider=self._now_provider)
        self._surd = RedesignSURDEngine(now_provider=self._now_provider)
        self._surface_active = False

    @property
    def state_view(self) -> RuntimeStateView:
        if self._mode is DecoMode.SURD and self._surface_active:
            return RuntimeStateView(mode=self._mode, phase_name=self._surd.state.phase.name, surface_active=True)
        return RuntimeStateView(mode=self._mode, phase_name=self._air.state.phase.name, surface_active=False)

    @property
    def active_handoff(self) -> RedesignSURDHandoff | None:
        if self._mode is not DecoMode.SURD:
            return None
        return self._surd.state.handoff

    def set_depth_text(self, raw: str) -> None:
        self._air.set_depth_text(raw)
        self._surd.set_depth_text(raw)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._air.advance_test_time(delta_seconds)
        self._surd.advance_test_time(delta_seconds)

    def reset_test_time(self) -> None:
        self._air.reset_test_time()
        self._surd.reset_test_time()

    def recall_lines(self) -> tuple[str, ...]:
        if self._mode is DecoMode.SURD and self._surface_active:
            return self._surd.recall_lines()
        return self._air.recall_lines()

    def snapshot(self) -> Snapshot:
        if self._mode is not DecoMode.SURD:
            return self._air.snapshot()
        if self._surface_active:
            snap = self._surd.snapshot()
            if self._surd.state.water_plan is not None:
                return self._replace_profile_schedule_text(snap, self._surd.state.water_plan.surface_profile)
            return snap
        snap = self._air.snapshot()
        if self._air.state.phase.name == "AT_AIR_STOP" and self._is_l40_stop():
            snap = self._replace_summary(snap, "Next: 40 fsw -> Surface", "surd_travel")
        return self._replace_mode_text(snap, DecoMode.SURD.value)

    def dispatch(self, action: OperatorAction) -> None:
        if action is OperatorAction.RESET:
            self._reset()
            return
        if self._mode is DecoMode.SURD and not self._surface_active and action is OperatorAction.LEAVE_STOP and self._should_start_surd_handoff():
            self._start_surd_handoff()
            return
        if self._mode is DecoMode.SURD and self._surface_active:
            self._surd.dispatch(action)
            return
        self._air.dispatch(action)

    def _reset(self) -> None:
        air_offset = self._air.state.test_time_offset_sec
        surd_offset = self._surd.state.test_time_offset_sec
        self._air = RedesignDiveEngine(mode=DecoMode.AIR if self._mode is DecoMode.SURD else self._mode, now_provider=self._now_provider)
        self._surd = RedesignSURDEngine(now_provider=self._now_provider)
        self._air.advance_test_time(air_offset)
        self._surd.advance_test_time(surd_offset)
        self._surface_active = False

    def _should_start_surd_handoff(self) -> bool:
        if self._air.state.phase.name != "AT_AIR_STOP" or self._air.state.plan is None:
            return False
        stop = self._air.state.plan.profile.stops[self._air.state.plan.current_stop_index - 1] if self._air.state.plan.current_stop_index else None
        return stop is not None and stop.depth_fsw == 40 and stop.gas == "air"

    def _is_l40_stop(self) -> bool:
        if self._air.state.plan is None or self._air.state.plan.current_stop_index is None:
            return False
        stop = self._air.state.plan.profile.stops[self._air.state.plan.current_stop_index - 1]
        return stop.depth_fsw == 40 and stop.gas == "air"

    def _start_surd_handoff(self) -> None:
        profile = self._air.state.plan.profile if self._air.state.plan is not None else None
        if profile is None:
            return
        current_stop_index = self._air.state.plan.current_stop_index if self._air.state.plan is not None else None
        handoff_audit = self._air.recall_lines()
        if current_stop_index is not None:
            handoff_audit = handoff_audit + (f"L{current_stop_index} {self._now_provider().strftime('%H:%M:%S')}",)
        handoff = RedesignSURDHandoff(
            entry_kind=RedesignSURDEntryKind.L40_NORMAL,
            source_mode_text=DecoMode.SURD.value,
            input_depth_fsw=profile.input_depth_fsw,
            input_bottom_time_min=profile.input_bottom_time_min,
            source_profile_schedule_text=self._snapshot_profile_schedule_text(),
            source_table_depth_fsw=profile.table_depth_fsw,
            source_table_bottom_time_min=profile.table_bottom_time_min,
            left_water_stop_depth_fsw=40,
            remaining_in_water_obligation_sec=0.0,
            handed_off_at=self._now_provider(),
            audit_lines=handoff_audit,
        )
        self._surd.start_handoff(handoff)
        self._surface_active = True

    def _snapshot_profile_schedule_text(self) -> str:
        profile = self._air.state.plan.profile if self._air.state.plan is not None else None
        if profile is None:
            return ""
        repeat_group = f" {profile.repeat_group}" if profile.repeat_group else ""
        return f"{profile.table_depth_fsw} / {profile.table_bottom_time_min}{repeat_group}"

    @staticmethod
    def _replace_mode_text(snapshot: Snapshot, mode_text: str) -> Snapshot:
        return replace_snapshot(snapshot, mode_text=mode_text)

    @staticmethod
    def _replace_summary(snapshot: Snapshot, summary_text: str, summary_value_kind: str) -> Snapshot:
        return replace_snapshot(snapshot, summary_text=summary_text, summary_value_kind=summary_value_kind)

    def _replace_profile_schedule_text(self, snapshot: Snapshot, surface_profile) -> Snapshot:
        repeat_group = f" {surface_profile.repeat_group}" if surface_profile.repeat_group else ""
        return replace_snapshot(snapshot, profile_schedule_text=f"{surface_profile.table_depth_fsw} / {surface_profile.table_bottom_time_min}{repeat_group}")
