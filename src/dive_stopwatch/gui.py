"""Tkinter GUI for stopwatch and dive workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
import math
import tkinter as tk
from tkinter import ttk

from dive_stopwatch.dive_mode import DiveController, DivePhase
from dive_stopwatch.dive_session import ceil_minutes, format_minutes_seconds
from dive_stopwatch.stopwatch import DeviceMode, Stopwatch, format_hhmmss
from dive_stopwatch.tables import (
    DecompressionMode,
    build_air_o2_oxygen_shift_plan,
    build_basic_decompression_profile,
    build_basic_decompression_profile_for_session,
    evaluate_between_stops_delay,
    evaluate_first_stop_arrival,
    lookup_no_decompression_limit,
    lookup_no_decompression_limit_for_depth,
    lookup_repetitive_group_schedule,
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


@dataclass(frozen=True)
class OperateScreenState:
    phase_text: str
    primary_text: str
    depth_label_text: str
    depth_value_text: str
    show_depth_entry: bool
    show_depth_estimate: bool
    summary_text: str
    detail_text: str
    start_label: str
    start_enabled: bool
    lap_label: str
    lap_enabled: bool


@dataclass(frozen=True)
class RecallPage:
    title: str
    lines: list[str]


@dataclass(frozen=True)
class AirBreakEvent:
    kind: str
    index: int
    timestamp: datetime
    depth_fsw: int
    stop_number: int


class DivePresentationStatus(Enum):
    READY = auto()
    DESCENT = auto()
    BOTTOM_NO_DECO = auto()
    BOTTOM_DECO = auto()
    ASCENT_NO_DECO = auto()
    ASCENT_DECO_TRAVEL = auto()
    ASCENT_DECO_STOP = auto()
    SURFACE = auto()
    RECALL = auto()


@dataclass(frozen=True)
class DepthRowState:
    label_text: str
    value_text: str
    show_entry: bool
    show_estimate: bool


@dataclass(frozen=True)
class ButtonRowState:
    start_label: str
    start_enabled: bool
    lap_label: str
    lap_enabled: bool


class DiveStopwatchApp:
    """Small operator-focused GUI for stopwatch and dive mode."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("The CAISSON")
        self.root.geometry("860x640")
        self.root.minsize(760, 560)

        self.mode = DeviceMode.STOPWATCH
        self.decompression_mode = DecompressionMode.AIR
        self.stopwatch = Stopwatch()
        self.dive = DiveController()

        self.mode_text = tk.StringVar(value="STOPWATCH MODE")
        self.display_label_text = tk.StringVar(value="READY")
        self.primary_display = tk.StringVar(value="00:00:00.000")
        self.secondary_display = tk.StringVar(value="--")
        self.ct_text = tk.StringVar(value="")
        self.ct_secondary_text = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Ready.")
        self.depth_label_text = tk.StringVar(value="Max Depth")
        self.depth_text = tk.StringVar(value="")
        self.depth_estimate_text = tk.StringVar(value="--")
        self.delay_to_first_stop_depth_fsw: int | None = None
        self.between_stops_delay_depth_fsw: int | None = None
        self.first_oxygen_confirmed_at: datetime | None = None
        self.first_oxygen_confirmed_stop_number: int | None = None
        self.oxygen_segment_started_at: datetime | None = None
        self.air_break_events: list[AirBreakEvent] = []
        self.logic_log_entries: list[str] = []
        self._logic_log_keys: set[tuple[object, ...]] = set()
        self.show_recall = False
        self.recall_page = 0
        self.status_left_text = tk.StringVar(value="")
        self.status_center_text = tk.StringVar(value="")
        self.status_right_text = tk.StringVar(value="")
        self.test_time_text = tk.StringVar(value="Test Time: LIVE")
        self.test_time_offset_seconds = 0.0
        self.recall_title_text = tk.StringVar(value="DIVE LOG")
        self.recall_footer_text = tk.StringVar(value="Page 1/3")
        self.recall_line_vars = [tk.StringVar(value="") for _ in range(5)]
        self.hold_label_vars = [tk.StringVar(value=f"H{index}") for index in range(1, 7)]
        self.hold_value_vars = [tk.StringVar(value="--") for _ in range(6)]
        self.hold_row_widgets: list[tuple[ttk.Label, ttk.Label]] = []
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
        style.configure("Value.TLabel", background="#fffaf1", foreground="#102133", font=("Menlo", 38, "bold"))
        style.configure("SmallValue.TLabel", background="#fffaf1", foreground="#2f4358", font=("Menlo", 18, "bold"))
        style.configure("CardLabel.TLabel", background="#fffaf1", foreground="#445b70", font=("Avenir Next", 11, "bold"))
        style.configure("EventKey.TLabel", background="#fffaf1", foreground="#506578", font=("Avenir Next", 11, "bold"))
        style.configure("EventValue.TLabel", background="#fffaf1", foreground="#102133", font=("Menlo", 16, "bold"))
        style.configure("Status.TLabel", background="#f3efe5", foreground="#183153", font=("Avenir Next", 12))
        style.configure("RoundPhase.TLabel", background="#fffaf1", foreground="#183153", font=("Menlo", 20, "bold"))
        style.configure("RoundInfo.TLabel", background="#fffaf1", foreground="#2f4358", font=("Menlo", 18, "bold"))
        style.configure("RoundSummary.TLabel", background="#fffaf1", foreground="#183153", font=("Menlo", 16, "bold"))
        style.configure("RecallTitle.TLabel", background="#fffaf1", foreground="#183153", font=("Menlo", 22, "bold"))
        style.configure("RecallLine.TLabel", background="#fffaf1", foreground="#102133", font=("Menlo", 16, "bold"))

        container = ttk.Frame(self.root, padding=18, style="Panel.TFrame")
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="CAISSON", style="Header.TLabel").grid(row=0, column=0, sticky="n")
        ttk.Label(header, text="Deepwater Research Group", style="Subheader.TLabel").grid(row=1, column=0, sticky="n", pady=(4, 0))
        ttk.Label(header, textvariable=self.mode_text, style="CardLabel.TLabel").grid(row=2, column=0, sticky="n", pady=(4, 0))
        ttk.Label(header, textvariable=self.test_time_text, style="Subheader.TLabel").grid(row=3, column=0, sticky="n", pady=(4, 0))

        time_controls = ttk.Frame(header, style="Panel.TFrame")
        time_controls.grid(row=4, column=0, pady=(8, 0))
        for index in range(5):
            time_controls.columnconfigure(index, weight=1)
        self._make_action_button(time_controls, "-1m", lambda: self._advance_test_time(-60), bg="#e6ddd0").grid(row=0, column=0, padx=3)
        self._make_action_button(time_controls, "+1m", lambda: self._advance_test_time(60), bg="#e6ddd0").grid(row=0, column=1, padx=3)
        self._make_action_button(time_controls, "+5m", lambda: self._advance_test_time(300), bg="#e6ddd0").grid(row=0, column=2, padx=3)
        self._make_action_button(time_controls, "+30m", lambda: self._advance_test_time(1800), bg="#e6ddd0").grid(row=0, column=3, padx=3)
        self._make_action_button(time_controls, "Live", self._reset_test_time, bg="#e6ddd0").grid(row=0, column=4, padx=3)

        main_panel = ttk.Frame(container, style="Card.TFrame", padding=18)
        main_panel.grid(row=1, column=0, sticky="nsew")
        main_panel.columnconfigure(0, weight=1)
        main_panel.rowconfigure(0, weight=1)

        self.screen_container = ttk.Frame(main_panel, style="Card.TFrame")
        self.screen_container.grid(row=0, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self.operate_frame = ttk.Frame(self.screen_container, style="Card.TFrame", padding=(16, 8))
        self.operate_frame.grid(row=0, column=0, sticky="nsew")
        self.operate_frame.columnconfigure(0, weight=1)
        self.operate_frame.rowconfigure(0, weight=0)
        self.operate_frame.rowconfigure(1, weight=0)
        self.operate_frame.rowconfigure(2, weight=0)
        self.operate_frame.rowconfigure(3, weight=0)
        self.operate_frame.rowconfigure(4, weight=0)
        self.operate_frame.rowconfigure(5, weight=0)

        self.operate_overlay = tk.Canvas(
            self.operate_frame,
            bg="#fffaf1",
            highlightthickness=0,
            bd=0,
        )
        self.operate_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.operate_frame.bind("<Configure>", self._on_operate_frame_configure)

        ttk.Label(self.operate_frame, textvariable=self.display_label_text, style="RoundPhase.TLabel", anchor="center").grid(
            row=0, column=0, sticky="ew", pady=(6, 12)
        )
        self.primary_display_label = tk.Label(
            self.operate_frame,
            textvariable=self.primary_display,
            bg="#fffaf1",
            fg="#102133",
            font=("Menlo", 38, "bold"),
            anchor="center",
        )
        self.primary_display_label.grid(
            row=1, column=0, sticky="ew", pady=(0, 12)
        )

        self.depth_row = ttk.Frame(self.operate_frame, style="Card.TFrame")
        self.depth_row.grid(row=2, column=0, pady=(0, 12))
        self.depth_prefix_label = ttk.Label(self.depth_row, textvariable=self.depth_label_text, style="RoundInfo.TLabel")
        self.depth_prefix_label.grid(row=0, column=0, padx=(0, 8))
        self.depth_entry = tk.Entry(
            self.depth_row,
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
        self.depth_entry.grid(row=0, column=1)
        self.depth_estimate_label = ttk.Label(self.depth_row, textvariable=self.depth_estimate_text, style="RoundInfo.TLabel")
        self.depth_estimate_label.grid(row=0, column=1)

        self.status_row = ttk.Frame(self.operate_frame, style="Card.TFrame")
        self.status_row.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for index in range(3):
            self.status_row.columnconfigure(index, weight=1)
        ttk.Label(self.status_row, textvariable=self.status_left_text, style="RoundSummary.TLabel", anchor="center").grid(row=0, column=0, sticky="ew")
        ttk.Label(self.status_row, textvariable=self.status_center_text, style="RoundSummary.TLabel", anchor="center").grid(row=0, column=1, sticky="ew")
        ttk.Label(self.status_row, textvariable=self.status_right_text, style="RoundSummary.TLabel", anchor="center").grid(row=0, column=2, sticky="ew")
        self.status_row.grid_remove()

        self.summary_row = ttk.Frame(self.operate_frame, style="Card.TFrame")
        self.summary_row.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.summary_row.columnconfigure(0, weight=1)
        self.summary_row.columnconfigure(1, weight=0)
        self.summary_row.columnconfigure(2, weight=0)
        self.summary_row.columnconfigure(3, weight=1)
        self.summary_primary_label = tk.Label(
            self.summary_row,
            textvariable=self.ct_text,
            bg="#fffaf1",
            fg="#183153",
            font=("Menlo", 16, "bold"),
        )
        self.summary_primary_label.grid(row=0, column=1, sticky="e")
        self.summary_secondary_label = tk.Label(
            self.summary_row,
            textvariable=self.ct_secondary_text,
            bg="#fffaf1",
            fg="#9b1c1c",
            font=("Menlo", 16, "bold"),
        )
        self.summary_secondary_label.grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(self.operate_frame, textvariable=self.secondary_display, style="RoundSummary.TLabel", anchor="center", wraplength=500).grid(
            row=5, column=0, sticky="ew", pady=(0, 6)
        )

        self.recall_frame = ttk.Frame(self.screen_container, style="Card.TFrame", padding=(16, 8))
        self.recall_frame.grid(row=0, column=0, sticky="nsew")
        self.recall_frame.columnconfigure(0, weight=1)
        ttk.Label(self.recall_frame, textvariable=self.recall_title_text, style="RecallTitle.TLabel", anchor="center").grid(
            row=0, column=0, sticky="ew", pady=(6, 16)
        )
        for index, variable in enumerate(self.recall_line_vars, start=1):
            ttk.Label(self.recall_frame, textvariable=variable, style="RecallLine.TLabel", anchor="center").grid(
                row=index, column=0, sticky="ew", pady=8
            )
        ttk.Label(self.recall_frame, textvariable=self.recall_footer_text, style="Subheader.TLabel", anchor="center").grid(
            row=6, column=0, sticky="ew", pady=(18, 0)
        )

        button_bar = ttk.Frame(main_panel, style="Card.TFrame")
        button_bar.grid(row=1, column=0, sticky="ew", pady=(20, 0))
        for index in range(4):
            button_bar.columnconfigure(index, weight=1)

        self.start_button = self._make_action_button(button_bar, "Start/Stop", self._handle_start_stop)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.lap_button = self._make_action_button(button_bar, "Lap/Reset", self._handle_lap_reset, bg="#f0c8bd")
        self.lap_button.grid(row=0, column=1, sticky="ew", padx=4)

        self.recall_button = self._make_action_button(button_bar, "Recall", self._handle_recall, bg="#d8e6f2")
        self.recall_button.grid(row=0, column=2, sticky="ew", padx=4)

        self.mode_button = self._make_action_button(button_bar, "Mode", self._toggle_mode, bg="#d8e6f2")
        self.mode_button.grid(row=0, column=3, sticky="ew", padx=(8, 0))

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

    def _now(self) -> datetime:
        return datetime.now() + timedelta(seconds=self.test_time_offset_seconds)

    def _update_test_time_text(self) -> None:
        if abs(self.test_time_offset_seconds) < 1e-9:
            self.test_time_text.set("Test Time: LIVE")
            return
        sign = "+" if self.test_time_offset_seconds > 0 else "-"
        offset_seconds = abs(self.test_time_offset_seconds)
        minutes, seconds = divmod(int(offset_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            offset_text = f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
        else:
            offset_text = f"{sign}{minutes:02d}:{seconds:02d}"
        self.test_time_text.set(f"Test Time: {offset_text}")

    def _advance_test_time(self, seconds: float) -> None:
        self.test_time_offset_seconds = max(self.test_time_offset_seconds + seconds, 0.0)
        self._update_test_time_text()
        self._update_ui()

    def _reset_test_time(self) -> None:
        self.test_time_offset_seconds = 0.0
        self._update_test_time_text()
        self._update_ui()

    def _on_operate_frame_configure(self, _event: tk.Event) -> None:
        self._draw_safe_square_overlay()

    def _draw_safe_square_overlay(self) -> None:
        canvas = self.operate_overlay
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return

        canvas.delete("overlay")

        diameter = min(width, height) - 36
        if diameter <= 0:
            return

        center_x = width / 2
        center_y = height / 2
        radius = diameter / 2
        safe_side = diameter / math.sqrt(2)
        half_safe = safe_side / 2

        left = center_x - radius
        top = center_y - radius
        right = center_x + radius
        bottom = center_y + radius

        safe_left = center_x - half_safe
        safe_top = center_y - half_safe
        safe_right = center_x + half_safe
        safe_bottom = center_y + half_safe

        canvas.create_oval(
            left,
            top,
            right,
            bottom,
            outline="#d6d0c4",
            width=2,
            dash=(6, 6),
            tags="overlay",
        )
        canvas.create_rectangle(
            safe_left,
            safe_top,
            safe_right,
            safe_bottom,
            outline="#b88f67",
            width=2,
            dash=(4, 4),
            tags="overlay",
        )
        canvas.create_line(center_x, safe_top, center_x, safe_bottom, fill="#e7dfd0", width=1, dash=(2, 6), tags="overlay")
        canvas.create_line(safe_left, center_y, safe_right, center_y, fill="#e7dfd0", width=1, dash=(2, 6), tags="overlay")

    def _toggle_mode(self) -> None:
        if self.mode is DeviceMode.STOPWATCH:
            self.mode = DeviceMode.DIVE
            self.decompression_mode = DecompressionMode.AIR
        elif self.decompression_mode is DecompressionMode.AIR:
            self.decompression_mode = DecompressionMode.AIR_O2
        else:
            self.mode = DeviceMode.STOPWATCH
            self.decompression_mode = DecompressionMode.AIR
        self.first_oxygen_confirmed_at = None
        self.first_oxygen_confirmed_stop_number = None
        self.oxygen_segment_started_at = None
        self.air_break_events.clear()
        self.logic_log_entries.clear()
        self._logic_log_keys.clear()
        self.status_text.set(f"Switched to {self._mode_header_text()}.")
        self.delay_to_first_stop_depth_fsw = None
        self.between_stops_delay_depth_fsw = None
        self._update_ui()

    def _handle_start_stop(self) -> None:
        if self.mode is DeviceMode.DIVE and self.show_recall:
            self.recall_page = max(self.recall_page - 1, 0)
            self._update_ui()
            return
        if self.mode is DeviceMode.DIVE and self.dive.phase is DivePhase.ASCENT and self.dive._at_stop:
            self._handle_lap()
            return
        if self.mode is DeviceMode.DIVE and self.dive.phase is DivePhase.ASCENT and self._start_stop_reaches_surface():
            self._handle_stop()
            return
        if self.mode is DeviceMode.STOPWATCH and self.stopwatch.running:
            self._handle_stop()
            return
        self._handle_start()

    def _handle_lap_reset(self) -> None:
        if self.mode is DeviceMode.DIVE and self.show_recall:
            self.recall_page = min(self.recall_page + 1, len(self._build_recall_pages()) - 1)
            self._update_ui()
            return
        if self.mode is DeviceMode.STOPWATCH and not self.stopwatch.running:
            self._handle_reset()
            return
        if self.mode is DeviceMode.DIVE and self.dive.phase in {DivePhase.READY, DivePhase.CLEAN_TIME}:
            self._handle_reset()
            return
        if self.mode is DeviceMode.DIVE and self.dive.phase is DivePhase.BOTTOM:
            profile = self._planned_first_stop_profile()
            if profile is not None and profile.section != "no_decompression":
                self.status_text.set("Bottom delay procedure not implemented yet.")
                self._update_ui()
                return
        if self.mode is DeviceMode.DIVE and self.dive.phase is DivePhase.ASCENT and self.dive._at_stop:
            if (
                self._awaiting_first_oxygen_confirmation()
                or self._active_air_break_event() is not None
                or self._active_o2_display_mode()
                or self._can_start_air_break()
            ):
                self._handle_lap()
                return
            self.status_text.set("No special procedure is active at this stop.")
            self._update_ui()
            return
        if self.mode is DeviceMode.DIVE and self._can_flag_ascent_delay():
            self._flag_ascent_delay()
            return
        self._handle_lap()

    def _handle_recall(self) -> None:
        if self.mode is not DeviceMode.DIVE:
            self.status_text.set("Recall is available in dive mode.")
            self._update_ui()
            return
        self.show_recall = not self.show_recall
        self._update_ui()

    def _can_flag_ascent_delay(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.show_recall:
            return False
        if self.dive.phase is not DivePhase.ASCENT or self.dive._at_stop:
            return False
        profile = self._profile_after_first_stop_evaluation()
        return profile is not None

    def _has_active_ascent_delay(self) -> bool:
        return self._active_ascent_delay_event() is not None

    def _flag_ascent_delay(self) -> None:
        active_delay = self._active_ascent_delay_event()
        if active_delay is not None:
            ended_delay = self.dive.end_ascent_delay()
            if ended_delay is None:
                self.status_text.set("No active delay to stop.")
            else:
                self.status_text.set(
                    f"Delay{ended_delay.index} stopped at {ended_delay.depth_fsw} fsw"
                )
            self._update_ui()
            return

        depth = self._parsed_depth()
        if depth is None:
            self.status_text.set("Enter Max Depth before flagging a delay.")
            self._update_ui()
            return
        current_depth = self._estimated_current_depth(depth)
        if current_depth is None:
            self.status_text.set("Unable to determine current depth for delay flag.")
            self._update_ui()
            return

        profile = self._profile_after_first_stop_evaluation()
        if profile is not None and profile.section == "no_decompression":
            delay_event = self.dive.mark_ascent_delay_start(current_depth)
            self.between_stops_delay_depth_fsw = current_depth
            self.status_text.set(f"Delay{delay_event.index} flagged at {current_depth} fsw")
            self._update_ui()
            return

        if self.dive.first_stop_arrival_event() is None:
            delay_event = self.dive.mark_ascent_delay_start(current_depth)
            if self.delay_to_first_stop_depth_fsw is None:
                self.delay_to_first_stop_depth_fsw = current_depth
            flagged_depth = self.delay_to_first_stop_depth_fsw
            self.status_text.set(f"Delay{delay_event.index} to 1st flagged at {flagged_depth} fsw")
        else:
            delay_event = self.dive.mark_ascent_delay_start(current_depth)
            if self.between_stops_delay_depth_fsw is None:
                self.between_stops_delay_depth_fsw = current_depth
            flagged_depth = self.between_stops_delay_depth_fsw
            self.status_text.set(f"Delay{delay_event.index} flagged at {flagged_depth} fsw")
        self._update_ui()

    def _handle_start(self) -> None:
        try:
            if self.mode is DeviceMode.DIVE:
                if self.dive.phase is DivePhase.ASCENT:
                    if self._start_stop_reaches_surface():
                        result = self.dive.stop(self._now())
                        self.status_text.set(
                            f"RS {result['clock']}   AT {result['AT']}   TDT {result['TDT']}   TTD {result['TTD']}   CT {result['CT']}"
                        )
                    else:
                        result = self.dive.start(self._now())
                        self.between_stops_delay_depth_fsw = None
                        self.status_text.set(f"R{result['stop_number']}   {result['clock']}")
                else:
                    result = self.dive.start(self._now())
                    if result["event"] == "RB":
                        self.status_text.set(f"RB {result['clock']}   DT {result['DT']}")
                    elif result["event"] == "LB":
                        self.first_oxygen_confirmed_at = None
                        self.first_oxygen_confirmed_stop_number = None
                        self.oxygen_segment_started_at = None
                        self.air_break_events.clear()
                        self.between_stops_delay_depth_fsw = None
                        self.status_text.set(f"LB {result['clock']}   BT {result['BT']}")
                    else:
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
                if self._active_air_break_event() is not None:
                    elapsed_seconds = self._current_air_break_elapsed_seconds() or 0.0
                    if elapsed_seconds < 300:
                        remaining_seconds = max(300 - elapsed_seconds, 0.0)
                        self.status_text.set(
                            f"Complete 5:00 air break first ({format_minutes_seconds(remaining_seconds)} left)"
                        )
                        self._update_ui()
                        return
                    timestamp = self._now()
                    active_break = self._active_air_break_event()
                    self.air_break_events.append(
                        AirBreakEvent(
                            kind="end",
                            index=active_break.index,
                            timestamp=timestamp,
                            depth_fsw=active_break.depth_fsw,
                            stop_number=active_break.stop_number,
                        )
                    )
                    self.oxygen_segment_started_at = timestamp
                    self.status_text.set(f"Back on 100% O2   {timestamp.strftime('%H:%M:%S')}")
                    self._update_ui()
                    return
                if self._can_start_air_break():
                    profile = self._active_depth_profile()
                    latest_arrival = self.dive.latest_arrival_event()
                    if profile is None or latest_arrival is None:
                        self.status_text.set("Unable to start air break.")
                        self._update_ui()
                        return
                    stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
                    current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
                    if current_depth is None:
                        self.status_text.set("Unable to determine air-break depth.")
                        self._update_ui()
                        return
                    timestamp = self._now()
                    next_index = 1 + max((event.index for event in self.air_break_events), default=0)
                    self.air_break_events.append(
                        AirBreakEvent(
                            kind="start",
                            index=next_index,
                            timestamp=timestamp,
                            depth_fsw=current_depth,
                            stop_number=latest_arrival.stop_number,
                        )
                    )
                    self.oxygen_segment_started_at = None
                    self.status_text.set(f"AIR break started   {timestamp.strftime('%H:%M:%S')}")
                    self._update_ui()
                    return
                if self._awaiting_first_oxygen_confirmation():
                    timestamp = self._now()
                    latest_arrival = self.dive.latest_arrival_event()
                    self.first_oxygen_confirmed_at = timestamp
                    self.first_oxygen_confirmed_stop_number = latest_arrival.stop_number if latest_arrival is not None else None
                    self.oxygen_segment_started_at = timestamp
                    self.status_text.set(f"On 100% O2   {timestamp.strftime('%H:%M:%S')}")
                    self._update_ui()
                    return
                profile_before_leave = self._active_depth_profile()
                shift_to_air_for_surface = (
                    profile_before_leave is not None
                    and self._should_shift_to_air_for_surface(profile_before_leave)
                )
                result = self.dive.lap(self._now())
                if result["phase"] == DivePhase.ASCENT.name:
                    if shift_to_air_for_surface:
                        self.oxygen_segment_started_at = None
                    self.between_stops_delay_depth_fsw = None
                    if shift_to_air_for_surface:
                        self.status_text.set(f"L{result['stop_number']}   {result['clock']}   Shift to AIR for surface")
                    else:
                        self.status_text.set(f"L{result['stop_number']}   {result['clock']}")
                else:
                    action = "start" if result["event"] == "R" else "end"
                    self.status_text.set(f"H{result['stop_number']} {action}   {result['clock']}")
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
                result = self.dive.stop(self._now())
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
                self.delay_to_first_stop_depth_fsw = None
                self.between_stops_delay_depth_fsw = None
                self.first_oxygen_confirmed_at = None
                self.first_oxygen_confirmed_stop_number = None
                self.oxygen_segment_started_at = None
                self.air_break_events.clear()
                self.logic_log_entries.clear()
                self._logic_log_keys.clear()
                self.status_text.set("Dive session cleared.")
            else:
                self.stopwatch.reset()
                self.status_text.set("Stopwatch reset.")
        except RuntimeError as exc:
            self.status_text.set(str(exc))
        self._update_ui()

    def _update_ui(self) -> None:
        self.mode_text.set(self._mode_header_text())

        if self.mode is DeviceMode.DIVE:
            self._update_dive_summary()
            self._capture_delay_to_first_stop_depth()
            self._capture_between_stops_delay_depth()
            self._capture_logic_audit_entries()
            self._render_operate_screen_state(self._build_dive_operate_screen_state())
            self.recall_button.configure(text="Operate" if self.show_recall else "Recall", state="normal")
            self.mode_button.configure(text="Mode")
            self._update_recall_view()
            self._set_screen_visibility()
        else:
            self.show_recall = False
            self.delay_to_first_stop_depth_fsw = None
            self.between_stops_delay_depth_fsw = None
            for value in self.event_values.values():
                value.set("--")
            self._render_operate_screen_state(self._build_stopwatch_operate_screen_state())
            self.recall_button.configure(text="Recall")
            self.mode_button.configure(text="Mode")
            self._set_screen_visibility()

    def _mode_header_text(self) -> str:
        if self.mode is DeviceMode.STOPWATCH:
            return "Mode: STOPWATCH"
        return f"Mode: {self.decompression_mode.value}"

    def _build_dive_operate_screen_state(self) -> OperateScreenState:
        status = self._dive_presentation_status()
        button_state = self._dive_button_state(status)
        depth_state = self._dive_depth_row_state(status)
        return OperateScreenState(
            phase_text=f"Status: {self._phase_label()}",
            primary_text=self._primary_dive_display(),
            depth_label_text=depth_state.label_text,
            depth_value_text=depth_state.value_text,
            show_depth_entry=depth_state.show_entry,
            show_depth_estimate=depth_state.show_estimate,
            summary_text=self._summary_line_text(status),
            detail_text=self._line_five_text(),
            start_label=button_state.start_label,
            start_enabled=button_state.start_enabled,
            lap_label=button_state.lap_label,
            lap_enabled=button_state.lap_enabled,
        )

    def _build_stopwatch_operate_screen_state(self) -> OperateScreenState:
        display = self.stopwatch.display_time()
        return OperateScreenState(
            phase_text="STOPWATCH",
            primary_text=format_tenths(display),
            depth_label_text="Max Depth",
            depth_value_text="--",
            show_depth_entry=True,
            show_depth_estimate=False,
            summary_text="",
            detail_text="",
            start_label="Start/Stop",
            start_enabled=True,
            lap_label="Lap/Reset",
            lap_enabled=True,
        )

    def _render_operate_screen_state(self, state: OperateScreenState) -> None:
        self.display_label_text.set(state.phase_text)
        self.primary_display.set(state.primary_text)
        if self._active_air_break_event() is not None:
            primary_color = "#b42318"
        elif self._active_o2_display_mode():
            primary_color = "#207245"
        else:
            primary_color = "#102133"
        self.primary_display_label.configure(fg=primary_color)
        self.secondary_display.set(state.detail_text)
        self._render_summary_line(state.summary_text)
        self.depth_label_text.set(state.depth_label_text)
        self.depth_estimate_text.set(state.depth_value_text)

        if state.show_depth_entry:
            entry_state = (
                "normal"
                if self.mode is DeviceMode.STOPWATCH or self.dive.phase in {DivePhase.READY, DivePhase.BOTTOM}
                else "readonly"
            )
            self.depth_entry.configure(state=entry_state)
            if entry_state == "normal":
                self.depth_entry.configure(
                    bg="#fffdf8",
                    readonlybackground="#fffdf8",
                    highlightbackground="#d8d2c4",
                    highlightcolor="#d8d2c4",
                )
            else:
                self.depth_entry.configure(
                    bg="#f1ede4",
                    readonlybackground="#f1ede4",
                    highlightbackground="#b88f67",
                    highlightcolor="#b88f67",
                )
            self.depth_entry.grid()
        else:
            self.depth_entry.grid_remove()

        if state.show_depth_estimate:
            self.depth_estimate_label.grid()
        else:
            self.depth_estimate_label.grid_remove()

        self.start_button.configure(text=state.start_label, state="normal" if state.start_enabled else "disabled")
        self.lap_button.configure(text=state.lap_label, state="normal" if state.lap_enabled else "disabled")

    def _render_summary_line(self, text: str) -> None:
        if text.startswith("Next: 5 min Air break in "):
            prefix = "Next: 5 min"
            suffix = text[len(prefix):].lstrip()
            self.ct_text.set(prefix)
            self.ct_secondary_text.set(suffix)
            self.summary_primary_label.configure(fg="#183153")
            self.summary_secondary_label.configure(fg="#b42318")
            self.summary_secondary_label.grid()
            return
        if text.startswith("O2 ") and "Break" in text:
            split_token = "Break"
            prefix, suffix = text.split(split_token, maxsplit=1)
            self.ct_text.set(prefix.rstrip())
            self.ct_secondary_text.set(f"{split_token}{suffix}")
            self.summary_primary_label.configure(fg="#207245")
            self.summary_secondary_label.configure(fg="#b42318")
            self.summary_secondary_label.grid()
            return
        if "Break In" in text:
            split_token = "Break In"
            prefix, suffix = text.split(split_token, maxsplit=1)
            self.ct_text.set(prefix.rstrip())
            self.ct_secondary_text.set(f"{split_token}{suffix}")
            self.summary_primary_label.configure(fg="#183153")
            self.summary_secondary_label.configure(fg="#b42318")
            self.summary_secondary_label.grid()
            return
        if text.startswith("Air Break ") and "Resume In" in text:
            split_token = "Resume In"
            prefix, suffix = text.split(split_token, maxsplit=1)
            self.ct_text.set(prefix.rstrip())
            self.ct_secondary_text.set(f"{split_token}{suffix}")
            self.summary_primary_label.configure(fg="#b42318")
            self.summary_secondary_label.configure(fg="#b42318")
            self.summary_secondary_label.grid()
            return
        if text.startswith("Next: ") and " for " in text and self._summary_line_targets_oxygen_stop():
            prefix, suffix = text.split(" for ", maxsplit=1)
            self.ct_text.set(prefix.rstrip())
            self.ct_secondary_text.set(f"for {suffix}")
            self.summary_primary_label.configure(fg="#183153")
            self.summary_secondary_label.configure(fg="#207245")
            self.summary_secondary_label.grid()
            return

        self.ct_text.set(text)
        self.ct_secondary_text.set("")
        self.summary_primary_label.configure(fg="#183153")
        self.summary_secondary_label.grid_remove()

    def _dive_presentation_status(self) -> DivePresentationStatus:
        if self.show_recall:
            return DivePresentationStatus.RECALL
        if self.dive.phase is DivePhase.READY:
            return DivePresentationStatus.READY
        if self.dive.phase is DivePhase.DESCENT:
            return DivePresentationStatus.DESCENT
        if self.dive.phase is DivePhase.BOTTOM:
            profile = self._planned_first_stop_profile()
            if profile is not None and profile.section != "no_decompression":
                return DivePresentationStatus.BOTTOM_DECO
            return DivePresentationStatus.BOTTOM_NO_DECO
        if self.dive.phase is DivePhase.ASCENT:
            profile = self._active_depth_profile()
            if self.dive._at_stop:
                return DivePresentationStatus.ASCENT_DECO_STOP
            if profile is not None and profile.section != "no_decompression":
                return DivePresentationStatus.ASCENT_DECO_TRAVEL
            return DivePresentationStatus.ASCENT_NO_DECO
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return DivePresentationStatus.SURFACE
        return DivePresentationStatus.READY

    def _dive_depth_row_state(self, status: DivePresentationStatus) -> DepthRowState:
        if status is DivePresentationStatus.RECALL:
            return DepthRowState("", "", False, False)
        if status is DivePresentationStatus.READY:
            return DepthRowState("Max", "", True, False)
        if status in {DivePresentationStatus.BOTTOM_NO_DECO, DivePresentationStatus.BOTTOM_DECO}:
            bottom_text = self._bottom_depth_status_text()
            if bottom_text is None:
                return DepthRowState("Max", "", True, False)
            return DepthRowState("", bottom_text, False, True)
        if status in {
            DivePresentationStatus.DESCENT,
            DivePresentationStatus.ASCENT_NO_DECO,
        }:
            return DepthRowState("", self._depth_estimate_display(), False, True)
        if status is DivePresentationStatus.ASCENT_DECO_TRAVEL:
            return DepthRowState("", self._ascent_travel_depth_display(), False, True)
        if status is DivePresentationStatus.ASCENT_DECO_STOP:
            if self._awaiting_first_oxygen_confirmation():
                return DepthRowState("", self._awaiting_o2_depth_display(), False, True)
            if self._active_air_break_event() is not None:
                return DepthRowState("", self._air_break_depth_display(), False, True)
            return DepthRowState("", self._stop_depth_remaining_display(), False, True)
        if status is DivePresentationStatus.SURFACE:
            depth = self._parsed_depth()
            bt = self.dive.session.summary().get("BT", "--")
            text = f"{depth} fsw / {bt} min" if depth is not None and bt != "--" else "--"
            return DepthRowState("", text, False, True)
        return DepthRowState("Max", "", True, False)

    def _dive_button_state(self, status: DivePresentationStatus) -> ButtonRowState:
        if status is DivePresentationStatus.RECALL:
            pages = self._build_recall_pages()
            return ButtonRowState(
                "Prev",
                self.recall_page > 0,
                "Next",
                self.recall_page < len(pages) - 1,
            )

        if status is DivePresentationStatus.READY:
            return ButtonRowState("Leave Surface", True, "", False)
        if status is DivePresentationStatus.DESCENT:
            return ButtonRowState("Reach Bottom", True, "Hold", True)
        if status in {DivePresentationStatus.BOTTOM_NO_DECO, DivePresentationStatus.BOTTOM_DECO}:
            return ButtonRowState("Leave Bottom", True, "Delay" if status is DivePresentationStatus.BOTTOM_DECO else "", status is DivePresentationStatus.BOTTOM_DECO)
        if status is DivePresentationStatus.ASCENT_DECO_STOP:
            if self._awaiting_first_oxygen_confirmation():
                return ButtonRowState("Leave Stop", True, "On O2", True)
            if self._active_air_break_event() is not None:
                return ButtonRowState("Leave Stop", True, "On O2", True)
            if self._active_o2_display_mode() or self._can_start_air_break():
                return ButtonRowState("Leave Stop", True, "Off O2", True)
            return ButtonRowState("Leave Stop", True, "", False)
        if status in {
            DivePresentationStatus.ASCENT_NO_DECO,
            DivePresentationStatus.ASCENT_DECO_TRAVEL,
        }:
            return ButtonRowState(
                "Reach Surface" if self._start_stop_reaches_surface() else "Reach Stop",
                True,
                "Stop Delay" if self._has_active_ascent_delay() else ("Delay" if self._can_flag_ascent_delay() else ""),
                self._can_flag_ascent_delay(),
            )
        if status is DivePresentationStatus.SURFACE:
            return ButtonRowState("", False, "Reset", True)
        return ButtonRowState("Start/Stop", True, "Lap/Reset", True)

    def _update_dive_summary(self) -> None:
        summary = self.dive.session.summary()
        for key, variable in self.event_values.items():
            variable.set("--")
        for key in ("LS", "RB", "LB", "RS", "DT", "BT", "AT", "TDT", "TTD"):
            raw_value = summary.get(key, "--")
            self.event_values[key].set(format_call_response_value(key, raw_value) if raw_value != "--" else "--")
        self._update_hold_chart()

    def _update_hold_chart(self) -> None:
        for index, (label_var, value_var) in enumerate(zip(self.hold_label_vars, self.hold_value_vars), start=1):
            label_var.set(f"H{index}")
            value_var.set("--")

        hold_map: dict[int, dict[str, object]] = {}
        for event in self.dive.descent_hold_events:
            hold_map.setdefault(event.index, {})
            hold_map[event.index][event.kind] = event.timestamp

        depth = self._parsed_depth()
        for stop_number, value_var in enumerate(self.hold_value_vars, start=1):
            hold = hold_map.get(stop_number)
            if not hold or "start" not in hold:
                continue
            start_time = hold["start"]
            hold_depth = self._descent_hold_depth_at_start_for_display(start_time)
            if hold_depth is not None:
                self.hold_label_vars[stop_number - 1].set(f"H{stop_number} ({hold_depth} fsw)")
            end_time = hold.get("end")
            if end_time is None:
                duration_seconds = (self._now() - start_time).total_seconds()
            else:
                duration_seconds = (end_time - start_time).total_seconds()
            value_var.set(format_minutes_seconds(duration_seconds))

    def _primary_dive_display(self) -> str:
        if self.dive.phase is DivePhase.READY:
            return "00:00.0"
        if self.dive.phase is DivePhase.DESCENT:
            return self._live_descent_display()
        if self.dive.phase is DivePhase.BOTTOM:
            return self._live_total_display()
        if self.dive.phase is DivePhase.ASCENT:
            if self._show_tsv_on_primary_display():
                return self._live_tsv_display()
            if self._active_air_break_event() is not None:
                return format_tenths(self._current_air_break_elapsed_seconds() or 0.0)
            if self._active_o2_display_mode() and self.dive._at_stop:
                profile = self._active_depth_profile()
                latest_arrival = self.dive.latest_arrival_event()
                if profile is not None and latest_arrival is not None:
                    stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
                    current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
                    first_oxygen_number = self._first_oxygen_stop_number(profile)
                    first_oxygen_depth = (
                        self._stop_depth_for_number(stop_depths, first_oxygen_number)
                        if first_oxygen_number is not None
                        else None
                    )
                    if current_depth == first_oxygen_depth:
                        return format_tenths(self._oxygen_elapsed_seconds() or 0.0)
                return self._live_stop_display()
            if self.dive._at_stop:
                return self._live_stop_display()
            return self._live_ascent_display()
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return self._clean_time_remaining_text()
        return "--"

    def _line_three_text(self) -> str:
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return "Clean Time Remaining"
        if self.dive.phase is DivePhase.BOTTOM:
            depth = self._parsed_depth()
            return f"Max {depth} fsw" if depth is not None else "Max -- fsw"
        if self.dive.phase is DivePhase.READY:
            depth = self._parsed_depth()
            return f"Max {depth} fsw" if depth is not None else "Max -- fsw"
        depth_display = self._depth_estimate_display()
        return depth_display if depth_display != "--" else "--"

    def _secondary_dive_display(self) -> str:
        summary = self.dive.session.summary()
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
        if self.dive.phase is DivePhase.ASCENT and self.dive._at_stop:
            return "AT STOP"
        if self.dive.phase is DivePhase.ASCENT:
            return "TRAVELING"
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return "CLEAN TIME"
        return self.dive.phase.name

    def _set_screen_visibility(self) -> None:
        if self.mode is DeviceMode.DIVE and self.show_recall:
            self.operate_frame.grid_remove()
            self.recall_frame.grid()
        else:
            self.recall_frame.grid_remove()
            self.operate_frame.grid()

    def _update_recall_view(self) -> None:
        pages = self._build_recall_pages()
        self.recall_page = max(0, min(self.recall_page, len(pages) - 1))
        page = pages[self.recall_page]
        self.recall_title_text.set(page.title)
        for index, variable in enumerate(self.recall_line_vars):
            variable.set(page.lines[index] if index < len(page.lines) else "")
        self.recall_footer_text.set(f"Page {self.recall_page + 1}/{len(pages)}")

    def _build_recall_pages(self) -> list[RecallPage]:
        summary = self.dive.session.summary()
        page_one = RecallPage(
            title="Logs",
            lines=[
                "Event      Clock Time",
                f"LS         {self._compact_event_clock('LS')}",
                f"RB         {self._compact_event_clock('RB')}",
                f"LB         {self._compact_event_clock('LB')}",
                f"RS         {self._compact_event_clock('RS')}",
            ],
        )
        log_lines = self._build_combined_log_lines()
        page_two = RecallPage(
            title="Logs",
            lines=log_lines[:5] if log_lines else ["Proc   Depth   Clock   Time"],
        )
        logic_lines = self._compact_logic_lines()
        page_three = RecallPage(
            title="Summary",
            lines=[
                self._recall_profile_summary_line(),
                self._recall_rb_summary_line(summary),
                self._recall_lb_summary_line(summary),
                self._recall_rs_summary_line(summary),
                logic_lines[0] if logic_lines else self._recall_total_summary_line(summary),
            ],
        )
        return [page_one, page_two, page_three]

    def _compact_event_clock(self, code: str) -> str:
        event = self.dive.session.events.get(code)
        if event is None:
            return "--"
        return event.timestamp.strftime("%H%M")

    def _format_minutes_value(self, value: str | int | None) -> str:
        if value in {None, "--"}:
            return "-- min"
        return f"{int(value):02d} min"

    def _build_combined_log_lines(self) -> list[str]:
        rows = ["Proc   Depth   Clock   Time"]
        entries: list[tuple[datetime, str]] = []

        for event in self.dive.descent_hold_events:
            if event.kind != "start":
                continue
            end_event = next(
                (candidate for candidate in self.dive.descent_hold_events if candidate.index == event.index and candidate.kind == "end"),
                None,
            )
            duration_seconds = (
                (end_event.timestamp - event.timestamp).total_seconds()
                if end_event is not None
                else (self._now() - event.timestamp).total_seconds()
            )
            hold_depth = event.depth_fsw
            if hold_depth is None:
                hold_depth = self._descent_hold_depth_at_start_for_display(event.timestamp)
            depth_text = f"{hold_depth} fsw" if hold_depth is not None else "-- fsw"
            entries.append(
                (
                    event.timestamp,
                    f"H{event.index}   {depth_text}   {event.timestamp.strftime('%H%M')}   {format_minutes_seconds(duration_seconds)}",
                )
            )

        start_events = {
            event.index: event
            for event in self.dive.ascent_delay_events
            if event.kind == "start"
        }
        end_events = {
            event.index: event
            for event in self.dive.ascent_delay_events
            if event.kind == "end"
        }
        for index in sorted(start_events):
            start_event = start_events[index]
            end_event = end_events.get(index)
            duration_seconds = (
                (end_event.timestamp - start_event.timestamp).total_seconds()
                if end_event is not None
                else (self._now() - start_event.timestamp).total_seconds()
            )
            depth_text = f"{start_event.depth_fsw} fsw" if start_event.depth_fsw is not None else "-- fsw"
            entries.append(
                (
                    start_event.timestamp,
                    f"D{index}   {depth_text}   {start_event.timestamp.strftime('%H%M')}   {format_minutes_seconds(duration_seconds)}",
                )
            )

        air_break_starts = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "start"
        }
        air_break_ends = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "end"
        }
        for index in sorted(air_break_starts):
            start_event = air_break_starts[index]
            end_event = air_break_ends.get(index)
            duration_seconds = (
                (end_event.timestamp - start_event.timestamp).total_seconds()
                if end_event is not None
                else (self._now() - start_event.timestamp).total_seconds()
            )
            depth_text = f"{start_event.depth_fsw} fsw" if start_event.depth_fsw is not None else "-- fsw"
            entries.append(
                (
                    start_event.timestamp,
                    f"AB{index}  {depth_text}   {start_event.timestamp.strftime('%H%M')}   {format_minutes_seconds(duration_seconds)}",
                )
            )

        for _timestamp, line in sorted(entries, key=lambda item: item[0]):
            rows.append(line)
        return rows

    def _compact_logic_lines(self) -> list[str]:
        if not self.logic_log_entries:
            return []
        lines: list[str] = []
        for entry in self.logic_log_entries[-2:]:
            if ":" in entry:
                rule, detail = entry.split(":", maxsplit=1)
                compact = f"{rule}: {detail.strip()}"
            else:
                compact = entry
            if len(compact) > 48:
                compact = f"{compact[:45]}..."
            lines.append(compact)
        return lines

    def _recall_profile_summary_line(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return "Profile --/--   --"
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return f"Profile {self._surface_table_summary()}"
        profile = self._active_depth_profile() or self._planned_first_stop_profile()
        if profile is None:
            return "Profile --/--   --"
        return f"Profile {self._profile_line_text(profile)}"

    def _recall_rb_summary_line(self, summary: dict[str, str | int]) -> str:
        depth = self._parsed_depth()
        depth_text = f"{depth} fsw" if depth is not None else "-- fsw"
        return f"RB {self._compact_event_clock('RB')} | DT {self._format_minutes_value(summary.get('DT'))} | MD {depth_text}"

    def _recall_lb_summary_line(self, summary: dict[str, str | int]) -> str:
        return f"LB {self._compact_event_clock('LB')} | BT {self._format_minutes_value(summary.get('BT'))}"

    def _recall_rs_summary_line(self, summary: dict[str, str | int]) -> str:
        return f"RS {self._compact_event_clock('RS')} | TDT {self._format_minutes_value(summary.get('TDT'))}"

    def _recall_total_summary_line(self, summary: dict[str, str | int]) -> str:
        return f"TTD {self._format_minutes_value(summary.get('TTD'))}"

    def _append_logic_log(self, key: tuple[object, ...], line: str) -> None:
        if key in self._logic_log_keys:
            return
        self._logic_log_keys.add(key)
        self.logic_log_entries.append(line)

    def _capture_logic_audit_entries(self) -> None:
        self._capture_first_stop_logic_entry()
        self._capture_between_stops_logic_entry()

    def _capture_first_stop_logic_entry(self) -> None:
        evaluation = self._first_stop_arrival_evaluation()
        first_arrival = self.dive.first_stop_arrival_event()
        if evaluation is None or first_arrival is None:
            return

        key = (
            "first_stop",
            first_arrival.timestamp.isoformat(),
            evaluation.outcome,
            evaluation.rounded_delay_minutes,
            evaluation.active_profile.table_depth_fsw,
            evaluation.active_profile.table_bottom_time_min,
        )
        if evaluation.outcome == "early_arrival":
            rule = "9-11.2.2" if self.decompression_mode is DecompressionMode.AIR_O2 and evaluation.active_profile.first_stop_depth_fsw in {20, 30} else "9-11.2.1"
            if rule == "9-11.2.2":
                line = f"{rule}: early to 1st O2 stop; start after travel complete and divers confirmed on O2"
            else:
                line = f"{rule}: early to 1st stop; start timing when required travel time completes"
            self._append_logic_log(key, line)
            return

        if evaluation.delay_seconds is None or evaluation.delay_seconds <= 0:
            return

        delay_text = format_minutes_seconds(evaluation.delay_seconds)
        if evaluation.delay_seconds <= 60:
            line = f"9-11.3: ignore; delay {delay_text} <=1m to 1st stop"
        elif evaluation.outcome == "add_to_first_stop":
            depth_text = self.delay_to_first_stop_depth_fsw if self.delay_to_first_stop_depth_fsw is not None else "--"
            line = (
                f"9-11.3: +{evaluation.rounded_delay_minutes}m to 1st stop; "
                f"delay @{depth_text}fsw <=50"
            )
        else:
            depth_text = self.delay_to_first_stop_depth_fsw if self.delay_to_first_stop_depth_fsw is not None else "--"
            profile_text = self._profile_line_text(evaluation.active_profile)
            if evaluation.schedule_changed:
                line = f"9-11.3: recompute +{evaluation.rounded_delay_minutes}m @{depth_text}fsw -> {profile_text}"
            else:
                line = f"9-11.3: no change; +{evaluation.rounded_delay_minutes}m @{depth_text}fsw kept {profile_text}"
        self._append_logic_log(key, line)

    def _capture_between_stops_logic_entry(self) -> None:
        profile = self._profile_after_first_stop_evaluation()
        special_o2_entry = self._air_o2_special_delay_log_entry(profile)
        if special_o2_entry is not None:
            self._append_logic_log(*special_o2_entry)
            return
        evaluation = self._between_stops_delay_evaluation(profile)
        if evaluation is None or evaluation.delay_seconds <= 0:
            return

        stop_number = None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is not None:
            stop_number = latest_arrival.stop_number
        key = (
            "between_stops",
            stop_number,
            evaluation.outcome,
            evaluation.rounded_delay_minutes,
            evaluation.delay_depth_fsw,
            evaluation.active_profile.table_depth_fsw,
            evaluation.active_profile.table_bottom_time_min,
        )
        unimplemented_line = self._unimplemented_between_stops_rule_line(profile, evaluation)
        if unimplemented_line is not None:
            self._append_logic_log(key, unimplemented_line)
            return
        delay_text = format_minutes_seconds(evaluation.delay_seconds)
        if evaluation.delay_seconds <= 60:
            line = f"9-11.4: ignore; delay {delay_text} <1m leaving/between stops"
        elif evaluation.delay_depth_fsw <= 50:
            line = f"9-11.4: ignore; delay @{evaluation.delay_depth_fsw}fsw <=50"
        else:
            profile_text = self._profile_line_text(evaluation.active_profile)
            if evaluation.schedule_changed:
                line = f"9-11.4: recompute +{evaluation.rounded_delay_minutes}m -> {profile_text}"
            else:
                line = f"9-11.4: no change; +{evaluation.rounded_delay_minutes}m kept {profile_text}"
        self._append_logic_log(key, line)

    def _unimplemented_between_stops_rule_line(self, profile, evaluation) -> str | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2:
            return None
        if evaluation.delay_seconds <= 0:
            return None
        return None

    def _air_o2_special_delay_log_entry(self, profile) -> tuple[tuple[object, ...], str] | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return None

        if self.dive._at_stop and current_depth == 30:
            anchor_time = self._current_stop_timer_anchor(profile)
            required_seconds = (profile.stops_fsw.get(30) or 0) * 60
            if anchor_time is not None:
                delay_seconds = max(
                    (self._now() - anchor_time).total_seconds()
                    - self._ignored_air_seconds_between(anchor_time, self._now())
                    - required_seconds,
                    0.0,
                )
                if delay_seconds > 0:
                    key = ("o2_stop_30_delay", latest_arrival.timestamp.isoformat(), int(delay_seconds))
                    line = f"9-11.4: subtract {format_minutes_seconds(delay_seconds)} from subsequent 20 fsw O2 stop"
                    return key, line

        latest_departure = self.dive.latest_stop_departure_event()
        if latest_departure is not None and latest_arrival is not None:
            source_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
            destination_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            if source_depth == 30 and destination_depth == 20:
                planned_elapsed_seconds = math.ceil((max(source_depth - destination_depth, 0) / 30) * 60)
                actual_elapsed_seconds = (latest_arrival.timestamp - latest_departure.timestamp).total_seconds()
                if actual_elapsed_seconds > planned_elapsed_seconds:
                    delay_seconds = actual_elapsed_seconds - planned_elapsed_seconds
                    key = ("o2_30_to_20_delay", latest_arrival.timestamp.isoformat(), int(delay_seconds))
                    line = f"9-11.4: 30->20 O2 travel delay {format_minutes_seconds(delay_seconds)} applied to 20 fsw stop"
                    return key, line

        if self.dive._at_stop and current_depth == 20:
            anchor_time = self._current_stop_timer_anchor(profile)
            required_seconds = (profile.stops_fsw.get(20) or 0) * 60
            if anchor_time is not None:
                delay_seconds = max(
                    (self._now() - anchor_time).total_seconds()
                    - self._ignored_air_seconds_between(anchor_time, self._now())
                    - required_seconds,
                    0.0,
                )
                if delay_seconds > 0:
                    key = ("o2_stop_20_delay", latest_arrival.timestamp.isoformat(), int(delay_seconds))
                    if self._oxygen_break_due():
                        line = "9-11.4: delay leaving 20 fsw O2 stop ignored; shift to AIR and remain on AIR until surface"
                    else:
                        line = "9-11.4: delay leaving 20 fsw O2 stop ignored"
                    return key, line

        if self._oxygen_break_due():
            key = ("o2_break_due", latest_arrival.timestamp.isoformat(), latest_arrival.stop_number)
            line = "9-11.4: total O2 deeper than 20 exceeded 30m; shift to AIR and ignore AIR time until O2 resumes"
            return key, line
        return None

    def _summary_line_text(self, status: DivePresentationStatus) -> str:
        if self.mode is not DeviceMode.DIVE:
            return ""
        if status is DivePresentationStatus.READY:
            return self._planned_depth_guidance() or ""
        if status is DivePresentationStatus.DESCENT:
            return self._live_depth_guidance() or ""
        if status is DivePresentationStatus.BOTTOM_NO_DECO:
            return "Next: Surface"
        if status is DivePresentationStatus.BOTTOM_DECO:
            profile = self._planned_first_stop_profile()
            if profile is None:
                return self._live_depth_guidance() or ""
            return self._next_stop_instruction(profile)
        if status in {
            DivePresentationStatus.ASCENT_NO_DECO,
            DivePresentationStatus.ASCENT_DECO_TRAVEL,
            DivePresentationStatus.ASCENT_DECO_STOP,
        }:
            profile = self._active_depth_profile()
            if profile is None:
                return ""
            if profile.section == "no_decompression":
                return "Next: Surface"
            if status is DivePresentationStatus.ASCENT_DECO_STOP and self._active_air_break_event() is not None:
                return self._next_action_after_air_break(profile)
            if self._active_o2_display_mode():
                break_text = self._air_o2_break_line(profile)
                if break_text is not None:
                    return f"Next: 5 min Air break in {break_text.removeprefix("Break In ")}"
            if status is DivePresentationStatus.ASCENT_DECO_STOP and self._can_start_air_break():
                return "Next: 5 min Air break in 00:00"
            if status is DivePresentationStatus.ASCENT_DECO_STOP:
                return self._next_stop_instruction(profile)
            return self._next_stop_instruction(profile)
        if status is DivePresentationStatus.SURFACE:
            return self._surface_table_summary()
        return ""

    def _next_action_after_air_break(self, profile) -> str:
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return self._next_stop_instruction(profile)
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth == 20:
            remaining = self._current_stop_remaining_text(profile)
            return f"Next: 20 fsw for {remaining}"
        return self._next_stop_instruction(profile)

    def _summary_line_targets_oxygen_stop(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.decompression_mode is not DecompressionMode.AIR_O2:
            return False
        profile = self._active_depth_profile()
        if profile is None or profile.section == "no_decompression":
            return False
        return self._next_stop_text(profile) in {"20 fsw", "30 fsw"}

    def _line_five_text(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return ""
        if (
            self.decompression_mode is DecompressionMode.AIR_O2
            and self.dive.phase is DivePhase.ASCENT
            and not self.dive._at_stop
        ):
            return ""
        if (
            self.decompression_mode is DecompressionMode.AIR_O2
            and self.dive.phase is DivePhase.ASCENT
            and self.dive._at_stop
        ):
            return ""
        if self.dive.phase is DivePhase.ASCENT:
            profile = self._active_depth_profile()
            if profile is not None:
                break_text = self._air_o2_break_line(profile)
                if break_text is not None:
                    return f"Next Stop: {self._next_stop_text(profile)}"
                return self._profile_line_text(profile)
        active_event_text = self._active_line_five_event_text()
        return active_event_text or ""

    def _active_line_five_event_text(self) -> str | None:
        if self.mode is not DeviceMode.DIVE:
            return None

        latest_hold = self.dive.latest_stop_event()
        if (
            self.dive.phase is DivePhase.DESCENT
            and self.dive._awaiting_leave_stop
            and latest_hold is not None
        ):
            elapsed = (self._now() - latest_hold.timestamp).total_seconds()
            hold_depth = self._descent_hold_depth_at_start_for_display(latest_hold.timestamp)
            depth_text = f" ({hold_depth} fsw)" if hold_depth is not None else ""
            return f"H{latest_hold.index}{depth_text}   {format_minutes_seconds(elapsed)}"

        active_delay = self._active_ascent_delay_event()
        if self.dive.phase is DivePhase.ASCENT and active_delay is not None and not self.dive._at_stop:
            depth_text = f" ({active_delay.depth_fsw} fsw)" if active_delay.depth_fsw is not None else ""
            elapsed = (self._now() - active_delay.timestamp).total_seconds()
            return f"D{active_delay.index}{depth_text}   {format_minutes_seconds(elapsed)}"

        return None

    def _automatic_first_stop_delay_text(self) -> str | None:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            return None
        if self.dive.first_stop_arrival_event() is not None or self.dive._at_stop:
            return None

        profile = self._planned_first_stop_profile()
        lb_event = self.dive.session.events.get("LB")
        if profile is None or lb_event is None or profile.section == "no_decompression":
            return None

        planned_tt1st = self._planned_tt1st_seconds()
        if planned_tt1st is None:
            return None

        elapsed = (self._now() - lb_event.timestamp).total_seconds()
        if elapsed <= planned_tt1st:
            return None

        return f"Delay {format_minutes_seconds(elapsed - planned_tt1st)}"

    def _air_o2_line_five_text(self) -> str | None:
        if self.mode is not DeviceMode.DIVE or self.decompression_mode is not DecompressionMode.AIR_O2:
            return None
        if self.dive.phase is not DivePhase.ASCENT:
            return None

        profile = self._active_depth_profile()
        if profile is None or profile.section == "no_decompression":
            return None

        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        first_oxygen_stop_depth = shift_plan.first_oxygen_stop_depth_fsw
        if first_oxygen_stop_depth is None:
            return None

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        first_oxygen_stop_number = stop_depths.index(first_oxygen_stop_depth) + 1
        latest_arrival = self.dive.latest_arrival_event()
        latest_departure = self.dive.latest_stop_departure_event()
        if self._active_air_break_event() is not None:
            air_break_elapsed_seconds = self._current_air_break_elapsed_seconds() or 0.0
            resume_in_seconds = max(300 - air_break_elapsed_seconds, 0.0)
            return (
                f"Air Break {format_minutes_seconds(air_break_elapsed_seconds)}   "
                f"Resume In {format_minutes_seconds(resume_in_seconds)}"
            )
        if self.oxygen_segment_started_at is not None:
            oxygen_elapsed_seconds = self._oxygen_elapsed_seconds() or 0.0
            if oxygen_elapsed_seconds >= 1800:
                next_air_break_seconds = max(1800 - oxygen_elapsed_seconds, 0.0)
                return f"O2 {format_minutes_seconds(oxygen_elapsed_seconds)}   Break In {format_minutes_seconds(next_air_break_seconds)}"
            return f"O2 {format_minutes_seconds(oxygen_elapsed_seconds)}"
        if self._awaiting_first_oxygen_confirmation():
            anchor_time = self._first_oxygen_shift_anchor(profile)
            if anchor_time is not None:
                elapsed_seconds = (self._now() - anchor_time).total_seconds()
                return f"Travel/Shift/Vent   {format_minutes_seconds(elapsed_seconds)}"
            return f"Shift to 100% O2 at {first_oxygen_stop_depth} fsw"

        if (
            self.dive._at_stop
            and latest_arrival is not None
            and latest_arrival.stop_number == first_oxygen_stop_number
            and shift_plan.travel_shift_vent_starts_on_arrival
        ):
            return "On 100% O2"

        if (
            latest_departure is not None
            and shift_plan.travel_shift_vent_start_depth_fsw is not None
            and not shift_plan.travel_shift_vent_starts_on_arrival
        ):
            departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
            if departure_depth == shift_plan.travel_shift_vent_start_depth_fsw:
                if latest_arrival is None or latest_arrival.stop_number < first_oxygen_stop_number:
                    if self.first_oxygen_confirmed_at is None:
                        elapsed_seconds = (self._now() - latest_departure.timestamp).total_seconds()
                        return f"Travel/Shift/Vent   {format_minutes_seconds(elapsed_seconds)}"
                    return "On 100% O2"

        if latest_arrival is not None and latest_arrival.stop_number >= first_oxygen_stop_number:
            return "Shifted to 100% O2"

        if shift_plan.travel_shift_vent_starts_on_arrival:
            return f"Shift to 100% O2 at {first_oxygen_stop_depth} fsw"

        start_depth = shift_plan.travel_shift_vent_start_depth_fsw
        if start_depth is not None:
            return f"Leaving {start_depth} fsw starts Travel/Shift/Vent"
        return f"Shift to 100% O2 at {first_oxygen_stop_depth} fsw"

    def _current_procedure_line_text(self, profile) -> str | None:
        oxygen_warning = self._air_o2_oxygen_rule_warning_text(profile)
        if oxygen_warning is not None:
            return oxygen_warning
        active_event_text = self._active_line_five_event_text()
        if active_event_text is not None:
            return active_event_text
        automatic_delay_text = self._automatic_first_stop_delay_text()
        if automatic_delay_text is not None:
            return automatic_delay_text
        return self._air_o2_line_five_text() if profile.mode is DecompressionMode.AIR_O2 else None

    def _air_o2_oxygen_rule_warning_text(self, profile) -> str | None:
        if profile.mode is not DecompressionMode.AIR_O2:
            return None
        if self._active_air_break_event() is not None:
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return None

        if self._oxygen_break_due():
            if self.dive._at_stop and current_depth == 20 and self._current_stop_remaining_text(profile) == "00:00":
                return "Shift to AIR; remain on AIR until surface"
            if current_depth in {20, 30}:
                return "Shift to AIR at 30:00; ignore AIR time"
        return None

    def _profile_line_text(self, profile) -> str:
        if profile.section == "no_decompression":
            bt_minutes = self.dive.session.bottom_time_minutes()
            repet_group, schedule_time = lookup_repetitive_group_schedule(profile.table_depth_fsw, bt_minutes)
            return f"{profile.table_depth_fsw}/{schedule_time}   {repet_group}"
        return f"{self._table_schedule_text(profile)}   {profile.repeat_group or '--'}"

    def _stop_depth_remaining_display(self) -> str:
        profile = self._active_depth_profile()
        if profile is None or profile.section == "no_decompression" or not self.dive._at_stop:
            return self._depth_estimate_display()
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return self._depth_estimate_display()
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return self._depth_estimate_display()
        balance_seconds = self._current_stop_balance_seconds(profile)
        if balance_seconds is None:
            return self._depth_estimate_display()
        if balance_seconds >= 0:
            balance_text = f"{format_minutes_seconds(balance_seconds)} left"
        else:
            balance_text = f"+{format_minutes_seconds(abs(balance_seconds))}"
        return f"{current_depth} fsw | {balance_text}"

    def _ascent_travel_depth_display(self) -> str:
        depth_text = self._depth_estimate_display()
        profile = self._active_depth_profile()
        if (
            profile is None
            or profile.section == "no_decompression"
            or self.dive.phase is not DivePhase.ASCENT
            or self.dive._at_stop
        ):
            return depth_text
        o2_remaining_text = self._air_o2_travel_to_20_remaining_text(profile)
        if o2_remaining_text is not None:
            return f"{depth_text} | {o2_remaining_text} left"
        delay_text = self._delay_timer_text(profile)
        if delay_text == "00:00":
            return depth_text
        return f"{depth_text} | +{delay_text} delay"

    def _air_o2_travel_to_20_remaining_text(self, profile) -> str | None:
        if (
            profile is None
            or profile.mode is not DecompressionMode.AIR_O2
            or profile.section == "no_decompression"
            or self.dive.phase is not DivePhase.ASCENT
            or self.dive._at_stop
        ):
            return None
        latest_departure = self.dive.latest_stop_departure_event()
        if latest_departure is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        next_depth = self._next_stop_depth(stop_depths, latest_departure.stop_number)
        if departure_depth != 30 or next_depth != 20:
            return None
        remaining_seconds = self._remaining_oxygen_obligation_seconds(profile)
        if remaining_seconds is None:
            return None
        return format_minutes_seconds(remaining_seconds)

    def _air_break_depth_display(self) -> str:
        profile = self._active_depth_profile()
        active_break = self._active_air_break_event()
        if profile is None or active_break is None or not self.dive._at_stop:
            return self._stop_depth_remaining_display()
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return self._stop_depth_remaining_display()
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return self._stop_depth_remaining_display()
        elapsed = self._current_air_break_elapsed_seconds() or 0.0
        left = max(300 - elapsed, 0.0)
        return f"{current_depth} fsw | {format_minutes_seconds(left)} left"

    def _awaiting_o2_depth_display(self) -> str:
        profile = self._active_depth_profile()
        if profile is None or not self._awaiting_first_oxygen_confirmation():
            return self._stop_depth_remaining_display()
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return self._depth_estimate_display()
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return self._depth_estimate_display()
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        if shift_plan.travel_shift_vent_starts_on_arrival:
            return f"{current_depth} fsw"
        dead_seconds = max((self._now() - latest_arrival.timestamp).total_seconds(), 0.0)
        return f"{current_depth} fsw | +{format_minutes_seconds(dead_seconds)} dead time"

    def _bottom_depth_status_text(self) -> str | None:
        depth = self._parsed_depth()
        ls_event = self.dive.session.events.get("LS")
        if depth is None or ls_event is None:
            return None
        elapsed_seconds = max((self._now() - ls_event.timestamp).total_seconds(), 0.0)
        profile = self._planned_first_stop_profile()
        if profile is None:
            return f"{depth} fsw"
        if profile.section == "no_decompression":
            _table_depth, limit = lookup_no_decompression_limit_for_depth(depth)
            if limit is None:
                return f"{depth} fsw"
            remaining_seconds = max((limit * 60) - elapsed_seconds, 0.0)
            return f"{depth} fsw | {format_minutes_seconds(remaining_seconds)} left"
        remaining_seconds = max((profile.table_bottom_time_min * 60) - elapsed_seconds, 0.0)
        return f"{depth} fsw | {format_minutes_seconds(remaining_seconds)} left"

    def _current_stop_timer_anchor(self, profile) -> datetime | None:
        if profile is None or not self.dive._at_stop:
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        first_oxygen_number = self._first_oxygen_stop_number(profile)
        if (
            profile.mode is DecompressionMode.AIR_O2
            and latest_arrival.stop_number == first_oxygen_number
        ):
            return self.first_oxygen_confirmed_at
        if latest_arrival.stop_number == 1:
            if (
                profile.mode is DecompressionMode.AIR_O2
                and first_oxygen_number == 1
                and self.first_oxygen_confirmed_at is not None
            ):
                return self.first_oxygen_confirmed_at
            return latest_arrival.timestamp
        previous_departure = next(
            (
                event
                for event in reversed(self.dive.ascent_stop_events)
                if event.kind == "leave" and event.stop_number == latest_arrival.stop_number - 1
            ),
            None,
        )
        # For every stop after the first, stop time starts when the previous
        # stop is left. If that leave event is missing, fail closed instead of
        # silently restarting timing from arrival.
        if previous_departure is None:
            return None
        return previous_departure.timestamp

    def _first_oxygen_stop_number(self, profile) -> int | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2:
            return None
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        if shift_plan.first_oxygen_stop_depth_fsw is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        return stop_depths.index(shift_plan.first_oxygen_stop_depth_fsw) + 1

    def _first_oxygen_shift_anchor(self, profile) -> datetime | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2:
            return None
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        if shift_plan.first_oxygen_stop_depth_fsw is None:
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if shift_plan.travel_shift_vent_starts_on_arrival:
            return latest_arrival.timestamp if latest_arrival is not None else None
        latest_departure = self.dive.latest_stop_departure_event()
        if latest_departure is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        if departure_depth == shift_plan.travel_shift_vent_start_depth_fsw:
            return latest_departure.timestamp
        return None

    def _awaiting_first_oxygen_confirmation(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT or not self.dive._at_stop:
            return False
        profile = self._active_depth_profile()
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return False
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return False
        first_oxygen_number = self._first_oxygen_stop_number(profile)
        if first_oxygen_number is None or latest_arrival.stop_number != first_oxygen_number:
            return False
        return self.first_oxygen_confirmed_at is None or self.first_oxygen_confirmed_stop_number != latest_arrival.stop_number

    def _show_tsv_on_primary_display(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            return False
        profile = self._active_depth_profile()
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return False
        if self.first_oxygen_confirmed_at is not None:
            return False
        shift_plan = build_air_o2_oxygen_shift_plan(profile)
        anchor_time = self._first_oxygen_shift_anchor(profile)
        if anchor_time is None:
            return False
        if shift_plan.travel_shift_vent_start_depth_fsw == 40:
            return True
        return self._awaiting_first_oxygen_confirmation()

    def _live_tsv_display(self) -> str:
        profile = self._active_depth_profile()
        if profile is None:
            return "--:--"
        anchor_time = self._first_oxygen_shift_anchor(profile)
        if anchor_time is None:
            return "00:00 TSV"
        elapsed_seconds = max((self._now() - anchor_time).total_seconds(), 0.0)
        return f"{format_minutes_seconds(elapsed_seconds)} TSV"

    def _surface_table_summary(self) -> str:
        profile = self._active_depth_profile() or self._planned_first_stop_profile()
        if profile is None:
            return "--/--   --"
        if profile.section == "no_decompression":
            bt_minutes = self.dive.session.bottom_time_minutes()
            repet_group, schedule_time = lookup_repetitive_group_schedule(profile.table_depth_fsw, bt_minutes)
            return f"{profile.table_depth_fsw}/{schedule_time}   {repet_group}"
        return f"{self._table_schedule_text(profile)}   {profile.repeat_group or '--'}"

    def _depth_estimate_display(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return "--"
        depth = self._parsed_depth()
        if self.dive.phase is DivePhase.DESCENT:
            estimate = self._estimated_current_depth(depth)
            if estimate is None:
                return "0 fsw"
            return f"{estimate} fsw"
        if depth is None:
            return "--"
        if self.dive.phase is DivePhase.BOTTOM:
            return f"{depth} fsw"
        estimate = self._estimated_current_depth(depth)
        if estimate is None:
            return "--"
        return f"{estimate} fsw"

    def _estimated_current_depth(self, max_depth_fsw: int | None) -> int | None:
        if self.dive.phase is DivePhase.DESCENT:
            ls_event = self.dive.session.events.get("LS")
            if ls_event is None:
                return None
            latest_hold = self.dive.latest_stop_event()
            target_depth = max_depth_fsw if max_depth_fsw is not None else 10_000
            if self.dive._awaiting_leave_stop and latest_hold is not None:
                return self._descent_hold_depth_at_start(target_depth, latest_hold.timestamp, round_up=False)
            anchor_time = ls_event.timestamp
            anchor_depth = 0
            if latest_hold is not None and latest_hold.kind == "end":
                hold_depth = self._descent_hold_depth_at_end(target_depth, latest_hold.index)
                if hold_depth is None:
                    return None
                anchor_time = latest_hold.timestamp
                anchor_depth = hold_depth
            return self._interpolate_depth_at_rate(
                anchor_depth,
                target_depth,
                anchor_time,
                self._now(),
                60.0,
                round_up=False,
            )

        if self.dive.phase is not DivePhase.ASCENT:
            return None

        if max_depth_fsw is None:
            return None

        profile = self._active_depth_profile()
        if profile is None:
            return None

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        latest_departure = self.dive.latest_stop_departure_event()
        latest_arrival = self.dive.latest_arrival_event()
        first_stop_arrival = self.dive.first_stop_arrival_event()
        lb_event = self.dive.session.events.get("LB")
        active_delay = self._active_ascent_delay_event()

        if first_stop_arrival is None:
            if lb_event is None:
                return None
            if active_delay is not None and active_delay.depth_fsw is not None:
                return active_delay.depth_fsw
            destination = stop_depths[0] if stop_depths else 0
            return self._interpolate_depth(max_depth_fsw, destination, lb_event.timestamp)

        if self.dive._at_stop and latest_arrival is not None:
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            return current_depth if current_depth is not None else None

        if latest_departure is not None:
            if active_delay is not None and active_delay.depth_fsw is not None:
                return active_delay.depth_fsw
            source_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
            destination = self._next_stop_depth(stop_depths, latest_departure.stop_number)
            if source_depth is None:
                return None
            return self._interpolate_depth(source_depth, destination, latest_departure.timestamp)

        current_depth = self._stop_depth_for_number(stop_depths, first_stop_arrival.stop_number)
        return current_depth if current_depth is not None else None

    def _active_depth_profile(self):
        profile = self._profile_after_first_stop_evaluation()
        if profile is None:
            return None
        evaluation = self._between_stops_delay_evaluation(profile)
        if evaluation is not None:
            return evaluation.active_profile
        return profile

    def _profile_after_first_stop_evaluation(self):
        planned_profile = self._planned_first_stop_profile()
        if planned_profile is None:
            return None
        evaluation = self._first_stop_arrival_evaluation()
        if evaluation is not None:
            return evaluation.active_profile
        return planned_profile

    def _interpolate_depth(self, source_depth: int, destination_depth: int, anchor_time: datetime) -> int:
        return self._interpolate_depth_at(source_depth, destination_depth, anchor_time, self._now())

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

    def _descent_hold_depth_at_start(
        self,
        max_depth_fsw: int,
        start_time: datetime,
        round_up: bool = True,
    ) -> int | None:
        ls_event = self.dive.session.events.get("LS")
        if ls_event is None:
            return None

        previous_leave = next(
            (
                event
                for event in reversed(self.dive.descent_hold_events)
                if event.kind == "end" and event.timestamp <= start_time
            ),
            None,
        )
        if previous_leave is None:
            return self._interpolate_depth_at_rate(
                0,
                max_depth_fsw,
                ls_event.timestamp,
                start_time,
                60.0,
                round_up=round_up,
            )

        previous_start = next(
            (
                event
                for event in self.dive.descent_hold_events
                if event.kind == "start" and event.index == previous_leave.index
            ),
            None,
        )
        if previous_start is None:
            return None
        anchor_depth = self._descent_hold_depth_at_start(max_depth_fsw, previous_start.timestamp, round_up=round_up)
        if anchor_depth is None:
            return None
        return self._interpolate_depth_at_rate(
            anchor_depth,
            max_depth_fsw,
            previous_leave.timestamp,
            start_time,
            60.0,
            round_up=round_up,
        )

    def _descent_hold_depth_at_start_for_display(self, start_time: datetime) -> int | None:
        max_depth_fsw = self._parsed_depth()
        target_depth = max_depth_fsw if max_depth_fsw is not None else 10_000
        return self._descent_hold_depth_at_start(target_depth, start_time, round_up=False)

    def _descent_hold_depth_at_end(self, max_depth_fsw: int, stop_number: int) -> int | None:
        start_event = next(
            (
                event
                for event in self.dive.descent_hold_events
                if event.kind == "start" and event.index == stop_number
            ),
            None,
        )
        if start_event is None:
            return None
        return self._descent_hold_depth_at_start(max_depth_fsw, start_event.timestamp, round_up=False)

    def _live_descent_display(self) -> str:
        ls_event = self.dive.session.events.get("LS")
        if ls_event is None:
            return "Awaiting LS"

        latest_hold = self.dive.latest_stop_event()
        if self.dive._awaiting_leave_stop and latest_hold is not None:
            elapsed = (self._now() - latest_hold.timestamp).total_seconds()
            return format_tenths(elapsed)

        return self._live_total_display()

    def _interpolate_depth_at(
        self,
        source_depth: int,
        destination_depth: int,
        anchor_time: datetime,
        target_time: datetime,
    ) -> int:
        return self._interpolate_depth_at_rate(source_depth, destination_depth, anchor_time, target_time, 30.0)

    def _interpolate_depth_at_rate(
        self,
        source_depth: int,
        destination_depth: int,
        anchor_time: datetime,
        target_time: datetime,
        rate_fsw_per_minute: float,
        round_up: bool = True,
    ) -> int:
        elapsed_seconds = max((target_time - anchor_time).total_seconds(), 0.0)
        depth_delta = elapsed_seconds * (rate_fsw_per_minute / 60.0)
        if destination_depth >= source_depth:
            current_depth = source_depth + depth_delta
            clamped_depth = min(destination_depth, current_depth)
        else:
            current_depth = source_depth - depth_delta
            clamped_depth = max(destination_depth, current_depth)
        if round_up:
            return max(int(math.ceil(clamped_depth)), 0)
        return max(int(clamped_depth), 0)

    def _guidance_or_clean_time_text(self) -> str:
        if self.mode is not DeviceMode.DIVE:
            return "CT --:--"

        if self.dive.phase is DivePhase.CLEAN_TIME:
            return self._clean_time_text()

        if self.dive.phase is DivePhase.READY:
            return self._planned_depth_guidance() or "Input Max Depth for table / schedule"

        if self.dive.phase is DivePhase.ASCENT:
            return self._ascent_schedule_status_text()

        if self.dive.phase in {DivePhase.DESCENT, DivePhase.BOTTOM}:
            if self.dive.phase is DivePhase.BOTTOM:
                return self._live_depth_guidance() or "Press mode to input Max Depth"
            return self._live_depth_guidance() or "Input Max Depth for table / schedule"
        return "Deco info available after RB."

    def _clean_time_remaining_text(self) -> str:
        if self.dive.clean_time is None:
            return "10:00"

        status = self.dive.clean_time_status(self._now())
        return status["CT"]

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
        elapsed = (self._now() - ls_event.timestamp).total_seconds()
        return format_tenths(elapsed)

    def _live_ascent_display(self) -> str:
        active_delay = self._active_ascent_delay_event()
        if active_delay is not None and not self.dive._at_stop:
            elapsed = (self._now() - active_delay.timestamp).total_seconds()
            return format_tenths(elapsed)

        profile = self._active_depth_profile()
        if profile is not None and profile.section != "no_decompression":
            latest_departure = self.dive.latest_stop_departure_event()
            first_stop_arrival = self.dive.first_stop_arrival_event()
            if first_stop_arrival is not None and latest_departure is not None:
                elapsed = (self._now() - latest_departure.timestamp).total_seconds()
                return format_tenths(elapsed)

        lb_event = self.dive.session.events.get("LB")
        if lb_event is None:
            return "--:--.-"
        elapsed = (self._now() - lb_event.timestamp).total_seconds()
        return format_tenths(elapsed)

    def _live_stop_display(self) -> str:
        profile = self._active_depth_profile()
        if profile is None or profile.section == "no_decompression":
            latest_arrival = self.dive.latest_arrival_event()
            if latest_arrival is None:
                return "--:--.-"
            return format_tenths((self._now() - latest_arrival.timestamp).total_seconds())
        anchor_time = self._current_stop_timer_anchor(profile)
        if anchor_time is None:
            return "--:--.-"
        elapsed_seconds = max((self._now() - anchor_time).total_seconds(), 0.0)
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is not None:
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            if profile.mode is DecompressionMode.AIR_O2 and current_depth in {20, 30}:
                elapsed_seconds = max(
                    elapsed_seconds - self._ignored_air_seconds_between(anchor_time, self._now()),
                    0.0,
                )
        return format_tenths(elapsed_seconds)

    def _active_ascent_delay_event(self):
        latest = self.dive.latest_ascent_delay_event()
        if latest is None or latest.kind != "start":
            return None
        return latest

    def _live_tt1st_display(self) -> str:
        planned_seconds = self._planned_tt1st_seconds()
        lb_event = self.dive.session.events.get("LB")
        if planned_seconds is None or lb_event is None:
            return "--:--.-"

        elapsed_seconds = (self._now() - lb_event.timestamp).total_seconds()
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

    def _planned_depth_guidance(self) -> str | None:
        depth = self._parsed_depth()
        if depth is None:
            return None

        try:
            table_depth, no_d_limit = lookup_no_decompression_limit_for_depth(depth)
        except (KeyError, ValueError):
            return f"Depth {depth} fsw not supported yet."

        if no_d_limit is None:
            return f"No-D Limit {table_depth}/Unlimited   --"

        repet_group = lookup_repetitive_group(table_depth, no_d_limit)
        return f"No-D Limit {table_depth}/{no_d_limit}   {repet_group}"

    def _live_depth_guidance(self) -> str | None:
        depth = self._parsed_depth()
        ls_event = self.dive.session.events.get("LS")
        if depth is None or ls_event is None:
            return None

        try:
            table_depth, no_d_limit = lookup_no_decompression_limit_for_depth(depth)
        except (KeyError, ValueError):
            elapsed_minutes = ceil_minutes((self._now() - ls_event.timestamp).total_seconds())
            try:
                profile = build_basic_decompression_profile(self.decompression_mode, depth, elapsed_minutes)
            except (KeyError, ValueError):
                return f"Depth {depth} fsw not supported yet."

            if profile.section == "no_decompression":
                return f"Depth {depth} fsw not supported yet."

            return (
                f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
                f"DST: {profile.first_stop_time_min} min"
            )

        if no_d_limit is None:
            return f"No-D Limit: {table_depth}/Unlimited"

        elapsed_minutes = ceil_minutes((self._now() - ls_event.timestamp).total_seconds())
        if elapsed_minutes <= no_d_limit:
            return f"No-D Limit: {table_depth}/{no_d_limit}"

        profile = build_basic_decompression_profile(self.decompression_mode, depth, elapsed_minutes)
        if profile.section == "no_decompression":
            return f"No-D Limit: {table_depth}/{no_d_limit} [{profile.repeat_group}]"

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
            planned_tt1st_seconds = self._planned_tt1st_seconds()
            if planned_tt1st_seconds is None:
                return (
                    f"1st Stop: {profile.first_stop_depth_fsw} fsw   "
                    f"DST: {profile.first_stop_time_min} min"
                )
            elapsed_seconds = (self._now() - lb_event.timestamp).total_seconds()
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
                self._now() - lb_event.timestamp
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
        delay_status = self._delay_status_text()
        if delay_status is not None:
            return delay_status
        profile = self._active_depth_profile()
        if profile is None:
            return "--/--   --   Next Stop: --"

        table_text = self._table_schedule_text(profile)
        repet_text = profile.repeat_group or "--"
        next_stop_text = self._next_stop_text(profile)
        return f"{table_text}   {repet_text}   Next Stop: {next_stop_text}"

    def _delay_timer_text(self, profile) -> str:
        if self.dive.phase is not DivePhase.ASCENT:
            return ""
        if self.dive._at_stop:
            latest_arrival = self.dive.latest_arrival_event()
            elapsed = (self._now() - latest_arrival.timestamp).total_seconds() if latest_arrival is not None else 0.0
            return format_minutes_seconds(elapsed)
        first_stop_arrival = self.dive.first_stop_arrival_event()
        if first_stop_arrival is not None:
            latest_departure = self.dive.latest_stop_departure_event()
            if latest_departure is None:
                return "00:00"
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            source_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
            destination_depth = self._next_stop_depth(stop_depths, latest_departure.stop_number)
            if source_depth is None:
                return "00:00"
            planned_seconds = math.ceil((max(source_depth - destination_depth, 0) / 30) * 60)
            elapsed = (self._now() - latest_departure.timestamp).total_seconds()
            if elapsed <= planned_seconds:
                return "00:00"
            return format_minutes_seconds(elapsed - planned_seconds)
        planned_tt1st = self._planned_tt1st_seconds()
        lb_event = self.dive.session.events.get("LB")
        if planned_tt1st is None or lb_event is None:
            return "00:00"
        elapsed = (self._now() - lb_event.timestamp).total_seconds()
        if elapsed <= planned_tt1st:
            return "00:00"
        return format_minutes_seconds(elapsed - planned_tt1st)

    def _current_stop_required_time(self, profile) -> str:
        if profile.section == "no_decompression":
            return "--"
        if self.dive._at_stop:
            latest_arrival = self.dive.latest_arrival_event()
            if latest_arrival is None:
                return f"{profile.first_stop_time_min}m" if profile.first_stop_time_min is not None else "--"
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            if current_depth is None:
                return "--"
            stop_time = profile.stops_fsw.get(current_depth)
            return f"{stop_time}m" if stop_time is not None else "--"
        next_stop = self._next_stop_text(profile)
        if next_stop == "Surface":
            return "--"
        next_depth = int(next_stop.split()[0])
        stop_time = profile.stops_fsw.get(next_depth)
        return f"{stop_time}m" if stop_time is not None else "--"

    def _next_stop_required_time(self, profile) -> str:
        if profile.section == "no_decompression":
            return "--"
        next_stop = self._next_stop_text(profile)
        if next_stop == "Surface":
            return "--"
        next_depth = int(next_stop.split()[0])
        stop_time = profile.stops_fsw.get(next_depth)
        return f"{stop_time}m" if stop_time is not None else "--"

    def _next_stop_instruction(self, profile) -> str:
        next_stop = self._next_stop_text(profile)
        next_time = self._next_stop_required_time(profile)
        if next_stop == "Surface" or next_time == "--":
            return f"Next: {next_stop}"
        return f"Next: {next_stop} for {next_time}"

    def _current_stop_remaining_text(self, profile) -> str:
        balance_seconds = self._current_stop_balance_seconds(profile)
        if balance_seconds is None:
            return "--:--"
        return format_minutes_seconds(max(balance_seconds, 0.0))

    def _air_o2_break_line(self, profile) -> str | None:
        if not self._active_o2_display_mode() or not self.dive._at_stop:
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth != 20:
            return None
        remaining_oxygen_seconds = self._remaining_oxygen_obligation_seconds(profile)
        oxygen_elapsed = self._oxygen_elapsed_seconds()
        if remaining_oxygen_seconds is None or oxygen_elapsed is None:
            return None
        total_segment_seconds = remaining_oxygen_seconds + oxygen_elapsed
        if total_segment_seconds <= (35 * 60):
            return None
        break_in_seconds = max(1800 - oxygen_elapsed, 0.0)
        return f"Break In {format_minutes_seconds(break_in_seconds)}"

    def _remaining_oxygen_obligation_seconds(self, profile) -> float | None:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)

        if not self.dive._at_stop:
            latest_departure = self.dive.latest_stop_departure_event()
            if latest_departure is None:
                return None
            departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
            next_depth = self._next_stop_depth(stop_depths, latest_departure.stop_number)
            if departure_depth != 30 or next_depth != 20:
                return None
            stop_20_seconds = (profile.stops_fsw.get(20) or 0) * 60
            credited_seconds = self._air_o2_credit_to_20_stop_seconds(profile)
            elapsed_seconds = max(
                (self._now() - latest_departure.timestamp).total_seconds()
                - self._ignored_air_seconds_between(latest_departure.timestamp, self._now()),
                0.0,
            )
            return max(stop_20_seconds - credited_seconds - elapsed_seconds, 0.0)

        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth not in {20, 30}:
            return None

        current_balance = max(self._current_stop_balance_seconds(profile) or 0.0, 0.0)
        future_seconds = 0.0
        for depth, stop_time in profile.stops_fsw.items():
            if depth < current_depth and depth in {20, 30}:
                future_seconds += stop_time * 60

        if current_depth == 30:
            future_seconds = max(future_seconds - self._air_o2_accrued_credit_to_20_stop_seconds(profile), 0.0)

        return current_balance + future_seconds

    def _current_stop_balance_seconds(self, profile) -> float | None:
        if profile.section == "no_decompression" or not self.dive._at_stop:
            return None
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth is None:
            return None
        required_stop_time = profile.stops_fsw.get(current_depth)
        if required_stop_time is None:
            return None
        anchor_time = self._current_stop_timer_anchor(profile)
        if anchor_time is None:
            return None
        elapsed_seconds = max((self._now() - anchor_time).total_seconds(), 0.0)
        if profile.mode is DecompressionMode.AIR_O2 and current_depth in {20, 30}:
            elapsed_seconds = max(
                elapsed_seconds - self._ignored_air_seconds_between(anchor_time, self._now()),
                0.0,
            )
        balance_seconds = (required_stop_time * 60) - elapsed_seconds
        if profile.mode is DecompressionMode.AIR_O2 and current_depth == 20:
            balance_seconds -= self._air_o2_credit_to_20_stop_seconds(profile)
        return balance_seconds

    def _air_o2_credit_to_20_stop_seconds(self, profile) -> float:
        if profile.mode is not DecompressionMode.AIR_O2:
            return 0.0
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        if 20 not in stop_depths or 30 not in stop_depths:
            return 0.0
        stop_30_number = stop_depths.index(30) + 1
        arrival_30 = next(
            (
                event
                for event in self.dive.ascent_stop_events
                if event.kind == "reach" and event.stop_number == stop_30_number
            ),
            None,
        )
        departure_30 = next(
            (
                event
                for event in self.dive.ascent_stop_events
                if event.kind == "leave" and event.stop_number == stop_30_number
            ),
            None,
        )
        if arrival_30 is None or departure_30 is None or self.first_oxygen_confirmed_at is None:
            return 0.0
        planned_30_seconds = (profile.stops_fsw.get(30) or 0) * 60
        actual_30_seconds = max(
            (departure_30.timestamp - self.first_oxygen_confirmed_at).total_seconds()
            - self._ignored_air_seconds_between(self.first_oxygen_confirmed_at, departure_30.timestamp),
            0.0,
        )
        return max(actual_30_seconds - planned_30_seconds, 0.0)

    def _air_o2_accrued_credit_to_20_stop_seconds(self, profile) -> float:
        if profile.mode is not DecompressionMode.AIR_O2 or self.first_oxygen_confirmed_at is None:
            return 0.0
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return 0.0
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth != 30:
            return 0.0
        planned_30_seconds = (profile.stops_fsw.get(30) or 0) * 60
        elapsed_30_seconds = max(
            (self._now() - self.first_oxygen_confirmed_at).total_seconds()
            - self._ignored_air_seconds_between(self.first_oxygen_confirmed_at, self._now()),
            0.0,
        )
        return max(elapsed_30_seconds - planned_30_seconds, 0.0)

    def _oxygen_elapsed_seconds(self) -> float | None:
        if self.oxygen_segment_started_at is None or self._active_air_break_event() is not None:
            return None
        return max((self._now() - self.oxygen_segment_started_at).total_seconds(), 0.0)

    def _oxygen_break_due(self) -> bool:
        oxygen_elapsed = self._oxygen_elapsed_seconds()
        return oxygen_elapsed is not None and oxygen_elapsed >= 1800

    def _active_o2_display_mode(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            return False
        if self._active_air_break_event() is not None:
            return False
        profile = self._active_depth_profile()
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return False
        if self.oxygen_segment_started_at is None:
            return False

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        latest_arrival = self.dive.latest_arrival_event()
        if self.dive._at_stop:
            if latest_arrival is None:
                return False
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            return current_depth in {20, 30}

        latest_departure = self.dive.latest_stop_departure_event()
        if latest_departure is None:
            return False
        departure_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        next_depth = self._next_stop_depth(stop_depths, latest_departure.stop_number)
        return departure_depth in {20, 30} and next_depth in {20, 0}

    def _active_air_break_event(self) -> AirBreakEvent | None:
        starts = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "start"
        }
        ends = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "end"
        }
        active_indices = [index for index in starts if index not in ends]
        if not active_indices:
            return None
        return starts[max(active_indices)]

    def _current_air_break_elapsed_seconds(self) -> float | None:
        active_break = self._active_air_break_event()
        if active_break is None:
            return None
        return max((self._now() - active_break.timestamp).total_seconds(), 0.0)

    def _ignored_air_seconds_between(self, start_time: datetime, end_time: datetime) -> float:
        ignored_seconds = 0.0
        start_events = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "start"
        }
        end_events = {
            event.index: event
            for event in self.air_break_events
            if event.kind == "end"
        }
        for index, start_event in start_events.items():
            interval_end = end_events.get(index).timestamp if index in end_events else self._now()
            overlap_start = max(start_time, start_event.timestamp)
            overlap_end = min(end_time, interval_end)
            if overlap_end > overlap_start:
                ignored_seconds += (overlap_end - overlap_start).total_seconds()
        return ignored_seconds

    def _should_shift_to_air_for_surface(self, profile) -> bool:
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or not self.dive._at_stop:
            return False
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return False
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        return current_depth == 20 and self._oxygen_break_due() and self._current_stop_remaining_text(profile) == "00:00"

    def _can_start_air_break(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT or not self.dive._at_stop:
            return False
        if self._active_air_break_event() is not None or self._awaiting_first_oxygen_confirmation():
            return False
        profile = self._active_depth_profile()
        if profile is None or profile.mode is not DecompressionMode.AIR_O2 or profile.section == "no_decompression":
            return False
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return False
        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if current_depth not in {20, 30}:
            return False
        if self.oxygen_segment_started_at is None or not self._oxygen_break_due():
            return False
        if current_depth == 20 and self._current_stop_remaining_text(profile) == "00:00":
            return False
        return True

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
        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return f"{profile.first_stop_depth_fsw} fsw" if profile.first_stop_depth_fsw is not None else "--"

        if self.dive._at_stop:
            next_depth = self._next_stop_depth(stop_depths, latest_arrival.stop_number)
            return "Surface" if next_depth == 0 else f"{next_depth} fsw"

        next_depth = self._next_stop_depth(stop_depths, latest_arrival.stop_number)
        return "Surface" if next_depth == 0 else f"{next_depth} fsw"

    def _planned_first_stop_profile(self):
        depth = self._parsed_depth()
        if depth is None:
            return None
        try:
            if self.dive.phase is DivePhase.BOTTOM:
                ls_event = self.dive.session.events.get("LS")
                if ls_event is None:
                    return None
                elapsed_minutes = ceil_minutes((self._now() - ls_event.timestamp).total_seconds())
                return build_basic_decompression_profile(self.decompression_mode, depth, elapsed_minutes)
            if self.dive.session.events.get("LB") is None:
                return None
            return build_basic_decompression_profile_for_session(self.decompression_mode, depth, self.dive.session)
        except (KeyError, ValueError, RuntimeError):
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
                delay_depth_fsw=self.delay_to_first_stop_depth_fsw,
                mode=self.decompression_mode,
            )
        except (KeyError, ValueError):
            return None

    def _is_no_decompression_ascent(self) -> bool:
        profile = self._planned_first_stop_profile()
        return profile is not None and profile.section == "no_decompression"

    def _start_stop_reaches_surface(self) -> bool:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            return False
        if self.dive._at_stop:
            return False
        profile = self._active_depth_profile()
        if profile is None:
            return True
        if profile.section == "no_decompression":
            return True
        return not self._has_more_decompression_stops(profile)

    def _has_more_decompression_stops(self, profile) -> bool:
        if profile is None or profile.section == "no_decompression":
            return False
        return self._next_stop_text(profile) != "Surface"

    def _capture_delay_to_first_stop_depth(self) -> None:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            self.delay_to_first_stop_depth_fsw = None
            return
        if self.dive.first_stop_arrival_event() is not None:
            return
        profile = self._planned_first_stop_profile()
        if profile is None or profile.section == "no_decompression":
            self.delay_to_first_stop_depth_fsw = None
            return
        planned_seconds = self._planned_tt1st_seconds()
        lb_event = self.dive.session.events.get("LB")
        depth = self._parsed_depth()
        if planned_seconds is None or lb_event is None or depth is None:
            return
        elapsed_seconds = (self._now() - lb_event.timestamp).total_seconds()
        if elapsed_seconds <= planned_seconds or self.delay_to_first_stop_depth_fsw is not None:
            return
        current_depth = self._estimated_current_depth(depth)
        if current_depth is not None:
            self.delay_to_first_stop_depth_fsw = current_depth

    def _capture_between_stops_delay_depth(self) -> None:
        if self.mode is not DeviceMode.DIVE or self.dive.phase is not DivePhase.ASCENT:
            self.between_stops_delay_depth_fsw = None
            return
        profile = self._profile_after_first_stop_evaluation()
        if profile is None or profile.section == "no_decompression":
            self.between_stops_delay_depth_fsw = None
            return
        if self.dive.first_stop_arrival_event() is None:
            self.between_stops_delay_depth_fsw = None
            return

        if self.dive._at_stop:
            if self.between_stops_delay_depth_fsw is not None:
                return
            latest_arrival = self.dive.latest_arrival_event()
            if latest_arrival is None:
                return
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            if current_depth is None:
                return
            required_stop_time = profile.stops_fsw.get(current_depth)
            if required_stop_time is None:
                return
            stop_anchor = self._current_stop_timer_anchor(profile)
            if stop_anchor is None:
                return
            elapsed_seconds = (self._now() - stop_anchor).total_seconds()
            if elapsed_seconds > required_stop_time * 60:
                self.between_stops_delay_depth_fsw = current_depth
            return

        latest_leave = self.dive.latest_stop_departure_event()
        depth = self._parsed_depth()
        if (
            latest_leave is None
            or depth is None
        ):
            return
        if self.between_stops_delay_depth_fsw is not None:
            return

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        source_depth = self._stop_depth_for_number(stop_depths, latest_leave.stop_number)
        destination_depth = self._next_stop_depth(stop_depths, latest_leave.stop_number)
        if source_depth is None:
            return
        planned_seconds = math.ceil((max(source_depth - destination_depth, 0) / 30) * 60)
        elapsed_seconds = (self._now() - latest_leave.timestamp).total_seconds()
        if elapsed_seconds <= planned_seconds:
            return
        current_depth = self._estimated_current_depth(depth)
        if current_depth is not None:
            self.between_stops_delay_depth_fsw = current_depth

    def _between_stops_delay_evaluation(self, profile):
        if profile is None or profile.section == "no_decompression":
            return None
        if self.dive.first_stop_arrival_event() is None:
            return None

        latest_arrival = self.dive.latest_arrival_event()
        if latest_arrival is None:
            return None

        latest_departure = self.dive.latest_stop_departure_event()

        if self.dive._at_stop:
            stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
            current_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
            if current_depth is None:
                return None
            required_stop_time = profile.stops_fsw.get(current_depth)
            if required_stop_time is None:
                return None
            stop_anchor = self._current_stop_timer_anchor(profile)
            if stop_anchor is None:
                return None
            actual_elapsed_seconds = (self._now() - stop_anchor).total_seconds()
            return evaluate_between_stops_delay(
                max_depth_fsw=self._parsed_depth() or profile.input_depth_fsw,
                session=self.dive.session,
                planned_profile=profile,
                actual_elapsed_seconds=actual_elapsed_seconds,
                planned_elapsed_seconds=required_stop_time * 60,
                delay_depth_fsw=self.between_stops_delay_depth_fsw or current_depth,
                mode=self.decompression_mode,
            )

        if latest_arrival.stop_number <= 1 or latest_departure is None:
            return None

        stop_depths = sorted(profile.stops_fsw.keys(), reverse=True)
        source_depth = self._stop_depth_for_number(stop_depths, latest_departure.stop_number)
        destination_depth = self._stop_depth_for_number(stop_depths, latest_arrival.stop_number)
        if source_depth is None or destination_depth is None:
            return None
        planned_elapsed_seconds = math.ceil((max(source_depth - destination_depth, 0) / 30) * 60)
        actual_elapsed_seconds = (latest_arrival.timestamp - latest_departure.timestamp).total_seconds()
        return evaluate_between_stops_delay(
            max_depth_fsw=self._parsed_depth() or profile.input_depth_fsw,
            session=self.dive.session,
            planned_profile=profile,
            actual_elapsed_seconds=actual_elapsed_seconds,
            planned_elapsed_seconds=planned_elapsed_seconds,
            delay_depth_fsw=self.between_stops_delay_depth_fsw or destination_depth,
            mode=self.decompression_mode,
        )

    def _delay_status_text(self) -> str | None:
        profile = self._profile_after_first_stop_evaluation()
        between_stops = self._between_stops_delay_evaluation(profile)
        if between_stops is not None:
            if between_stops.delay_seconds <= 60:
                return "Delay: < 1 min"
            if between_stops.delay_depth_fsw > 50:
                return "Delay: > 1 min, > 50 fsw"
            return "Delay: > 1 min, < 50 fsw"
        evaluation = self._first_stop_arrival_evaluation()
        if evaluation is None or evaluation.delay_seconds is None:
            return None
        if evaluation.delay_seconds <= 60:
            return "Delay: < 1 min"
        if self.delay_to_first_stop_depth_fsw is not None and self.delay_to_first_stop_depth_fsw > 50:
            return "Delay: > 1 min, > 50 fsw"
        return "Delay: > 1 min, < 50 fsw"


def main() -> None:
    root = tk.Tk()
    app = DiveStopwatchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
