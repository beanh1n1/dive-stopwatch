from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from ..air_o2_engine import Intent
from ..air_o2_profiles import DecoMode
from ..air_o2_snapshot import Snapshot


class OperatorAction(Enum):
    LEAVE_SURFACE = auto()
    REACH_BOTTOM = auto()
    LEAVE_BOTTOM = auto()
    REACH_STOP = auto()
    LEAVE_STOP = auto()
    CONFIRM_ON_O2 = auto()
    TOGGLE_OFF_O2 = auto()
    TOGGLE_DELAY = auto()
    CONVERT_TO_AIR = auto()
    REACH_SURFACE = auto()
    LEAVE_SURFACE_INTERVAL = auto()
    REACH_CHAMBER_50 = auto()
    TOGGLE_CHAMBER_O2 = auto()
    ADVANCE_CHAMBER = auto()
    RESET = auto()


@dataclass(frozen=True)
class RuntimeStateView:
    mode: DecoMode
    phase_name: str
    surface_active: bool = False


class RuntimeEngine(Protocol):
    @property
    def state_view(self) -> RuntimeStateView: ...

    def dispatch(self, action: OperatorAction) -> None: ...
    def snapshot(self) -> Snapshot: ...
    def recall_lines(self) -> tuple[str, ...]: ...
    def set_depth_text(self, raw: str) -> None: ...
    def advance_test_time(self, delta_seconds: float) -> None: ...
    def reset_test_time(self) -> None: ...


def intent_to_operator_action(intent: Intent, state_view: RuntimeStateView) -> OperatorAction | None:
    if intent is Intent.MODE:
        return None
    if intent is Intent.RESET:
        return OperatorAction.RESET

    if state_view.mode in {DecoMode.AIR, DecoMode.AIR_O2} or (state_view.mode is DecoMode.SURD and not state_view.surface_active):
        return _air_intent_to_action(intent, state_view.phase_name)
    if state_view.mode is DecoMode.SURD and state_view.surface_active:
        return _surd_intent_to_action(intent, state_view.phase_name)
    return None


def _air_intent_to_action(intent: Intent, phase_name: str) -> OperatorAction | None:
    intent_map = {
        Intent.PRIMARY: {
            "READY": OperatorAction.LEAVE_SURFACE,
            "DESCENT": OperatorAction.REACH_BOTTOM,
            "BOTTOM": OperatorAction.LEAVE_BOTTOM,
            "TRAVEL_TO_FIRST_STOP": OperatorAction.REACH_STOP,
            "TRAVEL_TO_SURFACE": OperatorAction.REACH_STOP,
            "AT_AIR_STOP": OperatorAction.LEAVE_STOP,
            "AT_O2_STOP_WAITING": OperatorAction.LEAVE_STOP,
            "AT_O2_STOP_ON_O2": OperatorAction.LEAVE_STOP,
        },
        Intent.SECONDARY: {
            "TRAVEL_TO_FIRST_STOP": OperatorAction.TOGGLE_DELAY,
            "TRAVEL_TO_SURFACE": OperatorAction.TOGGLE_DELAY,
            "AT_O2_STOP_WAITING": OperatorAction.CONFIRM_ON_O2,
            "AT_O2_STOP_ON_O2": OperatorAction.TOGGLE_OFF_O2,
            "AT_O2_STOP_OFF_O2": OperatorAction.TOGGLE_OFF_O2,
            "AT_O2_STOP_AIR_BREAK": OperatorAction.TOGGLE_OFF_O2,
        },
    }
    return intent_map.get(intent, {}).get(phase_name)


def _surd_intent_to_action(intent: Intent, phase_name: str) -> OperatorAction | None:
    intent_map = {
        Intent.PRIMARY: {
            "SURFACE_ASCENT": OperatorAction.REACH_SURFACE,
            "UNDRESS": OperatorAction.LEAVE_SURFACE_INTERVAL,
            "SURFACE_TO_CHAMBER_50": OperatorAction.REACH_CHAMBER_50,
            "CHAMBER_WAITING_ON_O2": OperatorAction.ADVANCE_CHAMBER,
            "CHAMBER_ON_O2": OperatorAction.ADVANCE_CHAMBER,
            "CHAMBER_AIR_BREAK": OperatorAction.ADVANCE_CHAMBER,
            "COMPLETE": OperatorAction.ADVANCE_CHAMBER,
        },
        Intent.SECONDARY: {
            "CHAMBER_WAITING_ON_O2": OperatorAction.TOGGLE_CHAMBER_O2,
            "CHAMBER_ON_O2": OperatorAction.TOGGLE_CHAMBER_O2,
            "CHAMBER_OFF_O2": OperatorAction.TOGGLE_CHAMBER_O2,
        },
    }
    return intent_map.get(intent, {}).get(phase_name)
