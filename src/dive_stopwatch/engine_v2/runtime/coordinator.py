from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..domain.air_o2_profiles import DecoMode
from ..contracts.actions import EngineAction
from ..contracts.chamber_handoff import SurdToChamberHandoff
from ..contracts.events import AuditEvent, AuditEventKind
from ..contracts.modes import DecoProfile, DivingMode
from ..contracts.view import EngineView
from ..modes.air.engine import AirEngine
from ..modes.chamber.engine import ChamberEngine
from ..modes.mixed_gas.engine import MixedGasEngine
from ..modes.surd.engine import SurdEngine


def _air_deco_mode(diving_mode: DivingMode, deco_profile: DecoProfile) -> DecoMode:
    if diving_mode is DivingMode.AIR and deco_profile in {DecoProfile.AIR, DecoProfile.SURD}:
        return DecoMode.AIR
    return DecoMode.AIR_O2


def _initial_active(diving_mode: DivingMode) -> Literal["air", "mixed_gas", "surd", "chamber"]:
    if diving_mode is DivingMode.CHAMBER:
        return "chamber"
    if diving_mode is DivingMode.MIXED_GAS:
        return "mixed_gas"
    return "air"

@dataclass(frozen=True)
class CoordinatorState:
    diving_mode: DivingMode
    deco_profile: DecoProfile
    active: str


class EngineCoordinator:
    def __init__(
        self,
        *,
        diving_mode: DivingMode,
        deco_profile: DecoProfile,
        now_provider=None,
    ) -> None:
        self._diving_mode = diving_mode
        self._deco_profile = deco_profile
        self._now_provider = now_provider or datetime.now
        self._active: Literal["air", "mixed_gas", "surd", "chamber"] = _initial_active(diving_mode)
        air_mode = _air_deco_mode(diving_mode, deco_profile)
        self._air = AirEngine(
            mode=air_mode,
            selected_surd=deco_profile is DecoProfile.SURD and diving_mode is DivingMode.AIR,
            now_provider=self._now_provider,
        )
        self._mixed_gas = MixedGasEngine(
            selected_surd=deco_profile is DecoProfile.SURD and diving_mode is DivingMode.MIXED_GAS,
            now_provider=self._now_provider,
        )
        self._surd = SurdEngine(now_provider=self._now_provider)
        self._chamber = ChamberEngine(now_provider=self._now_provider)

    def set_depth(self, *, raw_text: str, depth_fsw: int | None) -> None:
        if self._active == "mixed_gas":
            self._mixed_gas.set_depth(raw_text=raw_text, depth_fsw=depth_fsw)
        elif self._active not in {"surd", "chamber"}:
            self._air.set_depth(raw_text=raw_text, depth_fsw=depth_fsw)

    def set_bottom_mix(self, *, raw_text: str, bottom_mix_o2_percent: float | None) -> None:
        if self._active == "mixed_gas":
            self._mixed_gas.set_bottom_mix(raw_text=raw_text, bottom_mix_o2_percent=bottom_mix_o2_percent)

    def set_relief_depth(self, depth_fsw: int | None) -> None:
        if self._active == "chamber":
            self._chamber.set_relief_depth(depth_fsw)

    def tick(self) -> None:
        if self._active == "surd":
            self._surd.tick()
            if self._surd.can_handoff_to_chamber():
                self._handoff_surd_to_chamber()

    def dispatch(self, action: EngineAction) -> tuple[AuditEvent, ...]:
        self.tick()

        if (
            self._active == "air"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.LEAVE_STOP
            and self._air.can_start_normal_surd_handoff()
        ):
            return self._start_normal_surd_handoff()

        if (
            self._active == "mixed_gas"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.LEAVE_STOP
            and self._mixed_gas.can_start_normal_surd_handoff()
        ):
            return self._start_normal_surd_handoff()

        if (
            self._active == "air"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.REACH_SURFACE
            and self._air.can_start_surface_surd_handoff()
        ):
            return self._start_surface_surd_handoff()

        if (
            self._active == "mixed_gas"
            and self._deco_profile is DecoProfile.SURD
            and action is EngineAction.REACH_SURFACE
            and self._mixed_gas.can_start_surface_surd_handoff()
        ):
            return self._start_surface_surd_handoff()

        if self._active == "mixed_gas":
            return self._mixed_gas.dispatch(action)
        if self._active == "chamber":
            return self._chamber.dispatch(action)
        if self._active == "surd":
            events = self._surd.dispatch(action)
            if self._surd.can_handoff_to_chamber():
                chamber_events = self._handoff_surd_to_chamber()
                return events + chamber_events
            return events
        return self._air.dispatch(action)

    def view(self) -> EngineView:
        self.tick()
        if self._active == "chamber":
            return self._chamber.view()
        if self._active == "surd":
            return self._surd.view()
        if self._active == "mixed_gas":
            return self._mixed_gas.view()
        view = self._air.view()
        return view

    def schedule_label(self) -> str:
        if self._active == "surd":
            return self._surd.schedule_label()
        if self._active == "mixed_gas":
            return self._mixed_gas.schedule_label()
        if self._active == "chamber":
            return self._chamber.schedule_label()
        return self._air.schedule_label()

    def selected_table_name(self) -> str | None:
        if self._active == "chamber":
            return self._chamber.selected_table_name()
        if self._active == "surd":
            return self._surd.schedule_label() or None
        return None

    def tender_view(self):
        if self._active == "chamber":
            return self._chamber.tender_view()
        return None

    def depth_input_text(self) -> str:
        if self._active == "mixed_gas":
            return self._mixed_gas.state.depth_text
        if self._active in {"surd", "chamber"}:
            return ""
        return self._air.state.depth_text

    def bottom_mix_input_text(self) -> str:
        if self._active == "mixed_gas":
            return self._mixed_gas.state.bottom_mix_o2_text
        return ""

    def relief_depth_input_text(self) -> str:
        if self._active == "chamber":
            return self._chamber.relief_depth_input_text()
        return ""

    def state(self) -> CoordinatorState:
        return CoordinatorState(diving_mode=self._diving_mode, deco_profile=self._deco_profile, active=self._active)

    def _start_normal_surd_handoff(self) -> tuple[AuditEvent, ...]:
        now = self._now_provider()
        active_engine = self._mixed_gas if self._active == "mixed_gas" else self._air
        handoff = active_engine.build_normal_surd_handoff()
        self._surd.start_handoff(handoff)
        self._active = "surd"
        return (
            AuditEvent(
                kind=AuditEventKind.HANDOFF_CREATED,
                at=now,
                payload={
                    "entry_kind": handoff.entry_kind.name,
                    "left_water_stop_depth_fsw": handoff.left_water_stop_depth_fsw,
                },
            ),
        )

    def _start_surface_surd_handoff(self) -> tuple[AuditEvent, ...]:
        now = self._now_provider()
        active_engine = self._mixed_gas if self._active == "mixed_gas" else self._air
        handoff = active_engine.build_surface_surd_handoff()
        self._surd.start_handoff(handoff)
        self._active = "surd"
        return (
            AuditEvent(kind=AuditEventKind.REACHED_SURFACE, at=now),
            AuditEvent(
                kind=AuditEventKind.HANDOFF_CREATED,
                at=now,
                payload={
                    "entry_kind": handoff.entry_kind.name,
                    "left_water_stop_depth_fsw": handoff.left_water_stop_depth_fsw,
                },
            ),
        )

    def _handoff_surd_to_chamber(self) -> tuple[AuditEvent, ...]:
        now = self._now_provider()
        handoff: SurdToChamberHandoff = self._surd.build_chamber_handoff()
        self._chamber.start_treatment(handoff)
        self._active = "chamber"
        self._deco_profile = DecoProfile.TREATMENT
        return (
            AuditEvent(
                kind=AuditEventKind.HANDOFF_CREATED,
                at=now,
                payload={
                    "trigger": handoff.trigger,
                    "surface_interval_elapsed_sec": handoff.surface_interval_elapsed_sec,
                },
            ),
        )
