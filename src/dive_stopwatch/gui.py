"""Tkinter GUI for stopwatch and dive workflows."""

from __future__ import annotations

from datetime import datetime
import math
import tkinter as tk
from tkinter import ttk

from dive_stopwatch.dive_mode import DiveController, DivePhase
from dive_stopwatch.dive_session import ceil_minutes, format_minutes_seconds
from dive_stopwatch.stopwatch import DeviceMode, Stopwatch, format_hhmmss
from dive_stopwatch.tables import (
    build_basic_air_decompression_profile,
    build_basic_air_decompression_profile_for_session,
    evaluate_first_stop_arrival,
    lookup_no_decompression_limit,
    lookup_no_decompression_limit_for_depth,
    planned_travel_time_to_first_stop_seconds,
)


def format_tenths(seconds: float) -> str:
    """Format elapsed seconds as MM:SS.t."""

    clamped = max(seconds, 0.0)
    total_tenths = math.floor((clamped * 10) + 1e-9)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"


def parse_minutes_seconds(display: str) -> float:
    """Parse a MM:SS display string into total seconds."""

    minutes_text, seconds_text = display.split(":", maxsplit=1)
    return (int(minutes_text) * 60) + int(seconds_text)


def format_countdown_tenths(seconds: float) -> str:
    """Format a countdown that can run past zero."""

    if seconds >= 0:
        return format_tenths(seconds)
    return f"+{format_tenths(abs(seconds))}"


def format_hours_minutes(total_minutes: int) -> str:
    """Format whole minutes as H:MM."""

    hours, minutes = divmod(max(total_minutes, 0), 60)
    return f"{hours}:{minutes:02d}"


def format_clock_hours_minutes(display: str) -> str:
    """Convert HH:MM:SS wall-clock text to HH:MM."""

    hours_text, minutes_text, _seconds_text = display.split(":", maxsplit=2)
    return f"{int(hours_text):02d}:{minutes_text}"


def format_call_response_value(key: str, value: str | int) -> str:
    """Format right-side call/response values as hours and minutes."""

    if isinstance(value, int):
        return format_hours_minutes(value)

    if key in {"LS", "RB", "LB", "RS", "R", "L"}:
        return format_clock_hours_minutes(value)

    if key == "AT":
        return format_hours_minutes(ceil_minutes(parse_minutes_seconds(value)))

    return value


class DiveStopwatchApp:
    """Small operator-focused GUI for stopwatch and dive mode."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("The CAISSON")
        self.root.geometry("860x640")
        self.root.minsize(760, 560)

        self.mode = DeviceMode.STOPWATCH
        self.stopwatch = Stopwatch()
        self.dive = DiveController()

        self.mode_text = tk.StringVar(value="STOPWATCH MODE")
        self.display_label_text = tk.StringVar(value="Primary Display")
        self.phase_text = tk.StringVar(value="READY")
        self.primary_display = tk.StringVar(value="00:00:00.000")
        self.secondary_display = tk.StringVar(value="live=00:00:00.000")
        self.ct_text = tk.StringVar(value="CT 10:00")
        self.status_text = tk.StringVar(value="Ready.")
        self.depth_label_text = tk.StringVar(value="Max Depth")
        self.depth_text = tk.StringVar(value="")
        self.depth_estimate_text = tk.StringVar(value="--")
        self.hold_label_vars = [tk.StringVar(value=f"H{index}") for index in range(1, 7)]
        self.hold_value_vars = [tk.StringVar(value="--") for _ in range(6)]
        self.event_values: dict[str, tk.StringVar] = {
            key: tk.StringVar(value="--")
            for key in ("LS", "RB", "LB", "RS", "R", "L", "DT", "BT", "AT", "TDT", "TTD")
        }

        self._build_ui()
        self._refresh_loop()

    def _build_ui(self) -> None:
        self.root.configure(bg="#f3efe5")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#f3efe5")
        style.configure("Card.TFrame", background="#fffaf1")
        style.configure("Header.TLabel", background="#f3efe5", foreground="#183153", font=("Menlo", 20, "bold"))
        style.configure("Subheader.TLabel", background="#f3efe5", foreground="#37536b", font=("Avenir Next", 12, "bold"))
        style.configure("Value.TLabel", background="#fffaf1", foreground="#102133", font=("Menlo", 28, "bold"))
        style.configure("SmallValue.TLabel", background="#fffaf1", foreground="#2f4358", font=("Menlo", 16, "bold"))
        style.configure("CardLabel.TLabel", background="#fffaf1", foreground="#445b70", font=("Avenir Next", 11, "bold"))
        style.configure("EventKey.TLabel", background="#fffaf1", foreground="#506578", font=("Avenir Next", 11, "bold"))
        style.configure("EventValue.TLabel", background="#fffaf1", foreground="#102133", font=("Menlo", 16, "bold"))
        style.configure("Status.TLabel", background="#f3efe5", foreground="#183153", font=("Avenir Next", 12))

        container = ttk.Frame(self.root, padding=18, style="Panel.TFrame")
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="Panel.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        ttk.Label(header, text="CAISSON", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Deepwater Research Group", style="Subheader.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.mode_text, style="CardLabel.TLabel").grid(row=2, column=0, sticky="w", pady=(4, 0))

        toggle_button = tk.Button(
            header,
            text="Toggle Mode",
            command=self._toggle_mode,
            bg="#d8e6f2",
            fg="#102133",
            activebackground="#c7ddef",
            activeforeground="#102133",
            font=("Avenir Next", 12, "bold"),
            padx=16,
            pady=10,
            relief="flat",
        )
        toggle_button.grid(row=0, column=1, rowspan=3, sticky="e")

        main_panel = ttk.Frame(container, style="Card.TFrame", padding=18)
        main_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        main_panel.columnconfigure(0, weight=1)

        ttk.Label(main_panel, textvariable=self.display_label_text, style="Subheader.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main_panel, textvariable=self.primary_display, style="Value.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(main_panel, textvariable=self.secondary_display, style="SmallValue.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 14))
        depth_row = ttk.Frame(main_panel, style="Card.TFrame")
        depth_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        depth_row.columnconfigure(2, weight=1)
        ttk.Label(depth_row, textvariable=self.depth_label_text, style="CardLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.depth_entry = tk.Entry(
            depth_row,
            textvariable=self.depth_text,
            font=("Menlo", 15, "bold"),
            width=8,
            bg="#fffdf8",
            fg="#102133",
            disabledbackground="#fffdf8",
            disabledforeground="#102133",
            readonlybackground="#fffdf8",
            insertbackground="#102133",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d2c4",
            highlightcolor="#d8d2c4",
        )
        self.depth_entry.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.depth_estimate_label = ttk.Label(depth_row, textvariable=self.depth_estimate_text, style="SmallValue.TLabel")
        self.depth_estimate_label.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(12, 0),
        )

        ttk.Label(main_panel, textvariable=self.ct_text, style="SmallValue.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 0))

        button_bar = ttk.Frame(main_panel, style="Card.TFrame")
        button_bar.grid(row=5, column=0, sticky="ew", pady=(24, 18))
        for index in range(4):
            button_bar.columnconfigure(index, weight=1)

        self.start_button = self._make_action_button(button_bar, "Start", self._handle_start)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.lap_button = self._make_action_button(button_bar, "Lap", self._handle_lap)
        self.lap_button.grid(row=0, column=1, sticky="ew", padx=4)

        self.stop_button = self._make_action_button(button_bar, "Stop", self._handle_stop)
        self.stop_button.grid(row=0, column=2, sticky="ew", padx=4)

        self.reset_button = self._make_action_button(button_bar, "Reset", self._handle_reset, bg="#f0c8bd")
        self.reset_button.grid(row=0, column=3, sticky="ew", padx=(8, 0))

        ttk.Label(main_panel, textvariable=self.status_text, style="Status.TLabel", wraplength=470).grid(
            row=6,
            column=0,
            sticky="ew",
        )

        side_panel = ttk.Frame(container, style="Card.TFrame", padding=18)
        side_panel.grid(row=1, column=1, sticky="nsew")
        side_panel.columnconfigure(1, weight=1)

        ttk.Label(side_panel, text="Charts", style="CardLabel.TLabel").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12),
        )

        row_index = 1
        for key in ("LS", "RB", "LB", "RS"):
            ttk.Label(side_panel, text=key, style="EventKey.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Label(side_panel, textvariable=self.event_values[key], style="EventValue.TLabel").grid(
                row=row_index,
                column=1,
                sticky="e",
                pady=4,
            )
            row_index += 1

        ttk.Separator(side_panel, orient="horizontal").grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        row_index += 1

        for label_var, value_var in zip(self.hold_label_vars, self.hold_value_vars):
            ttk.Label(side_panel, textvariable=label_var, style="EventKey.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Label(side_panel, textvariable=value_var, style="EventValue.TLabel").grid(
                row=row_index,
                column=1,
                sticky="e",
                pady=4,
            )
            row_index += 1

        ttk.Separator(side_panel, orient="horizontal").grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        row_index += 1

        for key in ("DT", "BT", "AT", "TDT", "TTD"):
            ttk.Label(side_panel, text=key, style="EventKey.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Label(side_panel, textvariable=self.event_values[key], style="EventValue.TLabel").grid(
                row=row_index,
                column=1,
                sticky="e",
                pady=4,
            )
            row_index += 1

        hint = (
            "Dive mode flow:\n"
            "Start = LS\n"
            "Lap = RB, then LB\n"
            "Lap after LB = R then L\n"
            "Stop = RS and begin CT"
        )
        ttk.Label(side_panel, text=hint, style="Status.TLabel", justify="left", wraplength=240).grid(
            row=row_index,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 0),
        )

        self._update_ui()

    def _make_action_button(self, parent: ttk.Frame, text: str, command: object, bg: str = "#cfe8df") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#102133",
            activebackground=bg,
            activeforeground="#102133",
            font=("Avenir Next", 14, "bold"),
            padx=12,
            pady=18,
            relief="flat",
        )

    def _toggle_mode(self) -> None:
        self.mode = DeviceMode.DIVE if self.mode is DeviceMode.STOPWATCH else DeviceMode.STOPWATCH
        self.status_text.set(f"Switched to {self.mode.name} mode.")
        self._update_ui()

    def _handle_start(self) -> None:
        try:
            if self.mode is DeviceMode.DIVE:
                if self.dive.phase is DivePhase.ASCENT and self.dive.delay_zone_prompt_active:
                    result = self.dive.start()
                    self.status_text.set("Delay to 1st: deeper than 50 selected.")
                elif self._can_prompt_delay_to_first_stop():
                    self.dive.flag_delay_to_first_stop()
                    self.status_text.set("Deeper than 50? Start = yes, Lap = no.")
                    result = None
                else:
                    result = self.dive.start()
                    self.status_text.set(f"{result['event']} {result['clock']}")
            else:
                self.stopwatch.start()
                self.status_text.set("Stopwatch running.")
        except RuntimeError as exc:
            self.status_text.set(str(exc))
        self._update_ui()

    def _handle_lap(self) -> None:
        try:
            if self.mode is DeviceMode.DIVE:
                result = self.dive.lap()
                if result["event"] == "DELAY_ZONE":
                    self.status_text.set("Delay to 1st: shallower than 50 selected.")
                elif result["event"] == "RB":
                    self.status_text.set(f"RB {result['clock']}   DT {result['DT']}")
                elif result["event"] == "LB":
                    self.status_text.set(f"LB {result['clock']}   BT {result['BT']}")
                else:
                    self.status_text.set(f"{result['event']}{result['stop_number']}   {result['clock']}")
            else:
                mark = self.stopwatch.lap()
                self.status_text.set(
                    f"LAP {mark.index}   lap {format_hhmmss(mark.lap_seconds)}   total {format_hhmmss(mark.total_seconds)}"
                )
        except RuntimeError as exc:
            self.status_text.set(str(exc))
        self._update_ui()

    def _handle_stop(self) -> None:
        try:
            if self.mode is DeviceMode.DIVE:
                result = self.dive.stop()
                self.status_text.set(
                    f"RS {result['clock']}   AT {result['AT']}   TDT {result['TDT']}   TTD {result['TTD']}   CT {result['CT']}"
                )
            else:
                self.stopwatch.stop()
                self.status_text.set("Stopwatch paused.")
        except RuntimeError as exc:
            self.status_text.set(str(exc))
        self._update_ui()

    def _handle_reset(self) -> None:
        try:
            if self.mode is DeviceMode.DIVE:
                self.dive.reset()
                self.status_text.set("Dive session cleared.")
            else:
                self.stopwatch.reset()
                self.status_text.set("Stopwatch reset.")
        except RuntimeError as exc:
            self.status_text.set(str(exc))
        self._update_ui()

    def _update_ui(self) -> None:
        self.mode_text.set(f"{self.mode.name} MODE")

        if self.mode is DeviceMode.DIVE:
            self.display_label_text.set(f"Phase: {self._phase_label()}")
            self._update_dive_summary()
            self.primary_display.set(self._primary_dive_display())
            self.secondary_display.set(self._secondary_dive_display())
            self.ct_text.set(self._guidance_or_clean_time_text())
            self._update_depth_entry_state()
            self.lap_button.configure(text="Lap")
            self.start_button.configure(text="Start")
            self.stop_button.configure(text="Stop")
        else:
            self.display_label_text.set("Primary Display")
            display = self.stopwatch.display_time()
            live = self.stopwatch.total_elapsed()
            self.primary_display.set(format_tenths(display))
            self.secondary_display.set(f"live={format_tenths(live)} running={self.stopwatch.running}")
            self.ct_text.set("CT --:--")
            self.depth_label_text.set("Max Depth")
            self.depth_estimate_text.set("--")
            self.depth_entry.configure(state="normal")
            self.depth_entry.grid()
            self.depth_estimate_label.grid_remove()
            for value in self.event_values.values():
                value.set("--")
            self.lap_button.configure(text="Lap")
            self.start_button.configure(text="Start")
            self.stop_button.configure(text="Stop")

    def _update_dive_summary(self) -> None:
        summary = self.dive.session.summary()
        for key, variable in self.event_values.items():
            variable.set("--")
        for key in ("LS", "RB", "LB", "RS", "DT", "BT", "AT", "TDT", "TTD"):
            raw_value = summary.get(key, "--")
            self.event_values[key].set(format_call_response_value(key, raw_value) if raw_value != "--" else "--")

        latest_r = next((event for event in reversed(self.dive.stop_events) if event.code == "R"), None)
        latest_l = next((event for event in reversed(self.dive.stop_events) if event.code == "L"), None)
        self._update_hold_chart()

    def _update_hold_chart(self) -> None:
        for index, (label_var, value_var) in enumerate(zip(self.hold_label_vars, self.hold_value_vars), start=1):
            label_var.set(f"H{index}")
            value_var.set("--")

        hold_map: dict[int, dict[str, datetime]] = {}
        for event in self.dive.stop_events:
            hold_map.setdefault(event.stop_number, {})
            hold_map[event.stop_number][event.code] = event.timestamp

        for stop_number, value_var in enumerate(self.hold_value_vars, start=1):
            hold = hold_map.get(stop_number)
            if not hold or "R" not in hold:
                continue
            start_time = hold["R"]
            end_time = hold.get("L")
            if end_time is None:
                duration_seconds = (datetime.now() - start_time).total_seconds()
            else:
                duration_seconds = (end_time - start_time).total_seconds()
            value_var.set(format_minutes_seconds(duration_seconds))

    def _primary_dive_display(self) -> str:
        summary = self.dive.session.summary()
        if self.dive.phase is DivePhase.READY:
            return "Awaiting LS"
        if self.dive.phase is DivePhase.DESCENT:
            return self._live_total_display()
        if self.dive.phase is DivePhase.BOTTOM:
            return self._live_total_display()
        if self.dive.phase is DivePhase.ASCENT:
            return self._live_ascent_display()
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return self._clean_time_text()
        return "--"

    def _secondary_dive_display(self) -> str:
        summary = self.dive.session.summary()
        if self.dive.phase in {DivePhase.DESCENT, DivePhase.BOTTOM} and "LS" in summary:
            if self.dive.phase is DivePhase.DESCENT:
                return "Press Lap to reach bottom"
            return "Press Lap to leave bottom"
        if self.dive.phase is DivePhase.ASCENT and "LB" in summary:
            profile = self._planned_first_stop_profile()
            if profile is not None and profile.section == "no_decompression":
                return "Stop to Reach Surface/ Lap to Hold"
            first_stop_arrival = self.dive.first_stop_arrival_event()
            if first_stop_arrival is None:
                if self.dive.delay_zone_prompt_active:
                    return "Delay to 1st?   Start = >50   Lap = <50"
                return "Lap to Reach Stop / Press Start for Delay"
            evaluation = self._first_stop_arrival_evaluation()
            if evaluation is not None and evaluation.outcome == "early_arrival":
                remaining_seconds = evaluation.stop_timer_starts_after_seconds - (
                    datetime.now() - self.dive.session.events["LB"].timestamp
                ).total_seconds()
                return f"Stop timer begins in {format_countdown_tenths(remaining_seconds)}"
            if self.dive._awaiting_leave_stop:
                return "Press Lap to leave stop"
            return "Press Lap to reach next stop"
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return "Observe diver for AGE symptoms"
        parts = []
        for key in ("LS", "RB", "LB", "RS"):
            if key in summary:
                parts.append(f"{key} {summary[key]}")
        return "   ".join(parts) if parts else "Press Start to leave Surface"

    def _phase_label(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return "RUNNING" if self.stopwatch.running else "READY"
        if self.dive.phase is DivePhase.ASCENT and self.dive._awaiting_leave_stop:
            return "AT STOP"
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return "CLEAN TIME"
        return self.dive.phase.name

    def _depth_estimate_display(self) -> str:
        depth = self._parsed_depth()
        if depth is None or self.mode is not DeviceMode.DIVE:
            return "--"
        if self.dive.phase is DivePhase.BOTTOM:
            return f"{depth} fsw"
        estimate = self._estimated_current_depth(depth)
        if estimate is None:
            return "--"
        return f"{estimate} fsw"

    def _estimated_current_depth(self, max_depth_fsw: int) -> int | None:
        if self.dive.phase is not DivePhase.ASCENT:
            return None

        profile = self._active_depth_profile()
        if profile is None:
            return None

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        latest_stop = self.dive.latest_stop_event()
        first_stop_arrival = self.dive.first_stop_arrival_event()
        lb_event = self.dive.session.events.get("LB")

        if first_stop_arrival is None:
            if lb_event is None:
                return None
            destination = stop_depths[0] if stop_depths else 0
            return self._interpolate_depth(max_depth_fsw, destination, lb_event.timestamp)

        if self.dive._awaiting_leave_stop and latest_stop is not None and latest_stop.code == "R":
            return self._stop_depth_for_number(stop_depths, latest_stop.stop_number)

        if latest_stop is not None and latest_stop.code == "L":
            source_depth = self._stop_depth_for_number(stop_depths, latest_stop.stop_number)
            destination = self._next_stop_depth(stop_depths, latest_stop.stop_number)
            if source_depth is None:
                return None
            return self._interpolate_depth(source_depth, destination, latest_stop.timestamp)

        return self._stop_depth_for_number(stop_depths, first_stop_arrival.stop_number)

    def _active_depth_profile(self):
        planned_profile = self._planned_first_stop_profile()
        if planned_profile is None:
            return None
        evaluation = self._first_stop_arrival_evaluation()
        if evaluation is not None and evaluation.outcome != "delay_zone_required":
            return evaluation.active_profile
        return planned_profile

    def _interpolate_depth(self, source_depth: int, destination_depth: int, anchor_time: datetime) -> int:
        elapsed_seconds = max((datetime.now() - anchor_time).total_seconds(), 0.0)
        current_depth = source_depth - (elapsed_seconds / 2.0)
        clamped_depth = max(destination_depth, current_depth)
        return max(int(math.ceil(clamped_depth)), 0)

    def _stop_depth_for_number(self, stop_depths: list[int], stop_number: int) -> int | None:
        index = stop_number - 1
        if 0 <= index < len(stop_depths):
            return stop_depths[index]
        return 0 if index == len(stop_depths) else None

    def _next_stop_depth(self, stop_depths: list[int], stop_number: int) -> int:
        next_index = stop_number
        if 0 <= next_index < len(stop_depths):
            return stop_depths[next_index]
        return 0

    def _guidance_or_clean_time_text(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return "CT --:--"

        if self.dive.phase is DivePhase.CLEAN_TIME:
            return self._clean_time_text()

        if self.dive.phase is DivePhase.ASCENT:
            return self._ascent_schedule_status_text()

        if self.dive.phase in {DivePhase.DESCENT, DivePhase.BOTTOM}:
            if self.dive.phase is DivePhase.BOTTOM:
                return self._live_depth_guidance() or "Press mode to input MD"
            return self._live_depth_guidance() or "Deco info available after RB."

        return "Deco info available after RB."

    def _update_depth_entry_state(self) -> None:
        if self.mode is not DeviceMode.DIVE:
            self.depth_label_text.set("Max Depth")
            self.depth_entry.configure(state="normal")
            self.depth_entry.grid()
            self.depth_estimate_label.grid_remove()
            return

        if self.dive.phase is DivePhase.ASCENT:
            self.depth_label_text.set("Depth")
            self.depth_estimate_text.set(self._depth_estimate_display())
            self.depth_entry.configure(state="readonly")
            self.depth_entry.grid_remove()
            self.depth_estimate_label.grid()
        elif self.dive.phase is DivePhase.BOTTOM:
            self.depth_label_text.set("Max Depth")
            self.depth_entry.configure(state="normal")
            self.depth_entry.grid()
            self.depth_estimate_label.grid_remove()
        else:
            self.depth_label_text.set("Max Depth")
            self.depth_entry.configure(state="readonly")
            self.depth_entry.grid()
            self.depth_estimate_label.grid_remove()

    def _clean_time_text(self) -> str:
        if self.dive.clean_time is None:
            return "CT 10:00"

        status = self.dive.clean_time_status()
        suffix = " COMPLETE" if status["complete"] else ""
        return f"CT {status['CT']}{suffix}"

    def _refresh_loop(self) -> None:
        try:
            self._update_ui()
        except Exception as exc:
            self.status_text.set(f"GUI warning: {exc}")
        self.root.after(100, self._refresh_loop)

    def _live_total_display(self) -> str:
        ls_event = self.dive.session.events.get("LS")
        if ls_event is None:
            return "Awaiting LS"
        elapsed = (datetime.now() - ls_event.timestamp).total_seconds()
        return format_tenths(elapsed)

    def _live_ascent_display(self) -> str:
        first_stop_arrival = self.dive.first_stop_arrival_event()
        if first_stop_arrival is None:
            tt1st_display = self._live_tt1st_display()
            if tt1st_display != "--:--.-":
                return tt1st_display
            lb_event = self.dive.session.events.get("LB")
            if lb_event is None:
                return "--:--.-"
            elapsed = (datetime.now() - lb_event.timestamp).total_seconds()
            return format_tenths(elapsed)

        lb_event = self.dive.session.events.get("LB")
        evaluation = self._first_stop_arrival_evaluation()
        if lb_event is None:
            return "--:--.-"
        if evaluation is None:
            elapsed = (datetime.now() - first_stop_arrival.timestamp).total_seconds()
            return format_tenths(elapsed)

        elapsed_since_lb = (datetime.now() - lb_event.timestamp).total_seconds()
        stop_elapsed = elapsed_since_lb - evaluation.stop_timer_starts_after_seconds
        if stop_elapsed < 0:
            return format_countdown_tenths(-stop_elapsed)
        return format_tenths(stop_elapsed)

    def _live_tt1st_display(self) -> str:
        planned_seconds = self._planned_tt1st_seconds()
        lb_event = self.dive.session.events.get("LB")
        if planned_seconds is None or lb_event is None:
            return "--:--.-"

        elapsed_seconds = (datetime.now() - lb_event.timestamp).total_seconds()
        remaining_seconds = planned_seconds - elapsed_seconds
        return format_countdown_tenths(remaining_seconds)

    def _parsed_depth(self) -> int | None:
        raw = self.depth_text.get().strip()
        if not raw:
            return None
        try:
            depth = int(raw)
        except ValueError:
            return None
        if depth <= 0:
            return None
        return depth

    def _live_depth_guidance(self) -> str | None:
        depth = self._parsed_depth()
        ls_event = self.dive.session.events.get("LS")
        if depth is None or ls_event is None:
            return None

        try:
            table_depth, no_d_limit = lookup_no_decompression_limit_for_depth(depth)
        except (KeyError, ValueError):
            elapsed_minutes = ceil_minutes((datetime.now() - ls_event.timestamp).total_seconds())
            try:
                profile = build_basic_air_decompression_profile(depth, elapsed_minutes)
            except (KeyError, ValueError):
                return f"Depth {depth} fsw not supported yet."

            if profile.section == "no_decompression":
                return f"Depth {depth} fsw not supported yet."

            return (
                f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
                f"DST: {profile.first_stop_time_min} min"
            )

        if no_d_limit is None:
            return f"No-D Limit: Unlimited   table {table_depth} fsw"

        elapsed_minutes = ceil_minutes((datetime.now() - ls_event.timestamp).total_seconds())
        if elapsed_minutes <= no_d_limit:
            return f"No-D Limit: {no_d_limit} min   table {table_depth} fsw"

        profile = build_basic_air_decompression_profile(depth, elapsed_minutes)
        if profile.section == "no_decompression":
            return f"No-D Limit: {no_d_limit} min   Repet: {profile.repeat_group}"

        return (
            f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
            f"DST: {profile.first_stop_time_min} min"
        )

    def _final_deco_guidance(self) -> str | None:
        profile = self._planned_first_stop_profile()
        lb_event = self.dive.session.events.get("LB")
        if profile is None or lb_event is None:
            return None
        if profile.section == "no_decompression":
            return f"No-D Dive   Repet: {profile.repeat_group}"

        first_stop_arrival = self.dive.first_stop_arrival_event()
        if first_stop_arrival is None:
            if self.dive.delay_zone_prompt_active:
                return "Delay to 1st? Start=>50  Lap=<50"
            planned_tt1st_seconds = self._planned_tt1st_seconds()
            if planned_tt1st_seconds is None:
                return (
                    f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
                    f"DST: {profile.first_stop_time_min} min"
                )
            elapsed_seconds = (datetime.now() - lb_event.timestamp).total_seconds()
            remaining_seconds = planned_tt1st_seconds - elapsed_seconds
            return (
                f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
                f"DST: {profile.first_stop_time_min} min   "
                f"TT1st {format_countdown_tenths(remaining_seconds)}"
            )

        evaluation = self._first_stop_arrival_evaluation()
        if evaluation is None:
            actual_tt1st = format_tenths((first_stop_arrival.timestamp - lb_event.timestamp).total_seconds())
            return (
                f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                f"Actual TT1st {actual_tt1st}   Recompute pending"
            )

        actual_tt1st = format_tenths(evaluation.actual_tt1st_seconds)
        if evaluation.outcome == "early_arrival":
            remaining_seconds = evaluation.stop_timer_starts_after_seconds - (
                datetime.now() - lb_event.timestamp
            ).total_seconds()
            return (
                f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                f"Early by {format_tenths(abs(evaluation.delay_seconds or 0.0))}   "
                f"Start stop in {format_countdown_tenths(remaining_seconds)}"
            )
        if evaluation.outcome == "ignore_delay":
            return (
                f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                f"Delay {format_tenths(evaluation.delay_seconds or 0.0)} ignored   "
                f"Stop {evaluation.active_profile.first_stop_time_min} min at {evaluation.active_profile.first_stop_depth_fsw} fsw"
            )
        if evaluation.outcome == "delay_zone_required":
            return (
                f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                f"Delay +{evaluation.rounded_delay_minutes} min   "
                f"Need delay zone (<50 or >50)"
            )
        if evaluation.outcome == "recompute":
            if evaluation.missed_deeper_stop:
                return (
                    f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                    f"Delay +{evaluation.rounded_delay_minutes} min   "
                    f"Missed deeper stop time moved to {evaluation.active_profile.first_stop_depth_fsw} fsw"
                )
            if evaluation.schedule_changed:
                return (
                    f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                    f"Delay +{evaluation.rounded_delay_minutes} min   "
                    f"New stop {evaluation.active_profile.first_stop_time_min} min at {evaluation.active_profile.first_stop_depth_fsw} fsw"
                )
            return (
                f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
                f"Delay +{evaluation.rounded_delay_minutes} min   "
                f"Planned schedule unchanged"
            )

        return (
            f"R1 {first_stop_arrival.timestamp.strftime('%H:%M:%S')}   "
            f"Actual TT1st {actual_tt1st}   Recompute pending"
        )

    def _ascent_schedule_status_text(self) -> str:
        profile = self._active_depth_profile()
        if profile is None:
            return "--/--   --   Next Stop: --"

        table_text = self._table_schedule_text(profile)
        repet_text = profile.repeat_group or "--"
        next_stop_text = self._next_stop_text(profile)
        return f"{table_text}   {repet_text}   Next Stop: {next_stop_text}"

    def _table_schedule_text(self, profile) -> str:
        if profile.table_bottom_time_min is None:
            no_d_limit = lookup_no_decompression_limit(profile.table_depth_fsw)
            limit_text = "Unlimited" if no_d_limit is None else str(no_d_limit)
            return f"{profile.table_depth_fsw}/{limit_text}"
        return f"{profile.table_depth_fsw}/{profile.table_bottom_time_min}"

    def _next_stop_text(self, profile) -> str:
        if profile.section == "no_decompression":
            return "Surface"

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        latest_stop = self.dive.latest_stop_event()
        if latest_stop is None:
            return f"{profile.first_stop_depth_fsw} fsw" if profile.first_stop_depth_fsw is not None else "--"

        if self.dive._awaiting_leave_stop:
            current_depth = self._stop_depth_for_number(stop_depths, latest_stop.stop_number)
            return f"{current_depth} fsw" if current_depth is not None else "--"

        next_depth = self._next_stop_depth(stop_depths, latest_stop.stop_number)
        return "Surface" if next_depth == 0 else f"{next_depth} fsw"

    def _planned_first_stop_profile(self):
        depth = self._parsed_depth()
        if depth is None or "LB" not in self.dive.session.summary():
            return None
        try:
            return build_basic_air_decompression_profile_for_session(depth, self.dive.session)
        except (KeyError, ValueError):
            return None

    def _planned_tt1st_seconds(self) -> int | None:
        depth = self._parsed_depth()
        profile = self._planned_first_stop_profile()
        if depth is None or profile is None:
            return None
        return planned_travel_time_to_first_stop_seconds(depth, profile)

    def _planned_tt1st_display(self) -> str | None:
        planned_seconds = self._planned_tt1st_seconds()
        if planned_seconds is None:
            return None
        return format_tenths(planned_seconds)

    def _first_stop_arrival_evaluation(self):
        depth = self._parsed_depth()
        lb_event = self.dive.session.events.get("LB")
        first_stop_arrival = self.dive.first_stop_arrival_event()
        if depth is None or lb_event is None or first_stop_arrival is None:
            return None
        actual_tt1st_seconds = (first_stop_arrival.timestamp - lb_event.timestamp).total_seconds()
        try:
            return evaluate_first_stop_arrival(
                depth,
                self.dive.session,
                actual_tt1st_seconds,
                delay_zone=self.dive.delay_to_first_stop_zone,
            )
        except (KeyError, ValueError):
            return None

    def _can_prompt_delay_to_first_stop(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            return False
        if self.dive.first_stop_arrival_event() is not None:
            return False
        if self.dive._awaiting_leave_stop:
            return False
        profile = self._planned_first_stop_profile()
        return profile is not None and profile.section != "no_decompression" and profile.first_stop_depth_fsw is not None


def main() -> None:
    root = tk.Tk()
    app = DiveStopwatchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
