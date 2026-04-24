from __future__ import annotations

import tkinter as tk

from .air_o2_engine import Intent
from .runtime import Engine


class DiveStopwatchApp:
    REFRESH_MS = 100

    def __init__(self, root: tk.Tk, engine: Engine | None = None) -> None:
        self.root = root
        self.engine = engine or Engine()
        self._refresh_job: str | None = None
        self._last_log_rendered: tuple[str, ...] = ()

        self.root.title("CAISSON Active")
        self.root.geometry("500x420")
        self.root.minsize(460, 380)

        self.mode_text = tk.StringVar()
        self.status_text = tk.StringVar()
        self.primary_text = tk.StringVar()
        self.depth_text = tk.StringVar()
        self.remaining_text = tk.StringVar()
        self.summary_text = tk.StringVar()
        self.detail_text = tk.StringVar()
        self.test_time_text = tk.StringVar()
        self.depth_input = tk.StringVar()

        self._build_ui()
        self._render()
        self._start_refresh_loop()
        self.root.bind("<Destroy>", self._on_destroy, add="+")

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="CAISSON Active", font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.mode_text, font=("Helvetica", 11)).pack(anchor="w")
        self.test_time_label = tk.Label(frame, textvariable=self.test_time_text, font=("Helvetica", 11))
        self.test_time_label.pack(anchor="w")
        tk.Label(frame, textvariable=self.status_text, font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(8, 0))
        tk.Label(frame, textvariable=self.primary_text, font=("Courier", 24, "bold")).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.depth_text, font=("Helvetica", 14)).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.remaining_text, font=("Helvetica", 12)).pack(anchor="w")
        tk.Label(frame, textvariable=self.summary_text, font=("Helvetica", 12)).pack(anchor="w", pady=(8, 0))
        tk.Label(frame, textvariable=self.detail_text, font=("Helvetica", 11)).pack(anchor="w")

        self.input_row = tk.Frame(frame)
        self.input_row.pack(fill="x", pady=(12, 0))
        tk.Label(self.input_row, text="Max Depth (fsw):").pack(side="left")
        depth_entry = tk.Entry(self.input_row, textvariable=self.depth_input, width=8)
        depth_entry.pack(side="left", padx=(6, 8))
        depth_entry.bind("<Return>", self._set_depth, add="+")
        tk.Button(self.input_row, text="Set", command=self._set_depth).pack(side="left")

        self.test_time_row = tk.Frame(frame)
        self.test_time_row.pack(fill="x", pady=(10, 0))
        tk.Button(self.test_time_row, text="-1m", command=lambda: self._advance_test_time(-60)).pack(side="left", padx=(0, 6))
        tk.Button(self.test_time_row, text="+1m", command=lambda: self._advance_test_time(60)).pack(side="left", padx=(0, 6))
        tk.Button(self.test_time_row, text="+5m", command=lambda: self._advance_test_time(300)).pack(side="left", padx=(0, 6))
        tk.Button(self.test_time_row, text="+30m", command=lambda: self._advance_test_time(1800)).pack(side="left", padx=(0, 6))
        tk.Button(self.test_time_row, text="Live", command=self._reset_test_time).pack(side="left")

        button_row = tk.Frame(frame)
        button_row.pack(fill="x", pady=(12, 0))
        self.primary_button = tk.Button(button_row, command=lambda: self._dispatch(Intent.PRIMARY))
        self.primary_button.pack(side="left", padx=(0, 8))
        self.secondary_button = tk.Button(button_row, command=lambda: self._dispatch(Intent.SECONDARY))
        self.secondary_button.pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Mode", command=lambda: self._dispatch(Intent.MODE)).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Reset", command=lambda: self._dispatch(Intent.RESET)).pack(side="left")

        self.log_label = tk.Label(frame, text="Event Log", font=("Helvetica", 11, "bold"))
        self.log_label.pack(anchor="w", pady=(12, 0))
        self.log_box = tk.Text(frame, height=10, width=60, state="disabled")
        self.log_box.pack(fill="both", expand=True)

    def _sync_depth_input(self) -> None:
        self.engine.set_depth_text(self.depth_input.get())

    def _set_depth(self, _event=None) -> None:
        self._run_and_render(self._sync_depth_input)

    def _dispatch(self, intent: Intent) -> None:
        self._run_and_render(self._sync_depth_input, lambda: self.engine.dispatch(intent))

    def _advance_test_time(self, delta_seconds: float) -> None:
        self._run_and_render(lambda: self.engine.advance_test_time(delta_seconds))

    def _reset_test_time(self) -> None:
        self._run_and_render(self.engine.reset_test_time)

    def _run_and_render(self, *actions) -> None:
        for action in actions:
            action()
        self._render()

    def _start_refresh_loop(self) -> None:
        if self._refresh_job is None: self._schedule_next_refresh()

    def _schedule_next_refresh(self) -> None:
        if not self.root.winfo_exists():
            self._refresh_job = None
            return
        self._refresh_job = self.root.after(self.REFRESH_MS, self._refresh_tick)

    def _refresh_tick(self) -> None:
        self._refresh_job = None
        if not self.root.winfo_exists():
            return
        self._render()
        self._schedule_next_refresh()

    def _on_destroy(self, _event) -> None:
        if self._refresh_job is None:
            return
        try:
            self.root.after_cancel(self._refresh_job)
        except tk.TclError:
            pass
        self._refresh_job = None

    def _render(self) -> None:
        snap = self.engine.snapshot()
        is_stopwatch = snap.mode_text == "STOPWATCH"
        self.mode_text.set(f"Mode: {snap.mode_text}")
        self.test_time_text.set(self.engine.test_time_label())
        if is_stopwatch:
            if self.test_time_label.winfo_manager():
                self.test_time_label.pack_forget()
            if self.input_row.winfo_manager():
                self.input_row.pack_forget()
            if self.test_time_row.winfo_manager():
                self.test_time_row.pack_forget()
        else:
            if not self.test_time_label.winfo_manager():
                self.test_time_label.pack(anchor="w")
            if not self.input_row.winfo_manager():
                self.input_row.pack(fill="x", pady=(12, 0))
            if not self.test_time_row.winfo_manager():
                self.test_time_row.pack(fill="x", pady=(10, 0))
        self.status_text.set(f"Status: {snap.status_text}")
        self.primary_text.set(snap.primary_text)
        self.depth_text.set(snap.depth_text)
        self.remaining_text.set(snap.remaining_text)
        self.summary_text.set(snap.summary_text)
        self.detail_text.set(snap.detail_text)
        self.primary_button.config(text=snap.primary_button_label, state="normal" if snap.primary_button_enabled else "disabled")
        self.secondary_button.config(text=snap.secondary_button_label, state="normal" if snap.secondary_button_enabled else "disabled")
        self.log_label.config(text="Recall" if snap.mode_text == "STOPWATCH" else "Event Log")

        log_lines = self.engine.recall_lines()
        if log_lines != self._last_log_rendered:
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            for line in log_lines:
                self.log_box.insert("end", f"{line}\n")
            self.log_box.config(state="disabled")
            self._last_log_rendered = log_lines


def main() -> None:
    root = tk.Tk()
    DiveStopwatchApp(root)
    root.mainloop()
