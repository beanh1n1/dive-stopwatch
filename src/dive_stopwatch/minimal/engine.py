from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum, auto
import math

from .profiles import (
    DecoMode,
    DelayResult,
    DelayOutcome,
    DiveProfile,
    O2ToAirConversionResult,
    ProfileStop,
    apply_delay,
    build_profile,
    convert_remaining_o2_to_air,
    next_stop_after,
    stop_by_index,
)
from .snapshot import Snapshot, create_snapshot
from .stopwatch import StopwatchController


class DivePhase(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM = auto()
    TRAVEL = auto()
    AT_STOP = auto()
    SURFACE = auto()


class Intent(Enum):
    PRIMARY = auto()
    SECONDARY = auto()
    MODE = auto()
    RESET = auto()


@dataclass(frozen=True)
class Event:
    code: str
    timestamp: datetime


@dataclass(frozen=True)
class DelayState:
    started_at: datetime
    index: int
    depth_fsw: int
    from_stop_index: int | None


@dataclass(frozen=True)
class DelayRecomputeState:
    delay_min: int
    schedule_changed: bool
    outcome: str
    before_profile: DiveProfile
    after_profile: DiveProfile
    credited_o2_min: int = 0
    air_interruption_min: int = 0


@dataclass(frozen=True)
class OxygenState:
    first_confirmed_at: datetime | None = None
    segment_started_at: datetime | None = None
    active_air_break: datetime | None = None
    off_o2_started_at: datetime | None = None
    paused_stop_sec: float = 0.0


@dataclass(frozen=True)
class DiveState:
    phase: DivePhase = DivePhase.READY
    depth_input_text: str = ""
    events: tuple[Event, ...] = ()
    profile: DiveProfile | None = None
    profile_signature: tuple | None = None
    current_stop_index: int | None = None
    travel_delay_sec: float = 0.0
    active_delay: DelayState | None = None
    last_delay_recompute: DelayRecomputeState | None = None
    oxygen: OxygenState = field(default_factory=OxygenState)


@dataclass(frozen=True)
class EngineState:
    deco_mode: DecoMode | None = None
    dive: DiveState = field(default_factory=DiveState)
    ui_log: tuple[str, ...] = ()
    test_time_offset_sec: float = 0.0


@dataclass(frozen=True)
class DiveView:
    depth: int | None
    ls: Event | None
    profile: DiveProfile | None
    next_stop: ProfileStop | None
    travel_from_stop: ProfileStop | None
    travel_to_stop: ProfileStop | None
    at_stop: bool
    current_stop: ProfileStop | None
    at_o2_stop: bool
    awaiting_o2: bool
    waiting_at_o2_stop: bool
    on_o2_stop: bool
    off_o2_stop: bool
    traveling_on_o2: bool
    traveling_to_o2: bool
    can_break: bool
    stop_anchor: datetime | None
    air_break_remaining: float | None
    resume_o2_remaining: float | None
    air_break_due: float | None
    stop_remaining: float | None


FINAL_O2_AIR_BREAK_CUTOFF_SEC = 35 * 60


class DiveEngine:
    def __init__(self, now_provider=None, mode: DecoMode = DecoMode.AIR) -> None:
        self.state = EngineState(deco_mode=mode)
        self._now_provider = now_provider or datetime.now

    def _now(self) -> datetime:
        return self._now_provider() + timedelta(seconds=self.state.test_time_offset_sec)

    def dispatch(self, intent: Intent) -> None:
        now = self._now()
        self.state = rebuild_dive_profile_if_needed(apply_intent(self.state, intent, now), now)

    def snapshot(self) -> Snapshot:
        now = self._now()
        self.state = rebuild_dive_profile_if_needed(self.state, now)
        return create_snapshot(self.state, now)

    def recall_lines(self) -> tuple[str, ...]:
        return self.state.ui_log[-30:]

    def set_depth_text(self, raw: str) -> None:
        if raw == self.state.dive.depth_input_text:
            return
        self.state = replace(self.state, dive=replace(self.state.dive, depth_input_text=raw, profile=None, profile_signature=None))

    def advance_test_time(self, delta_seconds: float) -> None:
        self.state = replace(self.state, test_time_offset_sec=max(self.state.test_time_offset_sec + delta_seconds, 0.0))

    def reset_test_time(self) -> None:
        self.state = replace(self.state, test_time_offset_sec=0.0)

    def test_time_label(self) -> str:
        if abs(self.state.test_time_offset_sec) < 1e-9:
            return "Test Time: LIVE"
        total = int(abs(self.state.test_time_offset_sec))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"Test Time: +{hours}:{minutes:02d}:{seconds:02d}"
        return f"Test Time: +{minutes:02d}:{seconds:02d}"


class Engine:
    def __init__(self, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self._mode: DecoMode | None = None
        self._depth_input_text = ""
        self._stopwatch = StopwatchController(now_provider=self._now_provider)
        self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
        self._air_o2 = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR_O2)

    @property
    def state(self) -> EngineState:
        if self._mode is None:
            return EngineState(
                deco_mode=None,
                dive=DiveState(depth_input_text=self._depth_input_text),
                ui_log=(),
                test_time_offset_sec=self._stopwatch.test_time_offset_sec,
            )
        return self._active_dive().state

    def dispatch(self, intent: Intent) -> None:
        if intent is Intent.MODE:
            self._cycle_mode()
            return
        if self._mode is None:
            if intent is Intent.PRIMARY:
                self._stopwatch.dispatch_primary()
            elif intent is Intent.SECONDARY:
                self._stopwatch.dispatch_secondary()
            elif intent is Intent.RESET:
                self._stopwatch.reset()
            return
        self._active_dive().dispatch(intent)

    def snapshot(self) -> Snapshot:
        return self._stopwatch.snapshot() if self._mode is None else self._active_dive().snapshot()

    def recall_lines(self) -> tuple[str, ...]:
        return self._stopwatch.recall_lines() if self._mode is None else self._active_dive().recall_lines()

    def set_depth_text(self, raw: str) -> None:
        if raw == self._depth_input_text:
            return
        self._depth_input_text = raw
        self._air.set_depth_text(raw)
        self._air_o2.set_depth_text(raw)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._stopwatch.advance_test_time(delta_seconds)
        self._air.advance_test_time(delta_seconds)
        self._air_o2.advance_test_time(delta_seconds)

    def reset_test_time(self) -> None:
        self._stopwatch.reset_test_time()
        self._air.reset_test_time()
        self._air_o2.reset_test_time()

    def test_time_label(self) -> str:
        return self._stopwatch.test_time_label() if self._mode is None else self._active_dive().test_time_label()

    def _active_dive(self) -> DiveEngine:
        return self._air if self._mode is DecoMode.AIR else self._air_o2

    def _cycle_mode(self) -> None:
        current_offset = self._stopwatch.test_time_offset_sec
        self._mode = {None: DecoMode.AIR, DecoMode.AIR: DecoMode.AIR_O2, DecoMode.AIR_O2: None}[self._mode]
        if self._mode is DecoMode.AIR:
            self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
            self._air.set_depth_text(self._depth_input_text)
            self._air.state = replace(self._air.state, test_time_offset_sec=current_offset)
        elif self._mode is DecoMode.AIR_O2:
            self._air_o2 = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR_O2)
            self._air_o2.set_depth_text(self._depth_input_text)
            self._air_o2.state = replace(self._air_o2.state, test_time_offset_sec=current_offset)


def apply_intent(state: EngineState, intent: Intent, now: datetime) -> EngineState:
    if intent is Intent.RESET:
        return reset_current_mode(state)
    if intent is Intent.PRIMARY:
        return apply_primary_action(state, now)
    if intent is Intent.SECONDARY:
        return apply_secondary_action(state, now)
    return state


def apply_primary_action(state: EngineState, now: datetime) -> EngineState:
    if state.dive.phase is DivePhase.READY:
        return _record_event(state, now, code="LS", phase=DivePhase.DESCENT)

    if state.dive.phase is DivePhase.DESCENT:
        return _record_event(state, now, code="RB", phase=DivePhase.BOTTOM)

    if state.dive.phase is DivePhase.BOTTOM:
        if parse_depth_input(state.dive.depth_input_text) is None:
            return state
        return _record_event(state, now, code="LB", phase=DivePhase.TRAVEL, reset_travel=True)

    if state.dive.phase is DivePhase.TRAVEL:
        profile = state.dive.profile
        next_stop = None if profile is None or profile.is_no_decompression else next_stop_after(profile, state.dive.current_stop_index)
        if next_stop is None:
            return _record_event(state, now, code="RS", phase=DivePhase.SURFACE, clear_delay=True)
        return _record_event(state, now, code=f"R{next_stop.index}", phase=DivePhase.AT_STOP, current_stop_index=next_stop.index, clear_delay=True)

    if state.dive.phase is DivePhase.AT_STOP:
        view = _dive_view(state, now)
        if view.off_o2_stop:
            return _convert_current_o2_stop_to_air(state, now, view)
        if (stop := stop_by_index(state.dive.profile, state.dive.current_stop_index) if state.dive.profile is not None else None) is not None:
            return _record_event(state, now, code=f"L{stop.index}", phase=DivePhase.TRAVEL)
        return state

    return state


def apply_secondary_action(state: EngineState, now: datetime) -> EngineState:
    if state.dive.phase is DivePhase.DESCENT:
        active_hold = _active_descent_hold(state)
        if active_hold is None:
            index = 1 + sum(1 for event in state.dive.events if event.code.endswith("_START") and event.code.startswith("H"))
            return _record_event(state, now, code=f"H{index}_START", label=f"H{index} start")
        return _record_event(state, now, code=f"H{active_hold[0]}_END", label=f"H{active_hold[0]} end")

    if state.dive.phase is DivePhase.TRAVEL:
        return _toggle_delay(state, now)

    view = _dive_view(state, now)
    if not view.at_stop:
        return state

    if view.awaiting_o2:
        return _record_event(state, now, code="ON_O2", label="On O2", oxygen=replace(state.dive.oxygen, first_confirmed_at=now, segment_started_at=now))

    active_break = state.dive.oxygen.active_air_break
    if active_break is not None:
        elapsed = max((now - active_break).total_seconds(), 0.0)
        if elapsed < 300:
            return _record_event(state, now, code="", label=f"Complete break first ({format_mmss(300 - elapsed)})")
        return _record_event(state, now, code="AIR_BREAK_END", label="Back on O2", oxygen=replace(state.dive.oxygen, active_air_break=None, segment_started_at=now))

    if view.off_o2_stop:
        paused_sec = state.dive.oxygen.paused_stop_sec + max((now - state.dive.oxygen.off_o2_started_at).total_seconds(), 0.0)
        return _record_event(
            state,
            now,
            code="ON_O2",
            label="Back on O2",
            oxygen=replace(state.dive.oxygen, off_o2_started_at=None, paused_stop_sec=paused_sec, segment_started_at=now),
        )

    if view.on_o2_stop:
        return _record_event(
            state,
            now,
            code="OFF_O2",
            label="Off O2",
            oxygen=replace(state.dive.oxygen, off_o2_started_at=now, segment_started_at=None),
        )

    return state

def reset_current_mode(state: EngineState) -> EngineState:
    return replace(state, dive=DiveState())


def rebuild_dive_profile_if_needed(state: EngineState, now: datetime) -> EngineState:
    if state.deco_mode is None:
        return state

    depth = parse_depth_input(state.dive.depth_input_text)
    if depth is None or state.dive.phase in {DivePhase.READY, DivePhase.DESCENT}:
        return replace(state, dive=replace(state.dive, profile=None, profile_signature=None))

    ls = find_latest_event(state.dive.events, "LS")
    lb = find_latest_event(state.dive.events, "LB")
    signature = _profile_signature(state, now, depth=depth, ls=ls, lb=lb)
    if signature == state.dive.profile_signature:
        return state

    bottom_minutes = (
        max(math.ceil((now - ls.timestamp).total_seconds() / 60.0), 1)
        if state.dive.phase is DivePhase.BOTTOM and ls is not None
        else None
    )
    if state.dive.phase is DivePhase.BOTTOM:
        profile = build_profile(state.deco_mode, depth, bottom_minutes or 1)
    else:
        if ls is None or lb is None:
            return replace(state, dive=replace(state.dive, profile=None, profile_signature=signature))
        profile = build_profile(state.deco_mode, depth, max(math.ceil((lb.timestamp - ls.timestamp).total_seconds() / 60.0), 0))

    persisted_signature = _profile_signature(state, now, depth=depth, ls=ls, lb=lb, profile=profile)
    return replace(state, dive=replace(state.dive, profile=profile, profile_signature=persisted_signature))


def estimate_current_depth(state: EngineState, now: datetime) -> int | None:
    if state.dive.phase is DivePhase.DESCENT:
        ls = find_latest_event(state.dive.events, "LS")
        if ls is None:
            return None
        depth = parse_depth_input(state.dive.depth_input_text)
        estimate = int(_descent_progress_seconds(state, now, ls))
        return min(estimate, depth) if depth is not None else estimate
    depth = parse_depth_input(state.dive.depth_input_text)
    if depth is None:
        return None
    if state.dive.phase is not DivePhase.TRAVEL:
        return None
    profile = state.dive.profile
    if profile is None:
        return None
    anchor_event = _travel_anchor_event(state)
    anchor = anchor_event.timestamp if anchor_event is not None else None
    if anchor is None:
        return None
    elapsed_sec = _travel_progress_seconds(state, now, anchor)
    previous_stop = stop_by_index(profile, state.dive.current_stop_index) if state.dive.current_stop_index is not None else None
    start_depth = previous_stop.depth_fsw if previous_stop is not None else depth
    target = next_stop_after(profile, state.dive.current_stop_index)
    end_depth = target.depth_fsw if target is not None else 0
    traveled = elapsed_sec * 0.5
    if start_depth >= end_depth:
        return max(int(math.ceil(start_depth - traveled)), end_depth)
    return min(int(math.ceil(start_depth + traveled)), end_depth)


def _dive_view(state: EngineState, now: datetime) -> DiveView:
    profile = state.dive.profile
    travel_from_stop = stop_by_index(profile, state.dive.current_stop_index) if state.dive.phase is DivePhase.TRAVEL and profile is not None and state.dive.current_stop_index is not None else None
    travel_to_stop = next_stop_after(profile, state.dive.current_stop_index) if state.dive.phase is DivePhase.TRAVEL and profile is not None else None
    at_stop = state.dive.phase is DivePhase.AT_STOP and state.dive.current_stop_index is not None
    current_stop = stop_by_index(profile, state.dive.current_stop_index) if at_stop and profile is not None else None
    previous_stop = stop_by_index(profile, state.dive.current_stop_index - 1) if at_stop and profile is not None and state.dive.current_stop_index not in {None, 1} else None
    at_o2_stop = current_stop is not None and current_stop.gas == "o2"
    first_o2_stop = at_o2_stop and (previous_stop is None or previous_stop.gas != "o2")
    awaiting_o2 = at_o2_stop and state.dive.oxygen.first_confirmed_at is None
    active_break = state.dive.oxygen.active_air_break
    active_off_o2 = state.dive.oxygen.off_o2_started_at
    next_stop = next_stop_after(profile, state.dive.current_stop_index) if profile is not None else None
    arrival = find_latest_event(state.dive.events, f"R{state.dive.current_stop_index}") if at_stop else None
    prior_departure = (
        find_latest_event(state.dive.events, f"L{state.dive.current_stop_index - 1}")
        if at_stop and state.dive.current_stop_index not in {None, 1}
        else None
    )
    convert_to_air = find_latest_event(state.dive.events, f"CA{state.dive.current_stop_index}") if at_stop else None
    if arrival is None:
        stop_anchor = None
    elif first_o2_stop and awaiting_o2:
        stop_anchor = None
    elif convert_to_air is not None and current_stop is not None and current_stop.gas == "air":
        stop_anchor = convert_to_air.timestamp
    elif first_o2_stop and state.dive.oxygen.first_confirmed_at is not None:
        stop_anchor = state.dive.oxygen.first_confirmed_at
    elif prior_departure is not None:
        stop_anchor = prior_departure.timestamp
    else:
        stop_anchor = arrival.timestamp
    anchor_elapsed_sec = None if stop_anchor is None else max((now - stop_anchor).total_seconds(), 0.0)
    if anchor_elapsed_sec is not None and prior_departure is not None:
        anchor_elapsed_sec = max(anchor_elapsed_sec - state.dive.travel_delay_sec, 0.0)
    paused_stop_sec = state.dive.oxygen.paused_stop_sec
    if active_break is not None:
        paused_stop_sec += max((now - active_break).total_seconds(), 0.0)
    if active_off_o2 is not None:
        paused_stop_sec += max((now - active_off_o2).total_seconds(), 0.0)
    effective_elapsed_sec = None if anchor_elapsed_sec is None else max(anchor_elapsed_sec - paused_stop_sec, 0.0)
    stop_remaining = None if current_stop is None or effective_elapsed_sec is None else (current_stop.duration_min * 60) - effective_elapsed_sec
    continuous_o2_remaining = _continuous_o2_remaining(profile, state.dive.current_stop_index, current_stop, stop_remaining)
    air_break_required = _air_break_required(current_stop, continuous_o2_remaining)
    o2_exposure_anchor = state.dive.oxygen.segment_started_at if at_o2_stop else None
    traveling_on_air_due_to_delay = _traveling_on_air_due_to_o2_delay(state, now, travel_from_stop, travel_to_stop)
    waiting_at_o2_stop = at_o2_stop and awaiting_o2
    off_o2_stop = at_o2_stop and state.dive.oxygen.first_confirmed_at is not None and active_off_o2 is not None and active_break is None
    on_o2_stop = at_o2_stop and state.dive.oxygen.segment_started_at is not None and active_break is None and active_off_o2 is None
    traveling_on_o2 = (
        state.dive.phase is DivePhase.TRAVEL
        and travel_from_stop is not None
        and travel_from_stop.gas == "o2"
        and state.dive.oxygen.segment_started_at is not None
        and active_break is None
        and active_off_o2 is None
        and not traveling_on_air_due_to_delay
    )
    traveling_to_o2 = (
        state.dive.phase is DivePhase.TRAVEL
        and travel_to_stop is not None
        and travel_to_stop.gas == "o2"
        and state.dive.oxygen.segment_started_at is None
    )
    can_break = (
        at_o2_stop
        and air_break_required
        and not awaiting_o2
        and o2_exposure_anchor is not None
        and active_break is None
        and active_off_o2 is None
        and max((now - o2_exposure_anchor).total_seconds(), 0.0) >= 1800
    )
    air_break_remaining = max(300.0 - (now - active_break).total_seconds(), 0.0) if active_break is not None else None
    resume_o2_remaining = None if (active_break is None or current_stop is None or stop_anchor is None) else max((current_stop.duration_min * 60) - max((active_break - stop_anchor).total_seconds() - (state.dive.travel_delay_sec if prior_departure is not None else 0.0), 0.0), 0.0)
    air_break_due = None if (not at_o2_stop or not air_break_required or awaiting_o2 or active_break is not None or active_off_o2 is not None or o2_exposure_anchor is None) else max(1800.0 - (now - o2_exposure_anchor).total_seconds(), 0.0)
    return DiveView(
        depth=parse_depth_input(state.dive.depth_input_text),
        ls=find_latest_event(state.dive.events, "LS"),
        profile=profile,
        next_stop=next_stop,
        travel_from_stop=travel_from_stop,
        travel_to_stop=travel_to_stop,
        at_stop=at_stop,
        current_stop=current_stop,
        at_o2_stop=at_o2_stop,
        awaiting_o2=awaiting_o2,
        waiting_at_o2_stop=waiting_at_o2_stop,
        on_o2_stop=on_o2_stop,
        off_o2_stop=off_o2_stop,
        traveling_on_o2=traveling_on_o2,
        traveling_to_o2=traveling_to_o2,
        can_break=can_break,
        stop_anchor=stop_anchor,
        air_break_remaining=air_break_remaining,
        resume_o2_remaining=resume_o2_remaining,
        air_break_due=air_break_due,
        stop_remaining=stop_remaining,
    )


def _continuous_o2_remaining(
    profile: DiveProfile | None,
    current_stop_index: int | None,
    current_stop: ProfileStop | None,
    stop_remaining: float | None,
) -> float | None:
    if (
        profile is None
        or current_stop is None
        or current_stop_index is None
        or current_stop.gas != "o2"
        or stop_remaining is None
    ):
        return None
    remaining = max(stop_remaining, 0.0)
    next_index = current_stop_index + 1
    while True:
        next_stop = stop_by_index(profile, next_index)
        if next_stop is None or next_stop.gas != "o2":
            break
        remaining += next_stop.duration_min * 60
        next_index += 1
    return remaining


def _air_break_required(current_stop: ProfileStop | None, continuous_o2_remaining: float | None) -> bool:
    if current_stop is None or current_stop.gas != "o2":
        return False
    if continuous_o2_remaining is not None and continuous_o2_remaining <= FINAL_O2_AIR_BREAK_CUTOFF_SEC:
        return False
    return True


def _traveling_on_air_due_to_o2_delay(
    state: EngineState,
    now: datetime,
    travel_from_stop: ProfileStop | None,
    travel_to_stop: ProfileStop | None,
) -> bool:
    if (
        state.dive.phase is not DivePhase.TRAVEL
        or state.dive.active_delay is None
        or state.dive.oxygen.segment_started_at is None
        or travel_from_stop is None
        or travel_from_stop.gas != "o2"
    ):
        return False
    if travel_from_stop.depth_fsw == 30 and travel_to_stop is not None and travel_to_stop.gas == "o2" and travel_to_stop.depth_fsw == 20:
        limit_sec = 30 * 60
    elif travel_from_stop.depth_fsw == 20 and travel_to_stop is None:
        limit_sec = 30 * 60
    else:
        return False
    return max((now - state.dive.oxygen.segment_started_at).total_seconds(), 0.0) >= limit_sec

def parse_depth_input(text: str) -> int | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None

def find_latest_event(events: tuple[Event, ...], code_prefix: str) -> Event | None:
    for event in reversed(events):
        if event.code.startswith(code_prefix):
            return event
    return None


def _active_descent_hold(state: EngineState) -> tuple[int, datetime] | None:
    for event in reversed(state.dive.events):
        if not event.code.startswith("H"):
            continue
        if event.code.endswith("_END"):
            return None
        if event.code.endswith("_START"):
            return int(event.code[1:].split("_", 1)[0]), event.timestamp
    return None


def _descent_progress_seconds(state: EngineState, now: datetime, ls: Event | None = None) -> float:
    ls = find_latest_event(state.dive.events, "LS") if ls is None else ls
    if ls is None:
        return 0.0
    hold_elapsed_sec = 0.0
    hold_started_at: datetime | None = None
    for event in state.dive.events:
        if not event.code.startswith("H"):
            continue
        if event.code.endswith("_START"):
            hold_started_at = event.timestamp
        elif event.code.endswith("_END") and hold_started_at is not None:
            hold_elapsed_sec += max((event.timestamp - hold_started_at).total_seconds(), 0.0)
            hold_started_at = None
    if hold_started_at is not None:
        hold_elapsed_sec += max((now - hold_started_at).total_seconds(), 0.0)
    return max((now - ls.timestamp).total_seconds() - hold_elapsed_sec, 0.0)


def _travel_anchor_event(state: EngineState) -> Event | None:
    if state.dive.current_stop_index is None:
        return find_latest_event(state.dive.events, "LB")
    return find_latest_event(state.dive.events, f"L{state.dive.current_stop_index}")


def _travel_progress_seconds(state: EngineState, now: datetime, anchor: datetime) -> float:
    elapsed_sec = max((now - anchor).total_seconds(), 0.0)
    paused_sec = state.dive.travel_delay_sec
    if state.dive.phase is DivePhase.TRAVEL and state.dive.active_delay is not None:
        paused_sec += max((now - state.dive.active_delay.started_at).total_seconds(), 0.0)
    return max(elapsed_sec - paused_sec, 0.0)


def _profile_signature(
    state: EngineState,
    now: datetime,
    *,
    depth: int | None = None,
    ls: Event | None = None,
    lb: Event | None = None,
    profile: DiveProfile | None = None,
) -> tuple | None:
    depth = parse_depth_input(state.dive.depth_input_text) if depth is None else depth
    if depth is None:
        return None
    ls = find_latest_event(state.dive.events, "LS") if ls is None else ls
    lb = find_latest_event(state.dive.events, "LB") if lb is None else lb
    profile = state.dive.profile if profile is None else profile
    bottom_minutes = max(math.ceil((now - ls.timestamp).total_seconds() / 60.0), 1) if state.dive.phase is DivePhase.BOTTOM and ls is not None else None
    return (
        depth,
        ls.timestamp if ls is not None else None,
        lb.timestamp if lb is not None else None,
        bottom_minutes,
        _profile_fingerprint(profile),
    )


def _profile_fingerprint(profile: DiveProfile | None) -> tuple | None:
    if profile is None:
        return None
    return (
        profile.table_depth_fsw,
        profile.table_bottom_time_min,
        profile.time_to_first_stop_sec,
        tuple((stop.index, stop.depth_fsw, stop.duration_min, stop.gas) for stop in profile.stops),
        profile.repeat_group,
        profile.is_no_decompression,
    )


def format_mmss(seconds: float) -> str:
    total = max(int(math.ceil(seconds)), 0)
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_tenths(seconds: float) -> str:
    clamped = max(seconds, 0.0)
    total_tenths = math.floor((clamped * 10) + 1e-9)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"


def _record_event(
    state: EngineState,
    now: datetime,
    *,
    code: str,
    phase: DivePhase | None = None,
    label: str | None = None,
    current_stop_index: int | None = None,
    oxygen: OxygenState | None = None,
    clear_delay: bool = False,
    reset_travel: bool = False,
) -> EngineState:
    updated = state
    if code:
        updated = replace(state, dive=replace(state.dive, events=state.dive.events + (Event(code=code, timestamp=now),)))
    dive = updated.dive if phase is None else replace(updated.dive, phase=phase)
    if phase is DivePhase.TRAVEL:
        dive = replace(dive, travel_delay_sec=0.0)
    elif phase is not None and phase not in {DivePhase.TRAVEL, DivePhase.AT_STOP}:
        dive = replace(dive, travel_delay_sec=0.0)
    if current_stop_index is not None:
        dive = replace(dive, current_stop_index=current_stop_index)
    if oxygen is not None:
        dive = replace(dive, oxygen=oxygen)
    if clear_delay:
        dive = replace(dive, active_delay=None)
    if reset_travel:
        dive = replace(
            dive,
            current_stop_index=None,
            oxygen=OxygenState(),
            active_delay=None,
            travel_delay_sec=0.0,
        )
    logged = f"{(label or code)} {now.strftime('%H:%M:%S')}".strip()
    return replace(replace(updated, dive=dive), ui_log=updated.ui_log + ((logged,) if logged else ()))


def _convert_current_o2_stop_to_air(state: EngineState, now: datetime, view: DiveView) -> EngineState:
    if state.dive.profile is None or state.dive.current_stop_index is None or view.stop_remaining is None:
        return state
    before_profile = state.dive.profile
    result = convert_remaining_o2_to_air(
        before_profile,
        current_stop_index=state.dive.current_stop_index,
        remaining_o2_stop_sec=max(int(math.ceil(view.stop_remaining)), 0),
    )
    updated = _record_event(
        state,
        now,
        code=f"CA{state.dive.current_stop_index}",
        label="Convert to Air",
        current_stop_index=state.dive.current_stop_index,
        oxygen=OxygenState(),
    )
    signature = _profile_signature(updated, now, profile=result.profile)
    dive = replace(updated.dive, profile=result.profile, profile_signature=signature)
    ui_log = updated.ui_log + (
        (
            f"Converted remaining O2 at {result.source_stop_depth_fsw} fsw to "
            f"{result.converted_air_min} min air "
            f"{_profile_schedule_label(before_profile)} -> {_profile_schedule_label(result.profile)}"
        ),
    )
    return replace(updated, dive=dive, ui_log=ui_log)


def _toggle_delay(state: EngineState, now: datetime) -> EngineState:
    depth = estimate_current_depth(state, now)
    if depth is None:
        depth = parse_depth_input(state.dive.depth_input_text)
    if depth is None:
        return state
    if state.dive.active_delay is None:
        index = 1 + sum(1 for event in state.dive.events if event.code.endswith("_START") and event.code.startswith("D"))
        updated = _record_event(state, now, code=f"D{index}_START", label=f"Delay {index} start")
        return replace(updated, dive=replace(updated.dive, active_delay=DelayState(started_at=now, index=index, depth_fsw=depth, from_stop_index=state.dive.current_stop_index)))
    index = state.dive.active_delay.index
    updated = _record_event(
        state,
        now,
        code=f"D{index}_END",
        label=f"Delay {index} end",
    )
    delay_elapsed_sec = max((now - state.dive.active_delay.started_at).total_seconds(), 0.0)
    cleared = replace(
        updated,
        dive=replace(
            updated.dive,
            active_delay=None,
            travel_delay_sec=updated.dive.travel_delay_sec + delay_elapsed_sec if updated.dive.phase is DivePhase.TRAVEL else updated.dive.travel_delay_sec,
        ),
    )
    result = _apply_delay_result(cleared, now, state.dive.active_delay)
    return result


def _apply_delay_result(state: EngineState, now: datetime, delay: DelayState) -> EngineState:
    profile = state.dive.profile
    if profile is None or profile.is_no_decompression:
        return state

    delay_elapsed_sec = max(int((now - delay.started_at).total_seconds()), 0)
    o2_time_before_delay_sec = (
        max(int((delay.started_at - state.dive.oxygen.segment_started_at).total_seconds()), 0)
        if state.dive.oxygen.segment_started_at is not None
        else None
    )
    result = apply_delay(
        profile=profile,
        from_stop_index=delay.from_stop_index,
        delay_elapsed_sec=delay_elapsed_sec,
        delay_depth_fsw=delay.depth_fsw,
        o2_time_before_delay_sec=o2_time_before_delay_sec,
    )
    merged = _merge_delay_profile(
        state,
        now,
        profile,
        result,
        reset_stop_index=(result.outcome is DelayOutcome.RECOMPUTE and result.schedule_changed),
    )
    if result.air_interruption_min <= 0:
        return merged
    if result.outcome is DelayOutcome.O2_DELAY_CREDIT:
        return replace(
            merged,
            dive=replace(
                merged.dive,
                oxygen=replace(merged.dive.oxygen, segment_started_at=now, active_air_break=None),
            ),
            ui_log=merged.ui_log + (f"O2 delay interruption ({result.air_interruption_min}m air) ignored for O2 credit",),
        )
    if result.outcome is DelayOutcome.O2_SURFACE_DELAY:
        return replace(
            merged,
            dive=replace(
                merged.dive,
                oxygen=replace(merged.dive.oxygen, segment_started_at=now, active_air_break=None),
            ),
            ui_log=merged.ui_log + (f"20 fsw O2 departure delay interruption ({result.air_interruption_min}m air) ignored",),
        )
    return merged


def _merge_delay_profile(
    state: EngineState,
    now: datetime,
    before_profile: DiveProfile,
    result: DelayResult,
    *,
    reset_stop_index: bool = False,
) -> EngineState:
    profile = result.profile
    signature = _profile_signature(state, now, profile=profile)
    recompute = DelayRecomputeState(
        delay_min=result.delay_min,
        schedule_changed=result.schedule_changed,
        outcome=result.outcome,
        before_profile=before_profile,
        after_profile=profile,
        credited_o2_min=result.credited_o2_min,
        air_interruption_min=result.air_interruption_min,
    )
    updated = replace(
        state,
        dive=replace(
            state.dive,
            profile=profile,
            profile_signature=signature,
            current_stop_index=None if reset_stop_index else state.dive.current_stop_index,
            last_delay_recompute=recompute,
        ),
    )
    log_line = _delay_recompute_log_line(recompute)
    return updated if not log_line else replace(updated, ui_log=updated.ui_log + (log_line,))


def _delay_recompute_log_line(recompute: DelayRecomputeState) -> str:
    if recompute.outcome is DelayOutcome.EARLY_ARRIVAL:
        return "Early arrival, schedule unchanged"
    if recompute.outcome is DelayOutcome.O2_DELAY_CREDIT:
        before = _profile_schedule_label(recompute.before_profile)
        after = _profile_schedule_label(recompute.after_profile)
        base = (
            f"O2 delay credited (+{recompute.credited_o2_min}m) {before} -> {after}"
            if recompute.credited_o2_min > 0
            else f"O2 delay did not add O2 credit (+{recompute.delay_min}m delay)"
        )
        if recompute.air_interruption_min > 0:
            return f"{base}; {recompute.air_interruption_min}m on air ignored"
        return base
    if recompute.outcome is DelayOutcome.O2_SURFACE_DELAY:
        base = f"20 fsw departure delay ignored (+{recompute.delay_min}m)"
        if recompute.air_interruption_min > 0:
            return f"{base}; {recompute.air_interruption_min}m on air before surface"
        return base
    if recompute.outcome is DelayOutcome.IGNORE_DELAY:
        if recompute.delay_min > 0:
            return f"Delay (+{recompute.delay_min}m) did not change schedule"
        return "Delay <= 1m, schedule unchanged"
    if recompute.outcome is DelayOutcome.ADD_TO_FIRST_STOP:
        before = _profile_schedule_label(recompute.before_profile)
        after = _profile_schedule_label(recompute.after_profile)
        return f"First stop extended (+{recompute.delay_min}m) {before} -> {after}"
    if not recompute.schedule_changed:
        return f"Delay (+{recompute.delay_min}m), schedule unchanged"
    before = _profile_schedule_label(recompute.before_profile)
    after = _profile_schedule_label(recompute.after_profile)
    return f"Schedule updated (+{recompute.delay_min}m) {before} -> {after}"


def _profile_schedule_label(profile: DiveProfile) -> str:
    stops = ",".join(f"{stop.depth_fsw}/{stop.duration_min}" for stop in profile.stops) or "Surface"
    table_bottom = "--" if profile.table_bottom_time_min is None else str(profile.table_bottom_time_min)
    return f"{profile.table_depth_fsw}/{table_bottom} [{stops}]"
