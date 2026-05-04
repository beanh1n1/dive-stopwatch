from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Protocol

from dive_stopwatch.core import Engine, Intent
from dive_stopwatch.core.air_o2_profiles import DecoMode
from dive_stopwatch.core.air_o2_snapshot import Snapshot
from dive_stopwatch.core.redesign import (
    intent_to_operator_action,
    RedesignRuntime,
)


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "engine_golden_paths.json"
SNAPSHOT_FIELD_NAMES = tuple(field.name for field in fields(Snapshot))


@dataclass(frozen=True)
class GoldenExpectation:
    snapshot: dict[str, object]
    state_phase: str | None
    recall_contains: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenExpectation":
        return cls(
            snapshot=dict(data.get("snapshot", {})),
            state_phase=data.get("state_phase"),
            recall_contains=tuple(data.get("recall_contains", ())),
        )


@dataclass(frozen=True)
class GoldenStep:
    advance_sec: int
    intent: str | None
    expect: GoldenExpectation | None

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenStep":
        expect_data = data.get("expect")
        return cls(
            advance_sec=int(data.get("advance_sec", 0)),
            intent=data.get("intent"),
            expect=None if expect_data is None else GoldenExpectation.from_dict(expect_data),
        )


@dataclass(frozen=True)
class GoldenFixture:
    fixture_id: str
    mode: str
    depth_text: str | None
    start_time: datetime
    steps: tuple[GoldenStep, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenFixture":
        return cls(
            fixture_id=data["id"],
            mode=data["mode"],
            depth_text=data.get("depth_text"),
            start_time=datetime.fromisoformat(data["start_time"]),
            steps=tuple(GoldenStep.from_dict(step) for step in data["steps"]),
        )


def load_golden_fixtures(path: Path = FIXTURES_PATH) -> tuple[GoldenFixture, ...]:
    raw = json.loads(path.read_text())
    return tuple(GoldenFixture.from_dict(item) for item in raw)


class EngineAdapter(Protocol):
    def advance_time(self, delta_seconds: int) -> None: ...

    def dispatch(self, intent_name: str) -> None: ...

    def snapshot_dict(self) -> dict[str, object]: ...

    def snapshot_field(self, field: str) -> object: ...

    def recall_lines(self) -> tuple[str, ...]: ...

    def state_phase_name(self) -> str | None: ...


class LegacyEngineAdapter:
    def __init__(self, fixture: GoldenFixture) -> None:
        self._current = {"now": fixture.start_time}
        self._engine = Engine(now_provider=lambda: self._current["now"])
        if fixture.depth_text:
            self._engine.set_depth_text(fixture.depth_text)
        self._select_mode(fixture.mode)

    def advance_time(self, delta_seconds: int) -> None:
        self._current["now"] += timedelta(seconds=delta_seconds)

    def dispatch(self, intent_name: str) -> None:
        self._engine.dispatch(getattr(Intent, intent_name))

    def snapshot_dict(self) -> dict[str, object]:
        snapshot = self._engine.snapshot()
        return {field: getattr(snapshot, field) for field in SNAPSHOT_FIELD_NAMES}

    def snapshot_field(self, field: str) -> object:
        return getattr(self._engine.snapshot(), field)

    def recall_lines(self) -> tuple[str, ...]:
        return self._engine.recall_lines()

    def state_phase_name(self) -> str | None:
        dive_state = getattr(self._engine.state, "dive", None)
        if dive_state is None:
            return None
        phase = getattr(dive_state, "phase", None)
        return None if phase is None else phase.name

    def _select_mode(self, mode_text: str) -> None:
        cycles = {
            "STOPWATCH": 0,
            "AIR": 1,
            "AIR/O2": 2,
            "SURD": 3,
        }[mode_text]
        for _ in range(cycles):
            self._engine.dispatch(Intent.MODE)


class RedesignEngineAdapter:
    def __init__(self, fixture: GoldenFixture) -> None:
        mode = {"AIR": DecoMode.AIR, "AIR/O2": DecoMode.AIR_O2, "SURD": DecoMode.SURD}.get(fixture.mode)
        self._current = fixture.start_time
        if mode is None:
            raise ValueError(f"Redesign engine adapter does not support mode {fixture.mode}")
        self._engine = RedesignRuntime(mode=mode, now_provider=self._now)
        if fixture.depth_text:
            self._engine.set_depth_text(fixture.depth_text)

    def _now(self) -> datetime:
        return self._current

    def advance_time(self, delta_seconds: int) -> None:
        self._current += timedelta(seconds=delta_seconds)

    def dispatch(self, intent_name: str) -> None:
        action = intent_to_operator_action(getattr(Intent, intent_name), self._engine.state_view)
        if action is None:
            raise AssertionError(f"Unsupported redesign intent {intent_name} in phase {self._engine.state_view.phase_name}")
        self._engine.dispatch(action)

    def snapshot_dict(self) -> dict[str, object]:
        snapshot = self._engine.snapshot()
        return {field: getattr(snapshot, field) for field in SNAPSHOT_FIELD_NAMES}

    def snapshot_field(self, field: str) -> object:
        return getattr(self._engine.snapshot(), field)

    def recall_lines(self) -> tuple[str, ...]:
        return self._engine.recall_lines()

    def state_phase_name(self) -> str | None:
        phase_name = self._engine.state_view.phase_name
        return {
            "TRAVEL_TO_FIRST_STOP": "TRAVEL",
            "TRAVEL_TO_SURFACE": "TRAVEL",
            "AT_AIR_STOP": "AT_STOP",
            "SURFACE_CLEAN_TIME": "SURFACE",
            "SURFACE_COMPLETE": "SURFACE",
            "AT_O2_STOP_WAITING": "AT_STOP",
            "AT_O2_STOP_ON_O2": "AT_STOP",
            "AT_O2_STOP_OFF_O2": "AT_STOP",
            "AT_O2_STOP_AIR_BREAK": "AT_STOP",
        }.get(phase_name, phase_name)


@dataclass(frozen=True)
class CheckpointObservation:
    step_index: int
    snapshot: dict[str, object]
    state_phase: str | None
    recall_lines: tuple[str, ...]


def run_fixture(adapter: EngineAdapter, fixture: GoldenFixture) -> tuple[CheckpointObservation, ...]:
    checkpoints: list[CheckpointObservation] = []
    for step_index, step in enumerate(fixture.steps, start=1):
        adapter.advance_time(step.advance_sec)

        if step.intent is not None:
            adapter.dispatch(step.intent)

        if step.expect is not None:
            checkpoints.append(
                CheckpointObservation(
                    step_index=step_index,
                    snapshot=adapter.snapshot_dict(),
                    state_phase=adapter.state_phase_name(),
                    recall_lines=adapter.recall_lines(),
                )
            )
    return tuple(checkpoints)
