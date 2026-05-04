from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TimerState:
    started_at: datetime
    carried_elapsed_sec: float = 0.0
    running: bool = True


def elapsed(timer: TimerState | None, now: datetime) -> float:
    if timer is None:
        return 0.0
    if not timer.running:
        return timer.carried_elapsed_sec
    return timer.carried_elapsed_sec + max((now - timer.started_at).total_seconds(), 0.0)


def pause(timer: TimerState, now: datetime) -> TimerState:
    return replace(timer, started_at=now, carried_elapsed_sec=elapsed(timer, now), running=False)


def resume(timer: TimerState, now: datetime) -> TimerState:
    return replace(timer, started_at=now, running=True)


def shift(timer: TimerState | None, *, seconds: float) -> TimerState | None:
    if timer is None:
        return None
    return replace(timer, started_at=timer.started_at + timedelta(seconds=seconds))


def remaining(timer: TimerState | None, now: datetime, *, target_sec: float) -> float | None:
    if timer is None:
        return None
    return max(target_sec - elapsed(timer, now), 0.0)
