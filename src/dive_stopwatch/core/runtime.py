from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .air_o2_engine import DiveEngine, DiveState, EngineState, Intent
from .air_o2_profiles import DecoMode
from .air_o2_snapshot import Snapshot
from .stopwatch import StopwatchController
from .surd_runtime import SurdRuntime


class Engine:
    def __init__(self, now_provider=None) -> None:
        self._now_provider = now_provider or datetime.now
        self._mode: DecoMode | None = None
        self._depth_input_text = ""
        self._stopwatch = StopwatchController(now_provider=self._now_provider)
        self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
        self._air_o2 = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR_O2)
        self._surd = SurdRuntime(now_provider=self._now_provider)

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
        self._surd.set_depth_text(raw)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._stopwatch.advance_test_time(delta_seconds)
        self._air.advance_test_time(delta_seconds)
        self._air_o2.advance_test_time(delta_seconds)
        self._surd.advance_test_time(delta_seconds)

    def reset_test_time(self) -> None:
        self._stopwatch.reset_test_time()
        self._air.reset_test_time()
        self._air_o2.reset_test_time()
        self._surd.reset_test_time()

    def test_time_label(self) -> str:
        return self._stopwatch.test_time_label() if self._mode is None else self._active_dive().test_time_label()

    def _active_dive(self):
        if self._mode is DecoMode.AIR:
            return self._air
        if self._mode is DecoMode.AIR_O2:
            return self._air_o2
        return self._surd

    def _cycle_mode(self) -> None:
        current_offset = self._stopwatch.test_time_offset_sec
        self._mode = {None: DecoMode.AIR, DecoMode.AIR: DecoMode.AIR_O2, DecoMode.AIR_O2: DecoMode.SURD, DecoMode.SURD: None}[self._mode]
        if self._mode is DecoMode.AIR:
            self._air = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR)
            self._air.set_depth_text(self._depth_input_text)
            self._air.state = replace(self._air.state, test_time_offset_sec=current_offset)
        elif self._mode is DecoMode.AIR_O2:
            self._air_o2 = DiveEngine(now_provider=self._now_provider, mode=DecoMode.AIR_O2)
            self._air_o2.set_depth_text(self._depth_input_text)
            self._air_o2.state = replace(self._air_o2.state, test_time_offset_sec=current_offset)
        elif self._mode is DecoMode.SURD:
            self._surd = SurdRuntime(now_provider=self._now_provider)
            self._surd.set_depth_text(self._depth_input_text)
            self._surd.advance_test_time(current_offset)
