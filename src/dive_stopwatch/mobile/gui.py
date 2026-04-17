from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft

from ..minimal import Engine, Intent
from ..minimal.engine import DivePhase


class MobileDiveStopwatchApp:
    O2_COLOR = ft.Colors.GREEN_700
    AIR_BREAK_COLOR = ft.Colors.RED_700
    MODE_AIR_O2_ACCENT = "#2DE3A0"
    MODE_AIR_O2_GLOW = "#11392B"
    DEFAULT_TEXT_COLOR = ft.Colors.WHITE
    MUTED_TEXT_COLOR = "#9CA8B4"
    APP_BACKGROUND = "#05080C"
    APPBAR_BACKGROUND = "#0A0E13"
    EMPHASIZED_CARD = "#0D1217"
    CONTROL_CARD = "#111820"
    CARD_BORDER = "#2B353F"
    CARD_BORDER_SOFT = "#1B232B"
    LOG_SURFACE = "#080C10"
    LOG_INSET = "#0D1319"
    PRIMARY_BUTTON_BG = "#323E4A"
    PRIMARY_BUTTON_TEXT = ft.Colors.WHITE
    OUTLINE_ACCENT = "#54616E"
    BUTTON_SURFACE = "#0D1217"
    BUTTON_SHADOW = "#040608"
    METAL_HIGHLIGHT = "#D8E0E8"
    INSTRUMENT_FONT = "InstrumentMono"

    def __init__(self, page: ft.Page, engine: Engine | None = None) -> None:
        self.page = page
        self.engine = engine or Engine()
        self.recall_active = False
        self.depth_input = ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER,
            width=64,
            dense=True,
            value=self.engine.state.dive.depth_input_text,
            hint_text="__",
            text_align=ft.TextAlign.CENTER,
            bgcolor="#101820",
            color=self.DEFAULT_TEXT_COLOR,
            border=ft.InputBorder.OUTLINE,
            border_color=self.CARD_BORDER,
            focused_border_color=self.OUTLINE_ACCENT,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
            text_size=18,
            text_style=ft.TextStyle(font_family=self.INSTRUMENT_FONT, size=18, weight=ft.FontWeight.W_700),
            cursor_color=self.DEFAULT_TEXT_COLOR,
            on_change=lambda _: self._sync_depth_input(),
        )
        self.mode_label_text = ft.Text("Mode", size=14, weight=ft.FontWeight.W_800, color=self.METAL_HIGHLIGHT, font_family=self.INSTRUMENT_FONT)
        self.mode_label_chip = ft.Container(
            width=132,
            alignment=ft.alignment.center,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            border_radius=12,
            border=ft.border.all(1, self.CARD_BORDER),
            bgcolor="#0A0F14",
            ink=True,
            on_click=lambda _: self._dispatch(Intent.MODE),
            content=self.mode_label_text,
        )
        self.recall_button = ft.OutlinedButton(
            "Recall",
            on_click=lambda _: self._toggle_recall(),
            expand=True,
            height=48,
            style=self._utility_button_style(),
        )
        self.recall_timer_text = ft.Text(size=20, weight=ft.FontWeight.W_700, visible=False, font_family=self.INSTRUMENT_FONT)
        self.status_label_text = ft.Text("Status:", size=18, weight=ft.FontWeight.W_600, font_family=self.INSTRUMENT_FONT)
        self.status_value_text = ft.Text(size=24, weight=ft.FontWeight.BOLD, font_family=self.INSTRUMENT_FONT)
        self.primary_text = ft.Text(size=54, weight=ft.FontWeight.BOLD, font_family=self.INSTRUMENT_FONT)
        self.depth_text = ft.Text(size=22, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT)
        self.depth_unit_text = ft.Text("fsw", size=22, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.depth_input_row = ft.Row(
            spacing=8,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.depth_input,
                self.depth_unit_text,
            ],
        )
        self.depth_separator_text = ft.Text("|", size=18, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR, visible=False, font_family=self.INSTRUMENT_FONT)
        self.depth_timer_text = ft.Text(size=20, weight=ft.FontWeight.W_600, visible=False, font_family=self.INSTRUMENT_FONT)
        self.depth_row = ft.Row(
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.depth_text,
                self.depth_input_row,
                self.depth_separator_text,
                self.depth_timer_text,
            ],
        )
        self.remaining_text = ft.Text(size=16, weight=ft.FontWeight.W_500, font_family=self.INSTRUMENT_FONT)
        self.summary_prefix_text = ft.Text(size=17, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.summary_value_text = ft.Text(size=17, weight=ft.FontWeight.W_700, color=self.MUTED_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.summary_row = ft.Row(spacing=0, wrap=True, controls=[self.summary_prefix_text, self.summary_value_text])
        self.detail_text = ft.Text(size=14, italic=True, font_family=self.INSTRUMENT_FONT)
        self.test_time_text = ft.Text(size=14, weight=ft.FontWeight.W_500, font_family=self.INSTRUMENT_FONT)
        self.test_time_label = ft.Text("Test Time", size=13, weight=ft.FontWeight.W_700, color=self.MUTED_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.log_text = ft.TextField(
            value="",
            read_only=True,
            multiline=True,
            min_lines=16,
            max_lines=16,
            expand=True,
            border=ft.InputBorder.NONE,
            content_padding=ft.padding.all(0),
            text_size=13,
            color=self.DEFAULT_TEXT_COLOR,
            bgcolor=ft.Colors.TRANSPARENT,
            cursor_color=self.DEFAULT_TEXT_COLOR,
            text_style=ft.TextStyle(font_family="monospace", height=1.25),
        )
        self.primary_button = ft.FilledButton(
            text="Primary",
            on_click=lambda _: self._dispatch(Intent.PRIMARY),
            expand=True,
            height=58,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=14),
                bgcolor=self.PRIMARY_BUTTON_BG,
                color=self.PRIMARY_BUTTON_TEXT,
                padding=ft.padding.symmetric(vertical=14, horizontal=16),
                shadow_color=self.BUTTON_SHADOW,
                elevation=8,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
            ),
        )
        self.secondary_button = ft.OutlinedButton(
            text="-",
            on_click=lambda _: self._dispatch(Intent.SECONDARY),
            expand=True,
            height=58,
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, self.OUTLINE_ACCENT),
                shape=ft.RoundedRectangleBorder(radius=14),
                color=self.DEFAULT_TEXT_COLOR,
                bgcolor=self.BUTTON_SURFACE,
                padding=ft.padding.symmetric(vertical=14, horizontal=16),
                shadow_color=self.BUTTON_SHADOW,
                elevation=4,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
            ),
        )
        self._last_log_rendered: tuple[str, ...] = ()
        self.primary_header = ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            controls=[
                self.mode_label_chip,
                self.recall_timer_text,
            ],
        )
        self.primary_live_body = ft.Column(
            spacing=14,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        self.status_label_text,
                        self.status_value_text,
                    ],
                ),
                self.primary_text,
                self.depth_row,
                self.remaining_text,
                self.summary_row,
                self.detail_text,
            ],
        )
        self.primary_recall_body = ft.Column(
            expand=True,
            spacing=12,
            controls=[
                ft.Text("Event Log", size=16, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR),
                ft.Container(
                    expand=True,
                    border=ft.border.all(1, self.CARD_BORDER),
                    border_radius=12,
                    padding=12,
                    bgcolor=self.LOG_INSET,
                    content=self.log_text,
                ),
            ],
        )
        self.primary_body_switcher = ft.Container(content=self.primary_live_body, expand=True)
        self.primary_card_body = ft.Column(
            spacing=14,
            controls=[
                self.primary_header,
                self.primary_body_switcher,
            ],
        )

    def mount(self) -> None:
        self.page.title = "CAISSON Instruments Mobile"
        self.page.padding = 14
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.fonts = {
            self.INSTRUMENT_FONT: str(Path(__file__).resolve().parents[3] / "assets" / "fonts" / "CaissonCockpit.ttf"),
        }
        self.page.window_min_width = 360
        self.page.window_min_height = 720
        self.page.window_width = 430
        self.page.bgcolor = self.APP_BACKGROUND
        self.page.appbar = ft.AppBar(
            title=ft.Text(
                "Caisson Instruments",
                size=24,
                weight=ft.FontWeight.W_700,
                italic=True,
                font_family="Helvetica Neue",
                color=self.DEFAULT_TEXT_COLOR,
            ),
            center_title=False,
            bgcolor=self.APPBAR_BACKGROUND,
            color=self.DEFAULT_TEXT_COLOR,
            elevation=2,
        )
        self.page.add(
            ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    self._card(
                        self.primary_card_body,
                        emphasized=True,
                    ),
                    self._card(
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Controls", size=15, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT),
                                ft.Row(
                                    controls=[
                                        self.primary_button,
                                        self.secondary_button,
                                    ],
                                ),
                                ft.Row(
                                    controls=[
                                        self.recall_button,
                                        ft.OutlinedButton("Reset", on_click=lambda _: self._dispatch(Intent.RESET), expand=True, height=48, style=self._utility_button_style()),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    self._card(
                        ft.Column(
                            spacing=8,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        self.test_time_label,
                                        self.test_time_text,
                                    ],
                                ),
                                ft.Row(
                                    spacing=8,
                                    controls=[
                                        ft.OutlinedButton("-1m", on_click=lambda _: self._advance_test_time(-60), expand=True, height=42, style=self._test_time_button_style()),
                                        ft.OutlinedButton("+1m", on_click=lambda _: self._advance_test_time(60), expand=True, height=42, style=self._test_time_button_style()),
                                        ft.OutlinedButton("+5m", on_click=lambda _: self._advance_test_time(300), expand=True, height=42, style=self._test_time_button_style()),
                                        ft.OutlinedButton("+30m", on_click=lambda _: self._advance_test_time(1800), expand=True, height=42, style=self._test_time_button_style()),
                                    ],
                                    wrap=False,
                                ),
                            ],
                        ),
                        compact=True,
                    ),
                ],
            )
        )
        self.page.run_task(self._refresh_loop)
        self._render()

    def _sync_depth_input(self) -> None:
        self.engine.set_depth_text(self.depth_input.value or "")

    def _dispatch(self, intent: Intent) -> None:
        self._run_and_render(self._sync_depth_input, lambda: self.engine.dispatch(intent))

    def _advance_test_time(self, delta_seconds: float) -> None:
        self._run_and_render(lambda: self.engine.advance_test_time(delta_seconds))

    def _toggle_recall(self) -> None:
        self.recall_active = not self.recall_active
        self._render()

    def _run_and_render(self, *actions) -> None:
        for action in actions:
            action()
        self._render()

    async def _refresh_loop(self) -> None:
        while self.page.session is not None:
            self._render()
            await asyncio.sleep(0.1)

    def _render(self) -> None:
        snap = self.engine.snapshot()
        phase = self.engine.state.dive.phase
        editable_depth = phase in {DivePhase.READY, DivePhase.BOTTOM}
        self._render_mode_tile(snap.mode_text)
        self.status_value_text.value = snap.status_value_text
        self.primary_text.value = snap.primary_value_text
        if self.depth_input.value != self.engine.state.dive.depth_input_text:
            self.depth_input.value = self.engine.state.dive.depth_input_text
        self.depth_input_row.visible = editable_depth
        self.depth_text.visible = not editable_depth
        self.depth_text.value = snap.depth_text
        self.depth_separator_text.visible = bool(snap.depth_timer_text)
        self.depth_timer_text.visible = bool(snap.depth_timer_text)
        self.depth_timer_text.value = snap.depth_timer_text
        self.remaining_text.value = snap.remaining_display_text
        self.detail_text.value = snap.detail_text
        self.test_time_text.value = self.engine.test_time_label()
        self.primary_button.text = snap.primary_button_label or "-"
        self.primary_button.disabled = not snap.primary_button_enabled
        self.secondary_button.text = snap.secondary_button_label or "-"
        self.secondary_button.disabled = not snap.secondary_button_enabled
        self.summary_prefix_text.value = snap.summary_prefix_text
        self.summary_value_text.value = snap.summary_value_text
        self.summary_row.visible = bool(snap.summary_prefix_text or snap.summary_value_text)
        self._apply_phase_colors(snap)
        self.primary_body_switcher.content = self.primary_recall_body if self.recall_active else self.primary_live_body
        self.recall_button.text = "Live" if self.recall_active else "Recall"
        self.recall_timer_text.visible = self.recall_active
        self.recall_timer_text.value = snap.primary_value_text if self.recall_active else ""
        self.recall_button.style = ft.ButtonStyle(
            side=ft.BorderSide(1, self.OUTLINE_ACCENT if self.recall_active else self.CARD_BORDER),
            shape=ft.RoundedRectangleBorder(radius=12),
            color=self.PRIMARY_BUTTON_TEXT if self.recall_active else self.DEFAULT_TEXT_COLOR,
            bgcolor=self.PRIMARY_BUTTON_BG if self.recall_active else self.BUTTON_SURFACE,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            shadow_color=self.BUTTON_SHADOW,
            elevation=4 if self.recall_active else 2,
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_700),
        )

        log_lines = self.engine.state.ui_log[-30:]
        if log_lines != self._last_log_rendered:
            self.log_text.value = "\n".join(log_lines)
            self._last_log_rendered = log_lines

        self.page.update()

    def _apply_phase_colors(self, snap) -> None:
        self.status_label_text.color = self.DEFAULT_TEXT_COLOR
        self.status_value_text.color = self._kind_color(snap.status_value_kind)
        self.primary_text.color = self._kind_color(snap.primary_value_kind)
        self.remaining_text.color = self.DEFAULT_TEXT_COLOR
        self.detail_text.color = self.MUTED_TEXT_COLOR
        self.depth_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_input.color = self.DEFAULT_TEXT_COLOR
        self.depth_unit_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_timer_text.color = self._kind_color(snap.depth_timer_kind)
        self.test_time_text.color = self.MUTED_TEXT_COLOR
        self.recall_timer_text.color = self._kind_color(snap.primary_value_kind)

        self.summary_prefix_text.color = self.DEFAULT_TEXT_COLOR
        self.summary_value_text.color = self._kind_color(snap.summary_value_kind)

    def _render_mode_tile(self, mode_text: str) -> None:
        is_air_o2 = mode_text == "AIR/O2"
        is_stopwatch = mode_text == "STOPWATCH"
        self.mode_label_text.value = mode_text
        self.mode_label_text.color = self.PRIMARY_BUTTON_TEXT
        self.mode_label_chip.bgcolor = self.PRIMARY_BUTTON_BG if not is_stopwatch else "#252E37"
        self.mode_label_chip.border = ft.border.all(
            1,
            self.MODE_AIR_O2_ACCENT if is_air_o2 else self.OUTLINE_ACCENT if not is_stopwatch else self.CARD_BORDER,
        )
        self.mode_label_chip.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=14 if is_air_o2 else 10,
            color=self.MODE_AIR_O2_GLOW if is_air_o2 else self.BUTTON_SHADOW,
            offset=ft.Offset(0, 4),
        )

    def _kind_color(self, kind: str) -> str:
        if kind == "o2":
            return self.O2_COLOR
        if kind == "air_break":
            return self.AIR_BREAK_COLOR
        return self.DEFAULT_TEXT_COLOR

    def _card(self, content: ft.Control, *, emphasized: bool = False, expand: bool = False, compact: bool = False) -> ft.Container:
        return ft.Container(
            expand=expand,
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=18, vertical=12 if compact else 18),
            bgcolor=self.EMPHASIZED_CARD if emphasized else self.CONTROL_CARD,
            border=ft.border.all(1, self.CARD_BORDER if emphasized else self.CARD_BORDER_SOFT),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=18 if compact else 22,
                color="#05080B",
                offset=ft.Offset(0, 10),
            ),
            content=content,
        )

    def _test_time_button_style(self) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            side=ft.BorderSide(1, self.CARD_BORDER),
            shape=ft.RoundedRectangleBorder(radius=12),
            color=self.DEFAULT_TEXT_COLOR,
            bgcolor=self.BUTTON_SURFACE,
            shadow_color=self.BUTTON_SHADOW,
            elevation=3,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
        )

    def _utility_button_style(self) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            side=ft.BorderSide(1, self.CARD_BORDER),
            shape=ft.RoundedRectangleBorder(radius=14),
            color=self.MUTED_TEXT_COLOR,
            bgcolor=self.BUTTON_SURFACE,
            shadow_color=self.BUTTON_SHADOW,
            elevation=3,
            text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600, font_family=self.INSTRUMENT_FONT),
        )


def main(page: ft.Page) -> None:
    MobileDiveStopwatchApp(page).mount()
