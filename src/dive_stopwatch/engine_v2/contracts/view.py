from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class EngineMode(Enum):
    AIR = auto()
    AIR_O2 = auto()
    MIXED_GAS = auto()
    SURD = auto()
    CHAMBER = auto()


class TimerRole(Enum):
    BOTTOM = auto()
    TRAVEL = auto()
    STOP = auto()
    SURFACE_INTERVAL = auto()
    CHAMBER_SEGMENT = auto()
    AIR_BREAK = auto()
    CLEAN_TIME = auto()


class ObligationKind(Enum):
    NONE = auto()
    START_CHAMBER = auto()
    REACH_TREATMENT_DEPTH = auto()
    SELECT_TT5 = auto()
    SELECT_TT6 = auto()
    SELECT_TT6A = auto()
    ADVANCE_SEGMENT = auto()
    ADD_EXTENSION = auto()
    LEAVE_SURFACE = auto()
    REACH_BOTTOM = auto()
    LEAVE_BOTTOM = auto()
    REACH_STOP = auto()
    LEAVE_STOP = auto()
    CONFIRM_BOTTOM_MIX = auto()
    CONFIRM_50_50 = auto()
    CONFIRM_ON_O2 = auto()
    REACH_SURFACE = auto()
    SWITCH_TO_MIXED_GAS_SURFACE_DECOMPRESSION = auto()
    REACH_CHAMBER_50 = auto()
    MOVE_CHAMBER = auto()
    START_AIR_BREAK = auto()
    END_AIR_BREAK = auto()
    COMPLETE_TO_SURFACE = auto()


class WarningKind(Enum):
    NONE = auto()
    AIR_BREAK_DUE = auto()
    SURFACE_INTERVAL_PENALTY = auto()
    SURFACE_INTERVAL_EXCEEDED = auto()
    UNSUPPORTED_DEPTH = auto()
    UNSUPPORTED_BOTTOM_MIX = auto()


@dataclass(frozen=True)
class TimerView:
    role: TimerRole
    elapsed_sec: float
    remaining_sec: float | None = None


@dataclass(frozen=True)
class EngineView:
    mode: EngineMode
    phase_name: str
    gas_state_name: str
    committed_depth_fsw: int | None
    display_depth_fsw: int | None
    obligation: ObligationKind
    active_timer: TimerView | None
    next_stop_depth_fsw: int | None
    next_stop_duration_min: int | None
    current_stop_depth_fsw: int | None
    current_stop_remaining_sec: float | None
    available_actions: tuple[str, ...]
    travel_overtime_sec: float | None = None
    current_stop_gas_name: str | None = None
    next_stop_gas_name: str | None = None
    active_hold_label: str | None = None
    delay_active: bool = False
    traveling_on_o2: bool = False
    air_break_due_remaining_sec: float | None = None
    bottom_table_depth_fsw: int | None = None
    bottom_table_bottom_time_min: int | None = None
    bottom_repeat_group: str | None = None
    bottom_next_stop_depth_fsw: int | None = None
    bottom_next_stop_duration_min: int | None = None
    bottom_next_stop_gas_name: str | None = None
    warnings: tuple[WarningKind, ...] = ()
    gas_mix_label: str | None = None
    pending_action_text: str | None = None
    profile_preview_label: str | None = None
    surface_deco_required: bool = False
    surd_surface_half_periods: int | None = None
