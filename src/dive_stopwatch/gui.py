"""Tkinter GUI for stopwatch and dive workflows."""

from __future__ import annotations

from datetime import datetime
import math
import tkinter as tk
from tkinter import ttk

from dive_stopwatch.dive_mode import DiveController, DivePhase
from dive_stopwatch.stopwatch import DeviceMode, Stopwatch, format_hhmmss


def format_tenths(seconds: float) -> str:
    """Format elapsed seconds as MM:SS.t."""

    clamped = max(seconds, 0.0)
    total_tenths = math.floor((clamped * 10) + 1e-9)
    whole_seconds, tenths = divmod(total_tenths, 10)
    minutes, secs = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{secs:02d}.{tenths}"


class DiveStopwatchApp:
    """Small operator-focused GUI for stopwatch and dive mode."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Dive Stopwatch")
        self.root.geometry("860x640")
        self.root.minsize(760, 560)

        self.mode = DeviceMode.STOPWATCH
        self.stopwatch = Stopwatch()
        self.dive = DiveController()

        self.mode_text = tk.StringVar(value="STOPWATCH MODE")
        self.phase_text = tk.StringVar(value="READY")
        self.primary_display = tk.StringVar(value="00:00:00.000")
        self.secondary_display = tk.StringVar(value="live=00:00:00.000")
        self.ct_text = tk.StringVar(value="CT 10:00")
        self.status_text = tk.StringVar(value="Ready.")
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
        style.configure("Header.TLabel", background="#f3efe5", foreground="#183153", font=("Avenir Next", 24, "bold"))
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

        ttk.Label(header, text="Dive Stopwatch", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.mode_text, style="Subheader.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

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
        toggle_button.grid(row=0, column=1, rowspan=2, sticky="e")

        main_panel = ttk.Frame(container, style="Card.TFrame", padding=18)
        main_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        main_panel.columnconfigure(0, weight=1)

        ttk.Label(main_panel, text="Primary Display", style="CardLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main_panel, textvariable=self.primary_display, style="Value.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(main_panel, textvariable=self.secondary_display, style="SmallValue.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 14))
        ttk.Label(main_panel, textvariable=self.phase_text, style="Subheader.TLabel").grid(row=3, column=0, sticky="w")
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

        ttk.Label(side_panel, text="Dive Call And Response", style="CardLabel.TLabel").grid(
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

        for key in ("R", "L"):
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
                if result["event"] == "RB":
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
            self.phase_text.set(f"Phase: {self.dive.phase.name}")
            self._update_dive_summary()
            self.primary_display.set(self._primary_dive_display())
            self.secondary_display.set(self._secondary_dive_display())
            self.ct_text.set(self._clean_time_text())
            self.lap_button.configure(text="Lap")
            self.start_button.configure(text="Start")
            self.stop_button.configure(text="Stop")
        else:
            self.phase_text.set(f"Phase: {'RUNNING' if self.stopwatch.running else 'READY'}")
            display = self.stopwatch.display_time()
            live = self.stopwatch.total_elapsed()
            self.primary_display.set(format_tenths(display))
            self.secondary_display.set(f"live={format_tenths(live)} running={self.stopwatch.running}")
            self.ct_text.set("CT --:--")
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
            self.event_values[key].set(str(summary.get(key, "--")))

        latest_r = next((event for event in reversed(self.dive.stop_events) if event.code == "R"), None)
        latest_l = next((event for event in reversed(self.dive.stop_events) if event.code == "L"), None)
        if latest_r is not None:
            self.event_values["R"].set(f"R{latest_r.stop_number} {latest_r.timestamp.strftime('%H:%M:%S')}")
        if latest_l is not None:
            self.event_values["L"].set(f"L{latest_l.stop_number} {latest_l.timestamp.strftime('%H:%M:%S')}")

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
            return f"AT {summary.get('AT', '--')}"
        return "--"

    def _secondary_dive_display(self) -> str:
        summary = self.dive.session.summary()
        if self.dive.phase in {DivePhase.DESCENT, DivePhase.BOTTOM} and "LS" in summary:
            return f"Running from LS   LS {summary['LS']}"
        if self.dive.phase is DivePhase.ASCENT and "LB" in summary:
            latest_stop = self.dive.latest_stop_event()
            if latest_stop is None:
                return f"Lap from LB   LB {summary['LB']}"
            return f"{latest_stop.code}{latest_stop.stop_number}   {latest_stop.timestamp.strftime('%H:%M:%S')}"
        if self.dive.phase is DivePhase.CLEAN_TIME:
            return (
                f"RS {summary.get('RS', '--')}   "
                f"AT {summary.get('AT', '--')}   "
                f"TDT {summary.get('TDT', '--')}   "
                f"TTD {summary.get('TTD', '--')}"
            )
        parts = []
        for key in ("LS", "RB", "LB", "RS"):
            if key in summary:
                parts.append(f"{key} {summary[key]}")
        return "   ".join(parts) if parts else "Use Start to begin the dive."

    def _clean_time_text(self) -> str:
        if self.dive.clean_time is None:
            return "CT 10:00"

        status = self.dive.clean_time_status()
        suffix = " COMPLETE" if status["complete"] else ""
        return f"CT {status['CT']}{suffix}"

    def _refresh_loop(self) -> None:
        self._update_ui()
        self.root.after(100, self._refresh_loop)

    def _live_total_display(self) -> str:
        ls_event = self.dive.session.events.get("LS")
        if ls_event is None:
            return "Awaiting LS"
        elapsed = (datetime.now() - ls_event.timestamp).total_seconds()
        return format_tenths(elapsed)

    def _live_ascent_display(self) -> str:
        anchor = self.dive.session.events.get("LB")
        latest_stop = self.dive.latest_stop_event()
        if latest_stop is not None and latest_stop.code == "R":
            anchor_time = latest_stop.timestamp
        elif anchor is not None:
            anchor_time = anchor.timestamp
        else:
            return "--:--.-"
        elapsed = (datetime.now() - anchor_time).total_seconds()
        return format_tenths(elapsed)


def main() -> None:
    root = tk.Tk()
    app = DiveStopwatchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
