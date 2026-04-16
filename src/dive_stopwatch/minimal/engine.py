from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum, auto
import math

from .profiles import (
    DecoMode,
    DelayResult,
    DiveProfile,
    ProfileStop,
    apply_between_stop_delay,
    apply_first_stop_delay,
    build_profile,
    next_stop_after,
    stop_by_index,
)
from .snapshot import Snapshot, create_snapshot


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
class StopwatchState:
    running: bool = False
    started_at: datetime | None = None
    elapsed_before_start_sec: float = 0.0
    lap_count: int = 0


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


@dataclass(frozen=True)
class OxygenState:
    first_confirmed_at: datetime | None = None
    segment_started_at: datetime | None = None
    active_air_break: datetime | None = None


@dataclass(frozen=True)
class DiveState:
    phase: DivePhase = DivePhase.READY
    depth_input_text: str = ""
    events: tuple[Event, ...] = ()
    profile: DiveProfile | None = None
    profile_signature: tuple | None = None
    current_stop_index: int | None = None
    active_delay: DelayState | None = None
    last_delay_recompute: DelayRecomputeState | None = None
    oxygen: OxygenState = field(default_factory=OxygenState)


@dataclass(frozen=True)
class EngineState:
    deco_mode: DecoMode | None = None
    stopwatch: StopwatchState = field(default_factory=StopwatchState)
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
    traveling_on_o2: bool
    traveling_to_o2: bool
    can_break: bool
    stop_anchor: datetime | None
    air_break_remaining: float | None
    resume_o2_remaining: float | None
    air_break_due: float | None
    stop_remaining: float | None


FINAL_O2_AIR_BREAK_CUTOFF_SEC = 35 * 60


class Engine:
    def __init__(self, now_provider=None) -> None:
        self.state = EngineState()
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


def apply_intent(state: EngineState, intent: Intent, now: datetime) -> EngineState:
    if intent is Intent.MODE:
        return cycle_mode(state)
    if intent is Intent.RESET:
        return reset_current_mode(state)
    if intent is Intent.PRIMARY:
        return apply_primary_action(state, now)
    if intent is Intent.SECONDARY:
        return apply_secondary_action(state, now)
    return state


def apply_primary_action(state: EngineState, now: datetime) -> EngineState:
    if state.deco_mode is None:
        stopwatch = state.stopwatch
        if stopwatch.running:
            elapsed = stopwatch.elapsed_before_start_sec + (now - stopwatch.started_at).total_seconds()
            return replace(state, stopwatch=replace(stopwatch, running=False, started_at=None, elapsed_before_start_sec=elapsed))
        return replace(state, stopwatch=replace(stopwatch, running=True, started_at=now))

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
        if (stop := stop_by_index(state.dive.profile, state.dive.current_stop_index) if state.dive.profile is not None else None) is not None:
            return _record_event(state, now, code=f"L{stop.index}", phase=DivePhase.TRAVEL)
        return state

    return state


def apply_secondary_action(state: EngineState, now: datetime) -> EngineState:
    if state.deco_mode is None:
        if state.stopwatch.running:
            elapsed = state.stopwatch.elapsed_before_start_sec + (now - state.stopwatch.started_at).total_seconds()
            lap_count = state.stopwatch.lap_count + 1
            return replace(state, stopwatch=replace(state.stopwatch, lap_count=lap_count), ui_log=state.ui_log + (f"Lap {lap_count} {format_tenths(elapsed)}",))
        return replace(state, stopwatch=StopwatchState())

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

    if view.can_break:
        return _record_event(state, now, code="AIR_BREAK_START", label="Air break start", oxygen=replace(state.dive.oxygen, active_air_break=now, segment_started_at=None))

    active_break = state.dive.oxygen.active_air_break
    if active_break is not None:
        elapsed = max((now - active_break).total_seconds(), 0.0)
        if elapsed < 300:
            return _record_event(state, now, code="", label=f"Complete break first ({format_mmss(300 - elapsed)})")
        return _record_event(state, now, code="AIR_BREAK_END", label="Back on O2", oxygen=replace(state.dive.oxygen, active_air_break=None, segment_started_at=now))

    return state


def cycle_mode(state: EngineState) -> EngineState:
    return replace(state, deco_mode={None: DecoMode.AIR, DecoMode.AIR: DecoMode.AIR_O2, DecoMode.AIR_O2: None}[state.deco_mode], dive=DiveState(depth_input_text=state.dive.depth_input_text))


def reset_current_mode(state: EngineState) -> EngineState:
    return replace(state, stopwatch=StopwatchState()) if state.deco_mode is None else replace(state, dive=DiveState())


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

    if state.dive.phase is DivePhase.BOTTOM:
        profile = build_profile(state.deco_mode, depth, signature[-1] or 1)
    else:
        if ls is None or lb is None:
            return replace(state, dive=replace(state.dive, profile=None, profile_signature=signature))
        profile = build_profile(state.deco_mode, depth, max(math.ceil((lb.timestamp - ls.timestamp).total_seconds() / 60.0), 0))

    return replace(state, dive=replace(state.dive, profile=profile, profile_signature=signature))


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
    elapsed_sec = max((now - anchor).total_seconds(), 0.0)
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
    next_stop = next_stop_after(profile, state.dive.current_stop_index) if profile is not None else None
    arrival = find_latest_event(state.dive.events, f"R{state.dive.current_stop_index}") if at_stop else None
    prior_departure = (
        find_latest_event(state.dive.events, f"L{state.dive.current_stop_index - 1}")
        if at_stop and state.dive.current_stop_index not in {None, 1}
        else None
    )
    if arrival is None:
        stop_anchor = None
    elif first_o2_stop and awaiting_o2:
        stop_anchor = None
    elif first_o2_stop and state.dive.oxygen.first_confirmed_at is not None:
        stop_anchor = state.dive.oxygen.first_confirmed_at
    elif prior_departure is not None:
        stop_anchor = prior_departure.timestamp
    else:
        stop_anchor = arrival.timestamp
    stop_remaining = None if current_stop is None or stop_anchor is None else (current_stop.duration_min * 60) - max((now - stop_anchor).total_seconds(), 0.0)
    air_break_required = _air_break_required(current_stop, stop_remaining)
    waiting_at_o2_stop = at_o2_stop and awaiting_o2
    on_o2_stop = at_o2_stop and state.dive.oxygen.segment_started_at is not None and active_break is None
    traveling_on_o2 = (
        state.dive.phase is DivePhase.TRAVEL
        and travel_from_stop is not None
        and travel_from_stop.gas == "o2"
        and state.dive.oxygen.segment_started_at is not None
        and active_break is None
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
        and state.dive.oxygen.segment_started_at is not None
        and active_break is None
        and max((now - state.dive.oxygen.segment_started_at).total_seconds(), 0.0) >= 1800
    )
    air_break_remaining = max(300.0 - (now - active_break).total_seconds(), 0.0) if active_break is not None else None
    resume_o2_remaining = None if (active_break is None or current_stop is None or stop_anchor is None) else max((current_stop.duration_min * 60) - max((active_break - stop_anchor).total_seconds(), 0.0), 0.0)
    air_break_due = None if (not at_o2_stop or not air_break_required or awaiting_o2 or active_break is not None or state.dive.oxygen.segment_started_at is None or next_stop is not None) else max(1800.0 - (now - state.dive.oxygen.segment_started_at).total_seconds(), 0.0)
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
        traveling_on_o2=traveling_on_o2,
        traveling_to_o2=traveling_to_o2,
        can_break=can_break,
        stop_anchor=stop_anchor,
        air_break_remaining=air_break_remaining,
        resume_o2_remaining=resume_o2_remaining,
        air_break_due=air_break_due,
        stop_remaining=stop_remaining,
    )


def _air_break_required(current_stop: ProfileStop | None, stop_remaining: float | None) -> bool:
    if current_stop is None or current_stop.gas != "o2":
        return False
    if current_stop.depth_fsw == 20 and stop_remaining is not None and stop_remaining <= FINAL_O2_AIR_BREAK_CUTOFF_SEC:
        return False
    return True

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


def _profile_signature(
    state: EngineState,
    now: datetime,
    *,
    depth: int | None = None,
    ls: Event | None = None,
    lb: Event | None = None,
) -> tuple | None:
    depth = parse_depth_input(state.dive.depth_input_text) if depth is None else depth
    if depth is None:
        return None
    ls = find_latest_event(state.dive.events, "LS") if ls is None else ls
    lb = find_latest_event(state.dive.events, "LB") if lb is None else lb
    bottom_minutes = max(math.ceil((now - ls.timestamp).total_seconds() / 60.0), 1) if state.dive.phase is DivePhase.BOTTOM and ls is not None else None
    return (depth, state.dive.phase, ls.timestamp if ls is not None else None, lb.timestamp if lb is not None else None, bottom_minutes)


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
        )
    logged = f"{(label or code)} {now.strftime('%H:%M:%S')}".strip()
    return replace(replace(updated, dive=dive), ui_log=updated.ui_log + ((logged,) if logged else ()))


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
    cleared = replace(updated, dive=replace(updated.dive, active_delay=None))
    result = _apply_delay_result(cleared, now, state.dive.active_delay)
    return result


def _apply_delay_result(state: EngineState, now: datetime, delay: DelayState) -> EngineState:
    profile = state.dive.profile
    if profile is None or profile.is_no_decompression:
        return state

    delay_elapsed_sec = max(int((now - delay.started_at).total_seconds()), 0)
    if delay.from_stop_index is None:
        planned = profile.time_to_first_stop_sec
        if planned is None:
            return state
        result = apply_first_stop_delay(
            profile=profile,
            actual_time_to_first_stop_sec=planned + delay_elapsed_sec,
            delay_depth_fsw=delay.depth_fsw,
        )
        return _merge_delay_profile(state, now, profile, result)

    next_stop = next_stop_after(profile, delay.from_stop_index)
    current_stop = stop_by_index(profile, delay.from_stop_index)
    if next_stop is None or current_stop is None:
        return state

    planned_elapsed_sec = int(abs(current_stop.depth_fsw - next_stop.depth_fsw) * 2)
    result = apply_between_stop_delay(
        profile=profile,
        actual_elapsed_sec=planned_elapsed_sec + delay_elapsed_sec,
        planned_elapsed_sec=planned_elapsed_sec,
        delay_depth_fsw=delay.depth_fsw,
    )
    return _merge_delay_profile(state, now, profile, result, reset_stop_index=result.schedule_changed)


def _merge_delay_profile(
    state: EngineState,
    now: datetime,
    before_profile: DiveProfile,
    result: DelayResult,
    *,
    reset_stop_index: bool = False,
) -> EngineState:
    signature = _profile_signature(state, now)
    profile = result.profile
    recompute = DelayRecomputeState(
        delay_min=result.delay_min,
        schedule_changed=result.schedule_changed,
        outcome=result.outcome,
        before_profile=before_profile,
        after_profile=profile,
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
    if not recompute.schedule_changed:
        return ""
    before = _profile_schedule_label(recompute.before_profile)
    after = _profile_schedule_label(recompute.after_profile)
    return f"Schedule updated (+{recompute.delay_min}m) {before} -> {after}"


def _profile_schedule_label(profile: DiveProfile) -> str:
    stops = ",".join(f"{stop.depth_fsw}/{stop.duration_min}" for stop in profile.stops) or "Surface"
    table_bottom = "--" if profile.table_bottom_time_min is None else str(profile.table_bottom_time_min)
    return f"{profile.table_depth_fsw}/{table_bottom} [{stops}]"
