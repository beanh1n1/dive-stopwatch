from __future__ import annotations

import tkinter as tk

from .core import EngineV2
from .models import IntentV2


class V2ShellApp:
    REFRESH_MS = 100

    def __init__(self, root: tk.Tk, engine: EngineV2 | None = None) -> None:
        self.root = root
        self.engine = engine or EngineV2()
        self._refresh_job: str | None = None

        self.root.title("The CAISSON v2")
        self.root.geometry("500x420")
        self.root.minsize(460, 380)

        self.mode_text = tk.StringVar()
        self.deco_text = tk.StringVar()
        self.test_time_text = tk.StringVar()
        self.status_text = tk.StringVar()
        self.primary_text = tk.StringVar()
        self.depth_text = tk.StringVar()
        self.remaining_text = tk.StringVar()
        self.summary_text = tk.StringVar()
        self.detail_text = tk.StringVar()
        self.depth_input = tk.StringVar()

        self._build_ui()
        self._render()
        self._start_refresh_loop()
        self.root.bind("<Destroy>", self._on_destroy, add="+")

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="CAISSON v2", font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.mode_text, font=("Helvetica", 11)).pack(anchor="w")
        tk.Label(frame, textvariable=self.deco_text, font=("Helvetica", 11)).pack(anchor="w")
        tk.Label(frame, textvariable=self.test_time_text, font=("Helvetica", 11)).pack(anchor="w")
        tk.Label(frame, textvariable=self.status_text, font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(8, 0))
        tk.Label(frame, textvariable=self.primary_text, font=("Courier", 24, "bold")).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.depth_text, font=("Helvetica", 14)).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.remaining_text, font=("Helvetica", 12)).pack(anchor="w")
        tk.Label(frame, textvariable=self.summary_text, font=("Helvetica", 12)).pack(anchor="w", pady=(8, 0))
        tk.Label(frame, textvariable=self.detail_text, font=("Helvetica", 11)).pack(anchor="w")

        input_row = tk.Frame(frame)
        input_row.pack(fill="x", pady=(12, 0))
        tk.Label(input_row, text="Max Depth (fsw):").pack(side="left")
        tk.Entry(input_row, textvariable=self.depth_input, width=8).pack(side="left", padx=(6, 8))
        tk.Button(input_row, text="Set", command=self._set_depth).pack(side="left")

        test_time_row = tk.Frame(frame)
        test_time_row.pack(fill="x", pady=(10, 0))
        tk.Button(test_time_row, text="-1m", command=lambda: self._advance_test_time(-60)).pack(side="left", padx=(0, 6))
        tk.Button(test_time_row, text="+1m", command=lambda: self._advance_test_time(60)).pack(side="left", padx=(0, 6))
        tk.Button(test_time_row, text="+5m", command=lambda: self._advance_test_time(300)).pack(side="left", padx=(0, 6))
        tk.Button(test_time_row, text="+30m", command=lambda: self._advance_test_time(1800)).pack(side="left", padx=(0, 6))
        tk.Button(test_time_row, text="Live", command=self._reset_test_time).pack(side="left")

        button_row = tk.Frame(frame)
        button_row.pack(fill="x", pady=(12, 0))
        self.primary_button = tk.Button(button_row, command=lambda: self._dispatch(IntentV2.PRIMARY))
        self.primary_button.pack(side="left", padx=(0, 8))
        self.secondary_button = tk.Button(button_row, command=lambda: self._dispatch(IntentV2.SECONDARY))
        self.secondary_button.pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Mode", command=lambda: self._dispatch(IntentV2.MODE)).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Reset", command=lambda: self._dispatch(IntentV2.RESET)).pack(side="left")

        tk.Label(frame, text="Event Log", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(12, 0))
        self.log_box = tk.Text(frame, height=10, width=60, state="disabled")
        self.log_box.pack(fill="both", expand=True)

    def _set_depth(self) -> None:
        self.engine.set_depth_text(self.depth_input.get())
        self._render()

    def _dispatch(self, intent: IntentV2) -> None:
        self.engine.dispatch(intent)
        self._render()

    def _advance_test_time(self, delta_seconds: float) -> None:
        self.engine.advance_test_time(delta_seconds)
        self._render()

    def _reset_test_time(self) -> None:
        self.engine.reset_test_time()
        self._render()

    def _start_refresh_loop(self) -> None:
        if self._refresh_job is not None:
            return
        self._schedule_next_refresh()

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
        self.mode_text.set(f"Mode: {snap.mode_text}")
        self.deco_text.set(f"Deco: {snap.deco_mode_text}")
        self.test_time_text.set(self.engine.test_time_label())
        self.status_text.set(f"Status: {snap.status.value}")
        self.primary_text.set(snap.primary)
        self.depth_text.set(snap.depth)
        self.remaining_text.set(snap.remaining)
        self.summary_text.set(snap.summary)
        self.detail_text.set(snap.detail)
        self.primary_button.config(text=snap.start_label, state="normal" if snap.start_enabled else "disabled")
        self.secondary_button.config(text=snap.secondary_label, state="normal" if snap.secondary_enabled else "disabled")

        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        for line in self.engine.state.log_lines[-30:]:
            self.log_box.insert("end", f"{line}\n")
        self.log_box.config(state="disabled")
