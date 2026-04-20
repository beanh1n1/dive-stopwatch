from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .snapshot import Snapshot


@dataclass(frozen=True)
class StopwatchMark:
    index: int
    lap_elapsed_sec: float
    split_elapsed_sec: float


@dataclass(frozen=True)
class StopwatchState:
    running: bool = False
    started_at: datetime | None = None
    elapsed_before_start_sec: float = 0.0
    marks: tuple[StopwatchMark, ...] = field(default_factory=tuple)


class StopwatchRuntime:
    @staticmethod
    def latest_mark(state: StopwatchState) -> StopwatchMark | None:
        return state.marks[-1] if state.marks else None

    @staticmethod
    def previous_mark(state: StopwatchState) -> StopwatchMark | None:
        return state.marks[-2] if len(state.marks) >= 2 else None

    @staticmethod
    def elapsed_seconds(state: StopwatchState, now: datetime) -> float:
        if state.running and state.started_at is not None:
            return state.elapsed_before_start_sec + max((now - state.started_at).total_seconds(), 0.0)
        return state.elapsed_before_start_sec

    @staticmethod
    def has_memory(state: StopwatchState, now: datetime) -> bool:
        return bool(state.marks) or StopwatchRuntime.elapsed_seconds(state, now) > 0.0

    @staticmethod
    def apply_primary(state: StopwatchState, now: datetime) -> StopwatchState:
        if state.running:
            return replace(
                state,
                running=False,
                started_at=None,
                elapsed_before_start_sec=StopwatchRuntime.elapsed_seconds(state, now),
            )
        return replace(state, running=True, started_at=now)

    @staticmethod
    def apply_secondary(state: StopwatchState, now: datetime) -> StopwatchState:
        if state.running:
            split_elapsed_sec = StopwatchRuntime.elapsed_seconds(state, now)
            prior_split_sec = state.marks[-1].split_elapsed_sec if state.marks else 0.0
            mark = StopwatchMark(
                index=len(state.marks) + 1,
                lap_elapsed_sec=max(split_elapsed_sec - prior_split_sec, 0.0),
                split_elapsed_sec=split_elapsed_sec,
            )
            return replace(state, marks=state.marks + (mark,))
        return StopwatchState()

    @staticmethod
    def snapshot_fields(
        state: StopwatchState, now: datetime, format_tenths
    ) -> tuple[str, str, str, tuple[str, str, bool, bool]]:
        elapsed_sec = StopwatchRuntime.elapsed_seconds(state, now)
        if state.running:
            status_text = "RUNNING"
        elif elapsed_sec > 0.0 or state.marks:
            status_text = "STOPPED"
        else:
            status_text = "READY"

        button_fields = (
            "Start/Stop",
            "Lap/Split",
            True,
            state.running,
        )
        return status_text, format_tenths(elapsed_sec), "", button_fields

    @staticmethod
    def recall_lines(state: StopwatchState, now: datetime, format_tenths) -> tuple[str, ...]:
        if not StopwatchRuntime.has_memory(state, now):
            return ()

        lines = [f"Total   {format_tenths(StopwatchRuntime.elapsed_seconds(state, now))}"]
        for mark in state.marks:
            lines.append(
                f"L{mark.index:<2}  Lap {format_tenths(mark.lap_elapsed_sec)}"
                f"  Split {format_tenths(mark.split_elapsed_sec)}"
            )
        return tuple(lines)


class StopwatchController:
    def __init__(self, now_provider=None) -> None:
        self.state = StopwatchState()
        self._now_provider = now_provider or datetime.now
        self.test_time_offset_sec = 0.0

    def _now(self) -> datetime:
        return self._now_provider() + _seconds(self.test_time_offset_sec)

    def dispatch_primary(self) -> None:
        self.state = StopwatchRuntime.apply_primary(self.state, self._now())

    def dispatch_secondary(self) -> None:
        self.state = StopwatchRuntime.apply_secondary(self.state, self._now())

    def reset(self) -> None:
        self.state = StopwatchState()

    def snapshot(self) -> "Snapshot":
        from .snapshot import Snapshot

        now = self._now()
        status_text, primary_text, detail_text, button_fields = StopwatchRuntime.snapshot_fields(
            self.state, now, _format_tenths
        )
        latest_mark = StopwatchRuntime.latest_mark(self.state)
        previous_mark = StopwatchRuntime.previous_mark(self.state)
        primary_label, secondary_label, primary_enabled, secondary_enabled = button_fields
        status_value_text = status_text.title()
        return Snapshot(
            mode_text="STOPWATCH",
            profile_schedule_text="",
            status_text=status_text,
            status_value_text=status_value_text,
            status_value_kind="default",
            primary_text=primary_text,
            primary_value_text=primary_text,
            primary_value_kind="default",
            depth_text=f"Lap {_format_mmss(latest_mark.lap_elapsed_sec)}" if latest_mark is not None else "",
            depth_timer_text=f"Split {_format_mmss(latest_mark.split_elapsed_sec)}" if latest_mark is not None else "",
            depth_timer_kind="default",
            remaining_text=(
                f"Prev Lap {_format_mmss(previous_mark.lap_elapsed_sec)} | Split {_format_mmss(previous_mark.split_elapsed_sec)}"
                if previous_mark is not None
                else ""
            ),
            summary_text="",
            summary_value_kind="default",
            detail_text=detail_text,
            primary_button_label=primary_label,
            secondary_button_label=secondary_label,
            primary_button_enabled=primary_enabled,
            secondary_button_enabled=secondary_enabled,
        )

    def recall_lines(self) -> tuple[str, ...]:
        return StopwatchRuntime.recall_lines(self.state, self._now(), _format_tenths)

    def advance_test_time(self, delta_seconds: float) -> None:
        self.test_time_offset_sec = max(self.test_time_offset_sec + delta_seconds, 0.0)

    def reset_test_time(self) -> None:
        self.test_time_offset_sec = 0.0

    def test_time_label(self) -> str:
        if abs(self.test_time_offset_sec) < 1e-9:
            return "Test Time: LIVE"
        total = int(abs(self.test_time_offset_sec))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"Test Time: +{hours}:{minutes:02d}:{seconds:02d}"
        return f"Test Time: +{minutes:02d}:{seconds:02d}"


def _format_tenths(total_seconds: float) -> str:
    total_tenths = max(int(round(total_seconds * 10)), 0)
    total_seconds, tenths = divmod(total_tenths, 10)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{tenths}"
    return f"{minutes:02d}:{seconds:02d}.{tenths}"


def _format_mmss(total_seconds: float) -> str:
    total_seconds = max(int(total_seconds), 0)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _seconds(value: float):
    from datetime import timedelta

    return timedelta(seconds=value)
