"""EngineV2: central coordinator for button intents and runtime state.

Plain-English model:
- The GUI sends high-level intents (PRIMARY, SECONDARY, MODE, RESET).
- EngineV2 translates those intents into dive/stopwatch actions.
- Snapshot building is delegated to the kernel pipeline so rendering rules
  are separated from input handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from dive_stopwatch.v2.tables import (
    DecompressionMode,
    build_air_o2_oxygen_shift_plan,
)
from .decision_resolver import DecisionResolver
from .dive_controller import DiveController, DivePhase
from .facts import DiveFacts, FactsBuilder
from .models import AirBreakEventV2, IntentV2, ModeV2, SnapshotV2, StateV2
from .profile_helpers import next_stop_text
from .presenter import format_tenths
from .profile_resolver import ProfileResolver
from .runtime_context import RuntimeContextBuilder
from .snapshot_composer import SnapshotComposer
from .kernel_orchestrator import KernelOrchestrator


class EngineV2:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self.state = StateV2()
        # These collaborators isolate each concern:
        # facts -> profile lookup -> runtime flags -> decision -> snapshot fields.
        self._facts_builder = FactsBuilder()
        self._profile_resolver = ProfileResolver()
        self._runtime_context_builder = RuntimeContextBuilder()
        self._snapshot_composer = SnapshotComposer()
        self._decision_resolver = DecisionResolver()
        self._kernel_orchestrator = KernelOrchestrator(
            facts_builder=self._facts_builder,
            profile_resolver=self._profile_resolver,
            runtime_context_builder=self._runtime_context_builder,
            decision_resolver=self._decision_resolver,
            snapshot_composer=self._snapshot_composer,
        )
        self._now_provider = now_provider or datetime.now
        self._test_time_offset_seconds = 0.0

    def now(self) -> datetime:
        return self._now_provider() + timedelta(seconds=self._test_time_offset_seconds)

    def advance_test_time(self, delta_seconds: float) -> None:
        self._test_time_offset_seconds = max(self._test_time_offset_seconds + delta_seconds, 0.0)

    def reset_test_time(self) -> None:
        self._test_time_offset_seconds = 0.0

    def test_time_label(self) -> str:
        if abs(self._test_time_offset_seconds) < 1e-9:
            return "Test Time: LIVE"
        total = int(abs(self._test_time_offset_seconds))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"Test Time: +{hours}:{minutes:02d}:{seconds:02d}"
        return f"Test Time: +{minutes:02d}:{seconds:02d}"

    def set_depth_text(self, raw: str) -> None:
        self.state.depth_text = raw
        self._invalidate_runtime_caches()

    def dispatch(self, intent: IntentV2) -> None:
        # Intent routing: each physical button press maps to one intent.
        if intent is IntentV2.MODE:
            self._cycle_mode()
            return
        if intent is IntentV2.RESET:
            self._reset_current_mode()
            return
        if intent is IntentV2.PRIMARY:
            self._primary()
            return
        if intent is IntentV2.SECONDARY:
            self._secondary()
            return

    def snapshot(self) -> SnapshotV2:
        # Single read path used by the GUI refresh loop.
        return self._kernel_orchestrator.build_snapshot(
            self,
            state=self.state,
            now=self.now(),
        )

    def _cycle_mode(self) -> None:
        # Mode button cycles STOPWATCH -> DIVE/AIR -> DIVE/AIR_O2 -> STOPWATCH.
        self._invalidate_runtime_caches()
        if self.state.mode is ModeV2.STOPWATCH:
            self.state.mode = ModeV2.DIVE
            self._log("Mode -> DIVE")
            return
        if self.state.deco_mode is DecompressionMode.AIR:
            self.state.deco_mode = DecompressionMode.AIR_O2
            self._clear_dive_mode_sensitive_state()
            self._log("Deco -> AIR/O2")
            return
        self.state.mode = ModeV2.STOPWATCH
        self.state.deco_mode = DecompressionMode.AIR
        self._clear_dive_mode_sensitive_state()
        self._log("Mode -> STOPWATCH")

    def _reset_current_mode(self) -> None:
        self._invalidate_runtime_caches()
        if self.state.mode is ModeV2.STOPWATCH:
            self.state.stopwatch.reset()
            self._log("Stopwatch reset")
            return
        try:
            self.state.dive.reset()
        except RuntimeError:
            # Testing helper: allow reset from any active dive phase.
            self.state.dive = DiveController()
        self._clear_dive_mode_sensitive_state()
        self._log("Dive reset")

    def _primary(self) -> None:
        # Primary button is the "progress" button:
        # leave surface, reach bottom, leave bottom, reach/leave stops, reach surface.
        self._invalidate_runtime_caches()
        if self.state.mode is ModeV2.STOPWATCH:
            self.state.stopwatch.start_stop()
            self._log("Stopwatch start/stop")
            return

        now = self.now()
        dive = self.state.dive
        try:
            if dive.phase is DivePhase.ASCENT and dive._at_stop:
                result = dive.lap(now)
                event = result.get("event", "")
                if event == "L":
                    self._log(f"L{result['stop_number']} {result['clock']}")
                elif event:
                    self._log(f"{event}{result['stop_number']} {result['clock']}")
                return
            if dive.phase is DivePhase.ASCENT and not dive._at_stop and self._start_reaches_surface(now):
                result = dive.stop(now)
                self._log(f"RS {result['clock']}")
                return
            result = dive.start(now)
            event = result.get("event", "")
            if event == "R":
                self._log(f"R{result['stop_number']} {result['clock']}")
            elif event:
                self._log(f"{event} {result['clock']}")
            if event == "LB":
                self.state.first_o2_confirmed_at = None
                self.state.first_o2_confirmed_stop_number = None
                self.state.oxygen_segment_started_at = None
                self.state.air_break_events.clear()
        except RuntimeError as exc:
            self._log(str(exc))

    def _secondary(self) -> None:
        # Secondary button is the context button:
        # hold/delay/oxygen confirmations/air-break toggles depending on state.
        self._invalidate_runtime_caches()
        if self.state.mode is ModeV2.STOPWATCH:
            if self.state.stopwatch.running:
                mark = self.state.stopwatch.lap()
                self._log(f"LAP {mark.index}")
            else:
                self.state.stopwatch.reset()
                self._log("Stopwatch reset")
            return

        now = self.now()
        dive = self.state.dive
        profile = self._active_profile(now)
        try:
            if self._active_air_break() is not None:
                self._end_or_warn_air_break(now)
                return
            if self._can_start_air_break(profile):
                self._start_air_break(now, profile)
                return
            if self._awaiting_first_o2_confirmation(profile):
                latest = dive.latest_arrival_event()
                self.state.first_o2_confirmed_at = now
                self.state.first_o2_confirmed_stop_number = latest.stop_number if latest else None
                self.state.oxygen_segment_started_at = now
                self._log(f"On O2 {now.strftime('%H:%M:%S')}")
                return
            if dive.phase is DivePhase.ASCENT and not dive._at_stop:
                self._toggle_delay(now)
                return
            result = dive.lap(now)
            event = result.get("event", "")
            if event == "L":
                self._log(f"L{result['stop_number']} {result['clock']}")
            elif event:
                self._log(f"{event}{result['stop_number']} {result['clock']}")
        except RuntimeError as exc:
            self._log(str(exc))

    def _active_profile(self, now: datetime, *, facts: DiveFacts | None = None):
        # Profile lookup can fail for incomplete inputs; return None gracefully.
        if facts is None:
            facts = self._facts_builder.build(self.state, now=now)
        try:
            return self._profile_resolver.resolve(facts)
        except Exception:
            return None

    def _is_at_o2_stop(self, profile) -> bool:
        # In AIR/O2 mode, only 30 fsw and 20 fsw are oxygen-stop depths.
        if (
            self.state.mode is not ModeV2.DIVE
            or self.state.dive.phase is not DivePhase.ASCENT
            or not self.state.dive._at_stop
            or profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
        ):
            return False
        latest = self.state.dive.latest_arrival_event()
        if latest is None:
            return False
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        depth = self._stop_depth_for_number(stop_depths, latest.stop_number)
        return depth in {30, 20}

    def _awaiting_first_o2_confirmation(self, profile) -> bool:
        # First oxygen stop requires explicit "On O2" confirmation before
        # oxygen-timer logic starts.
        if (
            self.state.mode is not ModeV2.DIVE
            or self.state.dive.phase is not DivePhase.ASCENT
            or not self.state.dive._at_stop
            or profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
        ):
            return False
        latest = self.state.dive.latest_arrival_event()
        if latest is None:
            return False
        first_number = self._first_oxygen_stop_number(profile)
        if first_number is None or latest.stop_number != first_number:
            return False
        return self.state.first_o2_confirmed_at is None

    def _can_start_air_break(self, profile) -> bool:
        # Air breaks are only allowed at 20/30 stops once 30 min on O2 has elapsed.
        if (
            profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
            or self.state.mode is not ModeV2.DIVE
            or self.state.dive.phase is not DivePhase.ASCENT
            or not self.state.dive._at_stop
        ):
            return False
        if self._awaiting_first_o2_confirmation(profile):
            return False
        latest = self.state.dive.latest_arrival_event()
        if latest is None:
            return False
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest.stop_number)
        if current_depth not in {20, 30}:
            return False
        oxygen_elapsed = self._active_oxygen_elapsed()
        return oxygen_elapsed is not None and oxygen_elapsed >= 30 * 60

    def _active_o2_display_mode(self, profile) -> bool:
        # O2 display mode controls when summary text/countdowns should show
        # oxygen-related guidance instead of generic next-stop guidance.
        if (
            profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
            or self.state.mode is not ModeV2.DIVE
            or self.state.dive.phase is not DivePhase.ASCENT
            or self.state.oxygen_segment_started_at is None
            or self._active_air_break() is not None
        ):
            return False
        latest_arrival = self.state.dive.latest_arrival_event()
        latest_departure = self.state.dive.latest_stop_departure_event()
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        if self.state.dive._at_stop and latest_arrival is not None:
            depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            return depth in {20, 30}
        if latest_departure is None:
            return False
        departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        next_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number + 1)
        return departure_depth in {20, 30} and next_depth in {20, 0}

    def _start_air_break(self, now: datetime, profile) -> None:
        # Starting an air break pauses oxygen accumulation until the break ends.
        latest = self.state.dive.latest_arrival_event()
        if latest is None:
            return
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest.stop_number) or 0
        index = 1 + max((event.index for event in self.state.air_break_events), default=0)
        self.state.air_break_events.append(
            AirBreakEventV2(
                kind="start",
                index=index,
                timestamp=now,
                depth_fsw=current_depth,
                stop_number=latest.stop_number,
            )
        )
        self.state.oxygen_segment_started_at = None
        self._log(f"Air break start {now.strftime('%H:%M:%S')}")

    def _end_or_warn_air_break(self, now: datetime) -> None:
        # Break must run at least 5 minutes before "Back on O2" is allowed.
        active = self._active_air_break()
        if active is None:
            return
        elapsed = (now - active.timestamp).total_seconds()
        if elapsed < 300:
            left = 300 - elapsed
            self._log(f"Complete break first ({format_tenths(left)} left)")
            return
        self.state.air_break_events.append(
            AirBreakEventV2(
                kind="end",
                index=active.index,
                timestamp=now,
                depth_fsw=active.depth_fsw,
                stop_number=active.stop_number,
            )
        )
        self.state.oxygen_segment_started_at = now
        self._log(f"Back on O2 {now.strftime('%H:%M:%S')}")

    def _toggle_delay(self, now: datetime) -> None:
        # Delay markers are used during ascent travel (between stops).
        latest = self.state.dive.latest_ascent_delay_event()
        if latest is not None and latest.kind == "start":
            ended = self.state.dive.end_ascent_delay(now)
            if ended is not None:
                self._log(f"Delay {ended.index} end")
            return
        depth = self.state.parsed_depth()
        if depth is None:
            self._log("Enter max depth first")
            return
        event = self.state.dive.mark_ascent_delay_start(depth, now)
        self._log(f"Delay {event.index} start")

    def _active_air_break(self) -> AirBreakEventV2 | None:
        starts: dict[int, AirBreakEventV2] = {}
        ended: set[int] = set()
        for event in self.state.air_break_events:
            if event.kind == "start":
                starts[event.index] = event
            else:
                ended.add(event.index)
        open_indices = [idx for idx in starts.keys() if idx not in ended]
        if not open_indices:
            return None
        return starts[max(open_indices)]

    def _active_air_break_elapsed(self) -> float:
        active = self._active_air_break()
        if active is None:
            return 0.0
        return max((self.now() - active.timestamp).total_seconds(), 0.0)

    def _active_oxygen_elapsed(self) -> float | None:
        if self.state.oxygen_segment_started_at is None:
            return None
        if self._active_air_break() is not None:
            return None
        return max((self.now() - self.state.oxygen_segment_started_at).total_seconds(), 0.0)

    def _air_break_due_in_seconds(self) -> float | None:
        elapsed = self._active_oxygen_elapsed()
        if elapsed is None:
            return None
        return max((30 * 60) - elapsed, 0.0)

    def _start_reaches_surface(self, now: datetime) -> bool:
        # During ascent travel, PRIMARY means either "Reach Stop" or
        # "Reach Surface" depending on whether another stop remains.
        profile = self._active_profile(now)
        if profile is None or profile.section == "no_decompression":
            return True
        if self.state.dive._at_stop:
            return False
        latest_arrival = self.state.dive.latest_arrival_event()
        next_text = next_stop_text(
            profile,
            latest_arrival_stop_number=latest_arrival.stop_number if latest_arrival else None,
        )
        return next_text == "Surface"

    def _current_stop_anchor(self, profile) -> datetime | None:
        # Anchor = timestamp used as "time zero" for current stop timer.
        # It changes based on whether this is the first stop, a later stop,
        # or a first-oxygen-stop waiting for confirmation.
        if profile is None or not self.state.dive._at_stop:
            return None
        latest_arrival = self.state.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        first_o2 = self._first_oxygen_stop_number(profile)
        if profile.mode is DecompressionMode.AIR_O2 and latest_arrival.stop_number == first_o2:
            return self.state.first_o2_confirmed_at
        if latest_arrival.stop_number == 1:
            return latest_arrival.timestamp
        prev = next(
            (
                event
                for event in reversed(self.state.dive.ascent_stop_events)
                if event.kind == "leave" and event.stop_number == latest_arrival.stop_number - 1
            ),
            None,
        )
        return prev.timestamp if prev is not None else None

    def _first_oxygen_shift_anchor(self, profile) -> datetime | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2:
            return None
        shift = build_air_o2_oxygen_shift_plan(profile)
        if shift.first_oxygen_stop_depth_fsw is None:
            return None
        latest_arrival = self.state.dive.latest_arrival_event()
        if shift.travel_shift_vent_starts_on_arrival:
            return latest_arrival.timestamp if latest_arrival is not None else None
        latest_departure = self.state.dive.latest_stop_departure_event()
        if latest_departure is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        if departure_depth == shift.travel_shift_vent_start_depth_fsw:
            return latest_departure.timestamp
        return None

    def _show_tsv(self, profile) -> bool:
        # TSV display is used before first O2 confirmation to show travel-shift vent timing.
        if (
            self.state.mode is not ModeV2.DIVE
            or self.state.dive.phase is not DivePhase.ASCENT
            or profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
            or self.state.first_o2_confirmed_at is not None
        ):
            return False
        shift = build_air_o2_oxygen_shift_plan(profile)
        if self._first_oxygen_shift_anchor(profile) is None:
            return False
        if shift.travel_shift_vent_start_depth_fsw == 40:
            return True
        return self._awaiting_first_o2_confirmation(profile)

    def _first_oxygen_stop_number(self, profile) -> int | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2:
            return None
        shift = build_air_o2_oxygen_shift_plan(profile)
        if shift.first_oxygen_stop_depth_fsw is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        return stop_depths.index(shift.first_oxygen_stop_depth_fsw) + 1

    @staticmethod
    def _stop_depth_for_number(stop_depths: list[int], stop_number: int) -> int | None:
        index = stop_number - 1
        if 0 <= index < len(stop_depths):
            return stop_depths[index]
        return 0 if index == len(stop_depths) else None

    def _clear_dive_mode_sensitive_state(self) -> None:
        self.state.first_o2_confirmed_at = None
        self.state.first_o2_confirmed_stop_number = None
        self.state.oxygen_segment_started_at = None
        self.state.air_break_events.clear()

    def _invalidate_runtime_caches(self) -> None:
        self._kernel_orchestrator.invalidate()

    def _log(self, line: str) -> None:
        self.state.log_lines.append(line)
