from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Callable

from dive_stopwatch.tables import (
    DecompressionMode,
    build_air_o2_oxygen_shift_plan,
    build_basic_decompression_profile,
    build_basic_decompression_profile_for_session,
)
from .depth_estimation import descent_hold_depth_for_display, estimate_current_depth
from .dive_controller import DiveController, DivePhase
from .dive_session import format_minutes_seconds
from .models import AirBreakEventV2, IntentV2, ModeV2, SnapshotV2, StateV2
from .profile_helpers import next_stop_instruction, next_stop_text
from .presenter import build_snapshot, format_tenths, status_from_state, stopwatch_primary_text


class EngineV2:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self.state = StateV2()
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

    def dispatch(self, intent: IntentV2) -> None:
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
        now = self.now()
        profile = self._active_profile(now)
        at_o2_stop = self._is_at_o2_stop(profile)
        status = status_from_state(self.state, now=now, at_o2_stop=at_o2_stop)
        timer_kind = self._timer_kind(profile)
        summary_text = self._summary_text(profile)
        start_label, secondary_label, start_enabled, secondary_enabled = self._button_labels(
            status,
            profile=profile,
            now=now,
        )
        return build_snapshot(
            state=self.state,
            now=now,
            status=status,
            timer_kind=timer_kind,
            primary_text=self._primary_text(now, profile),
            depth_text=self._depth_text(now, profile),
            remaining_text=self._remaining_text(now, profile),
            summary_text=summary_text,
            summary_targets_oxygen_stop=self._summary_targets_oxygen_stop(summary_text),
            detail_text=self._detail_text(profile),
            start_label=start_label,
            secondary_label=secondary_label,
            start_enabled=start_enabled,
            secondary_enabled=secondary_enabled,
        )

    def _remaining_text(self, now: datetime, profile) -> str:
        if self.state.mode is not ModeV2.DIVE:
            return ""

        dive = self.state.dive
        if self._active_air_break() is not None:
            left = max(300.0 - self._active_air_break_elapsed(), 0.0)
            return f"Air Break: {format_minutes_seconds(left)} left"

        if dive.phase is DivePhase.BOTTOM:
            ls = dive.session.events.get("LS")
            if ls is None or profile is None or profile.table_bottom_time_min is None:
                return ""
            elapsed = max((now - ls.timestamp).total_seconds(), 0.0)
            left = max((profile.table_bottom_time_min * 60) - elapsed, 0.0)
            return f"Bottom: {format_minutes_seconds(left)} left"

        if dive.phase is DivePhase.ASCENT and dive._at_stop and profile is not None:
            latest = dive.latest_arrival_event()
            if latest is None:
                return ""
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = self._stop_depth_for_number(stop_depths, latest.stop_number)
            required_min = profile.stops_fsw.get(current_depth) if current_depth is not None else None
            anchor = self._current_stop_anchor(profile)
            if required_min is None or anchor is None:
                return ""
            remaining = (required_min * 60) - max((now - anchor).total_seconds(), 0.0)
            if remaining >= 0:
                return f"Stop: {format_minutes_seconds(remaining)} left"
            return f"Stop: +{format_minutes_seconds(abs(remaining))}"

        return ""

    def _cycle_mode(self) -> None:
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

    def _active_profile(self, now: datetime):
        depth = self.state.parsed_depth()
        if depth is None:
            return None
        try:
            if self.state.dive.phase is DivePhase.BOTTOM:
                ls = self.state.dive.session.events.get("LS")
                if ls is None:
                    return None
                minutes = math.ceil((now - ls.timestamp).total_seconds() / 60.0)
                return build_basic_decompression_profile(self.state.deco_mode, depth, minutes)
            if self.state.dive.session.events.get("LB") is None:
                return None
            return build_basic_decompression_profile_for_session(
                self.state.deco_mode,
                depth,
                self.state.dive.session,
            )
        except Exception:
            return None

    def _is_at_o2_stop(self, profile) -> bool:
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

    def _summary_text(self, profile) -> str:
        if self.state.mode is ModeV2.STOPWATCH:
            return ""
        if self.state.dive.phase is DivePhase.CLEAN_TIME:
            return "Next: Surface"
        if profile is None:
            return "Next: --"
        if profile.section == "no_decompression":
            return "Next: Surface"
        if self.state.dive.phase is DivePhase.ASCENT:
            if self._active_air_break() is not None:
                left = max(300.0 - self._active_air_break_elapsed(), 0.0)
                return f"Next: Back on O2 in {format_minutes_seconds(left)}"
            if self._can_start_air_break(profile):
                return "Next: 5 min Air break in 00:00"
            if self._active_o2_display_mode(profile):
                seconds = self._air_break_due_in_seconds()
                if seconds is not None:
                    return f"Next: 5 min Air break in {format_minutes_seconds(seconds)}"
        latest = self.state.dive.latest_arrival_event()
        return next_stop_instruction(
            profile,
            latest_arrival_stop_number=latest.stop_number if latest else None,
        )

    def _detail_text(self, profile) -> str:
        if self.state.mode is not ModeV2.DIVE:
            return ""
        dive = self.state.dive
        latest_hold = dive.latest_stop_event()
        if (
            dive.phase is DivePhase.DESCENT
            and dive._awaiting_leave_stop
            and latest_hold is not None
            and latest_hold.kind == "start"
        ):
            depth = descent_hold_depth_for_display(
                controller=dive,
                start_time=latest_hold.timestamp,
                max_depth_fsw=self.state.parsed_depth(),
            )
            depth_text = f" ({depth} fsw)" if depth is not None else ""
            elapsed = (self.now() - latest_hold.timestamp).total_seconds()
            return f"H{latest_hold.index}{depth_text}   {format_minutes_seconds(elapsed)}"
        latest_delay = self.state.dive.latest_ascent_delay_event()
        if latest_delay is not None and latest_delay.kind == "start":
            elapsed = (self.now() - latest_delay.timestamp).total_seconds()
            depth_text = f" ({latest_delay.depth_fsw} fsw)" if latest_delay.depth_fsw is not None else ""
            return f"D{latest_delay.index}{depth_text}   {format_minutes_seconds(elapsed)}"
        if self._active_air_break() is not None:
            elapsed = self._active_air_break_elapsed()
            return f"Air Break {format_tenths(elapsed)}"
        return ""

    def _timer_kind(self, profile) -> str:
        if self.state.mode is ModeV2.STOPWATCH:
            return "STOPWATCH"
        dive = self.state.dive
        if dive.phase is DivePhase.READY:
            return "READY_ZERO"
        if dive.phase is DivePhase.DESCENT:
            return "DESCENT_HOLD" if dive._awaiting_leave_stop else "DESCENT_TOTAL"
        if dive.phase is DivePhase.BOTTOM:
            return "BOTTOM_ELAPSED" if profile is not None and profile.section != "no_decompression" else "BOTTOM_NO_DECO_REMAINING"
        if dive.phase is DivePhase.ASCENT:
            if dive._at_stop:
                if self._active_air_break() is not None:
                    return "AIR_BREAK"
                if self._awaiting_first_o2_confirmation(profile):
                    return "TSV"
                return "STOP_TIMER"
            if self._show_tsv(profile):
                return "TSV"
            return "ASCENT_TRAVEL"
        if dive.phase is DivePhase.CLEAN_TIME:
            return "CLEAN_TIME"
        return "READY_ZERO"

    @staticmethod
    def _summary_targets_oxygen_stop(summary_text: str) -> bool:
        return summary_text.startswith("Next: 20 fsw for ") or summary_text.startswith("Next: 30 fsw for ")

    def _button_labels(self, status, *, profile, now: datetime) -> tuple[str, str, bool, bool]:
        if self.state.mode is ModeV2.STOPWATCH:
            return ("Start/Stop", "Lap/Reset", True, True)

        dive = self.state.dive
        if status.name == "READY":
            return ("Leave Surface", "", True, False)
        if status.name == "DESCENT":
            return ("Reach Bottom", "Hold", True, True)
        if status.name == "BOTTOM":
            bottom_is_deco = profile is not None and profile.section != "no_decompression"
            return ("Leave Bottom", "Delay" if bottom_is_deco else "", True, bottom_is_deco)
        if status.name in {"AT_STOP", "AT_O2_STOP"}:
            if self._awaiting_first_o2_confirmation(profile):
                return ("Leave Stop", "On O2", True, True)
            if self._active_air_break() is not None:
                return ("Leave Stop", "On O2", True, True)
            if self._active_o2_display_mode(profile) or self._can_start_air_break(profile):
                return ("Leave Stop", "Off O2", True, True)
            return ("Leave Stop", "", True, False)
        if status.name == "SURFACE":
            return ("", "Reset", False, True)

        reaches_surface = self._start_reaches_surface(now)
        latest_delay = dive.latest_ascent_delay_event()
        has_active_delay = latest_delay is not None and latest_delay.kind == "start"
        can_flag_delay = (
            dive.phase is DivePhase.ASCENT
            and not dive._at_stop
            and profile is not None
        )
        return (
            "Reach Surface" if reaches_surface else "Reach Stop",
            "Stop Delay" if has_active_delay else ("Delay" if can_flag_delay else ""),
            True,
            can_flag_delay,
        )

    def _primary_text(self, now: datetime, profile) -> str:
        if self.state.mode is ModeV2.STOPWATCH:
            return stopwatch_primary_text(self.state)

        dive = self.state.dive
        if dive.phase is DivePhase.READY:
            return "00:00.0"
        if dive.phase is DivePhase.CLEAN_TIME:
            status = dive.clean_time_status(now)
            return status["CT"]
        if dive.phase is DivePhase.DESCENT:
            ls = dive.session.events.get("LS")
            if ls is None:
                return "--:--.-"
            return format_tenths((now - ls.timestamp).total_seconds())
        if dive.phase is DivePhase.BOTTOM:
            ls = dive.session.events.get("LS")
            if ls is None:
                return "--:--.-"
            return format_tenths((now - ls.timestamp).total_seconds())
        if dive.phase is DivePhase.ASCENT and self._show_tsv(profile):
            anchor = self._first_oxygen_shift_anchor(profile)
            if anchor is None:
                return "00:00 TSV"
            elapsed = max((now - anchor).total_seconds(), 0.0)
            return f"{format_minutes_seconds(elapsed)} TSV"
        if dive.phase is DivePhase.ASCENT and dive._at_stop:
            anchor = self._current_stop_anchor(profile)
            if anchor is None:
                return "--:--.-"
            return format_tenths((now - anchor).total_seconds())
        lb = dive.session.events.get("LB")
        if lb is None:
            return "--:--.-"
        return format_tenths((now - lb.timestamp).total_seconds())

    def _depth_text(self, now: datetime, profile) -> str:
        if self.state.mode is ModeV2.STOPWATCH:
            return ""
        depth = self.state.parsed_depth()
        dive = self.state.dive
        if dive.phase is DivePhase.DESCENT:
            estimate = estimate_current_depth(
                controller=dive,
                now=now,
                max_depth_fsw=depth,
                active_profile=profile,
            )
            return f"{estimate if estimate is not None else 0} fsw"
        if depth is None:
            return "Max -- fsw"
        if dive.phase is DivePhase.BOTTOM:
            return f"{depth} fsw"
        if dive.phase is DivePhase.ASCENT and dive._at_stop and profile is not None:
            latest = dive.latest_arrival_event()
            if latest is not None:
                stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
                current_depth = self._stop_depth_for_number(stop_depths, latest.stop_number)
                if current_depth is not None:
                    return f"{current_depth} fsw"
        if dive.phase is DivePhase.ASCENT:
            estimate = estimate_current_depth(
                controller=dive,
                now=now,
                max_depth_fsw=depth,
                active_profile=profile,
            )
            return f"{estimate} fsw" if estimate is not None else "--"
        return f"{depth} fsw"

    def _awaiting_first_o2_confirmation(self, profile) -> bool:
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

    def _log(self, line: str) -> None:
        self.state.log_lines.append(line)
