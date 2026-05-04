from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from ..contracts.actions import EngineAction
from ..contracts.events import AuditEvent, AuditEventKind
from ..contracts.modes import DecoProfile, DivingMode, VALID_PROFILES
from ..projection.dive_log import build_dive_log
from ..projection.presentation_builder import PresentationModel, build_presentation_model
from .coordinator import EngineCoordinator


class EngineV2Session:
    def __init__(
        self,
        *,
        now_provider=None,
        diving_mode: DivingMode = DivingMode.AIR,
        deco_profile: DecoProfile | None = None,
    ) -> None:
        self._live_now_provider = now_provider or datetime.now
        self._test_time_offset_sec = 0.0
        if deco_profile is None:
            deco_profile = VALID_PROFILES[diving_mode][0]
        self._diving_mode = diving_mode
        self._deco_profile = deco_profile
        self._audit_events: tuple[AuditEvent, ...] = ()
        self._engine: EngineCoordinator
        self.launch(diving_mode, deco_profile)
        self._audit_events = ()
        self._append_runtime_event(
            AuditEventKind.MODE_LAUNCHED,
            {
                "diving_mode": self._diving_mode.name,
                "deco_profile": self._deco_profile.name,
            },
        )

    @property
    def diving_mode(self) -> DivingMode:
        return self._diving_mode

    @property
    def deco_profile(self) -> DecoProfile:
        return self._deco_profile

    def launch(self, diving_mode: DivingMode, deco_profile: DecoProfile | None = None) -> None:
        if deco_profile is None:
            deco_profile = VALID_PROFILES[diving_mode][0]
        self._diving_mode = diving_mode
        self._deco_profile = deco_profile
        self._audit_events = ()
        self._engine = EngineCoordinator(
            diving_mode=diving_mode,
            deco_profile=deco_profile,
            now_provider=self._now,
        )
        self._append_runtime_event(
            AuditEventKind.MODE_LAUNCHED,
            {
                "diving_mode": diving_mode.name,
                "deco_profile": deco_profile.name,
            },
        )

    def set_deco_profile(self, profile: DecoProfile) -> None:
        self.launch(self._diving_mode, profile)

    def set_depth_text(self, raw_text: str) -> None:
        depth_fsw = _parse_optional_int(raw_text)
        self._engine.set_depth(raw_text=raw_text, depth_fsw=depth_fsw)
        if self._diving_mode is not DivingMode.CHAMBER:
            self._append_runtime_event(
                AuditEventKind.INPUT_UPDATED,
                {"field": "depth_fsw", "raw_text": raw_text, "value": depth_fsw},
            )

    def set_relief_depth_text(self, raw_text: str) -> None:
        relief_depth_fsw = _parse_optional_int(raw_text)
        self._engine.set_relief_depth(relief_depth_fsw)
        if self._diving_mode is DivingMode.CHAMBER:
            self._append_runtime_event(
                AuditEventKind.INPUT_UPDATED,
                {"field": "relief_depth_fsw", "raw_text": raw_text, "value": relief_depth_fsw},
            )

    def set_bottom_mix_text(self, raw_text: str) -> None:
        bottom_mix_o2_percent = _parse_optional_float(raw_text)
        self._engine.set_bottom_mix(raw_text=raw_text, bottom_mix_o2_percent=bottom_mix_o2_percent)
        if self._diving_mode is DivingMode.MIXED_GAS:
            self._append_runtime_event(
                AuditEventKind.INPUT_UPDATED,
                {"field": "bottom_mix_o2_percent", "raw_text": raw_text, "value": bottom_mix_o2_percent},
            )

    def dispatch(self, action_name: str) -> tuple[AuditEvent, ...]:
        action = EngineAction[action_name]
        self._append_runtime_event(
            AuditEventKind.ACTION_DISPATCHED,
            {"action": action.name},
        )
        events = self._engine.dispatch(action)
        coordinator_state = self._engine.state()
        self._diving_mode = coordinator_state.diving_mode
        self._deco_profile = coordinator_state.deco_profile
        self._audit_events = self._audit_events + events
        return events

    def presentation_model(self) -> PresentationModel:
        self._engine.tick()
        view = self._engine.view()
        selected_table_name = self._engine.selected_table_name()
        tender_view = self._engine.tender_view()
        base = build_presentation_model(
            view,
            log_rows=build_dive_log(self._audit_events, mode=view.mode),
            selected_table_name=selected_table_name,
            tender_view=tender_view,
            schedule_label=self._engine.schedule_label(),
        )
        return replace(base, title=_title_for_mode(self._diving_mode), mode_name=view.mode.name)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._test_time_offset_sec = max(self._test_time_offset_sec + delta_seconds, 0.0)
        self._append_runtime_event(
            AuditEventKind.TEST_TIME_ADVANCED,
            {"delta_sec": int(delta_seconds), "offset_sec": int(self._test_time_offset_sec)},
        )

    def reset_test_time(self) -> None:
        self._test_time_offset_sec = 0.0
        self._append_runtime_event(AuditEventKind.TEST_TIME_RESET, {"offset_sec": 0})

    def test_time_label(self) -> str:
        if abs(self._test_time_offset_sec) < 1e-9:
            return "Test Time: LIVE"
        total = int(abs(self._test_time_offset_sec))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"Test Time: +{hours}:{minutes:02d}:{seconds:02d}"
        return f"Test Time: +{minutes:02d}:{seconds:02d}"

    def raw_audit_events(self) -> tuple[AuditEvent, ...]:
        return self._audit_events

    def depth_input_text(self) -> str:
        return self._engine.depth_input_text()

    def bottom_mix_input_text(self) -> str:
        return self._engine.bottom_mix_input_text()

    def relief_depth_input_text(self) -> str:
        return self._engine.relief_depth_input_text()

    def _now(self) -> datetime:
        return self._live_now_provider() + timedelta(seconds=self._test_time_offset_sec)

    def _append_runtime_event(self, kind: AuditEventKind, payload: dict[str, object]) -> None:
        self._audit_events = self._audit_events + (AuditEvent(kind=kind, at=self._now(), payload=payload),)


def _parse_optional_int(raw_text: str) -> int | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_optional_float(raw_text: str) -> float | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None

def _title_for_mode(diving_mode: DivingMode) -> str:
    return "CAISSON Chamber" if diving_mode is DivingMode.CHAMBER else "CAISSON Active"
