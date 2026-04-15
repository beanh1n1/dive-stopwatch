from __future__ import annotations

import asyncio

import flet as ft

from ..minimal import Engine, Intent


class MobileDiveStopwatchApp:
    O2_COLOR = ft.Colors.GREEN_700
    AIR_BREAK_COLOR = ft.Colors.RED_700
    DEFAULT_TEXT_COLOR = ft.Colors.BLACK
    MUTED_TEXT_COLOR = ft.Colors.BLUE_GREY_700
    SURFACE_CARD = ft.Colors.BLUE_GREY_50
    CONTROL_CARD = ft.Colors.WHITE
    CARD_BORDER = ft.Colors.BLUE_GREY_100
    DELAY_BANNER_COLOR = ft.Colors.BLUE_800

    def __init__(self, page: ft.Page, engine: Engine | None = None) -> None:
        self.page = page
        self.engine = engine or Engine()
        self.depth_input = ft.TextField(label="Max Depth (fsw)", keyboard_type=ft.KeyboardType.NUMBER, expand=True, dense=True)
        self.mode_text = ft.Text(size=15, weight=ft.FontWeight.W_600)
        self.status_label_text = ft.Text("Status:", size=22, weight=ft.FontWeight.BOLD)
        self.status_value_text = ft.Text(size=22, weight=ft.FontWeight.BOLD)
        self.primary_text = ft.Text(size=48, weight=ft.FontWeight.BOLD)
        self.depth_text = ft.Text(size=20, weight=ft.FontWeight.W_600)
        self.depth_separator_text = ft.Text("|", size=18, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR, visible=False)
        self.depth_timer_text = ft.Text(size=18, weight=ft.FontWeight.W_500, visible=False)
        self.depth_row = ft.Row(
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.depth_text,
                self.depth_separator_text,
                self.depth_timer_text,
            ],
        )
        self.remaining_text = ft.Text(size=16, weight=ft.FontWeight.W_500)
        self.summary_prefix_text = ft.Text(size=16, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR)
        self.summary_value_text = ft.Text(size=16, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR)
        self.summary_row = ft.Row(spacing=0, wrap=True, controls=[self.summary_prefix_text, self.summary_value_text])
        self.detail_text = ft.Text(size=14, italic=True)
        self.test_time_text = ft.Text(size=14)
        self.log_view = ft.ListView(expand=True, spacing=6, auto_scroll=False)
        self.primary_button = ft.FilledButton(text="Primary", on_click=lambda _: self._dispatch(Intent.PRIMARY), expand=True, height=54)
        self.secondary_button = ft.OutlinedButton(text="-", on_click=lambda _: self._dispatch(Intent.SECONDARY), expand=True, height=54)
        self._last_log_rendered: tuple[str, ...] = ()

    def mount(self) -> None:
        self.page.title = "CAISSON Instruments Mobile"
        self.page.padding = 16
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_min_width = 360
        self.page.window_min_height = 640
        self.page.bgcolor = ft.Colors.BLUE_GREY_50
        self.page.appbar = ft.AppBar(title=ft.Text("CAISSON Instruments"), center_title=False)
        self.page.add(
            ft.Column(
                expand=True,
                spacing=14,
                controls=[
                    self._card(
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        self.mode_text,
                                        self.test_time_text,
                                    ],
                                ),
                                ft.Row(
                                    spacing=8,
                                    controls=[
                                        self.status_label_text,
                                        self.status_value_text,
                                    ],
                                ),
                                self.primary_text,
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        self.depth_row,
                                        self.remaining_text,
                                    ],
                                ),
                                self.summary_row,
                                self.detail_text,
                            ],
                        ),
                        emphasized=True,
                    ),
                    self._card(
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Dive Setup", size=15, weight=ft.FontWeight.W_600),
                                ft.Row(
                                    controls=[
                                        self.depth_input,
                                        ft.FilledButton("Set", on_click=lambda _: self._set_depth(), height=50),
                                    ],
                                ),
                                ft.Text("Test Time", size=15, weight=ft.FontWeight.W_600),
                                ft.Row(
                                    controls=[
                                        ft.OutlinedButton("-1m", on_click=lambda _: self._advance_test_time(-60)),
                                        ft.OutlinedButton("+1m", on_click=lambda _: self._advance_test_time(60)),
                                        ft.OutlinedButton("+5m", on_click=lambda _: self._advance_test_time(300)),
                                        ft.OutlinedButton("+30m", on_click=lambda _: self._advance_test_time(1800)),
                                        ft.TextButton("Live", on_click=lambda _: self._reset_test_time()),
                                    ],
                                    wrap=True,
                                ),
                            ],
                        ),
                    ),
                    self._card(
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Controls", size=15, weight=ft.FontWeight.W_600),
                                ft.Row(
                                    controls=[
                                        self.primary_button,
                                        self.secondary_button,
                                    ],
                                ),
                                ft.Row(
                                    controls=[
                                        ft.OutlinedButton("Mode", on_click=lambda _: self._dispatch(Intent.MODE), expand=True, height=48),
                                        ft.OutlinedButton("Reset", on_click=lambda _: self._dispatch(Intent.RESET), expand=True, height=48),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    self._card(
                        ft.Column(
                            expand=True,
                            spacing=10,
                            controls=[
                                ft.Text("Event Log", size=16, weight=ft.FontWeight.W_600),
                                ft.Container(
                                    expand=True,
                                    border=ft.border.all(1, self.CARD_BORDER),
                                    border_radius=12,
                                    padding=12,
                                    content=self.log_view,
                                ),
                            ],
                        ),
                        expand=True,
                    ),
                ],
            )
        )
        self.page.run_task(self._refresh_loop)
        self._render()

    def _sync_depth_input(self) -> None:
        self.engine.set_depth_text(self.depth_input.value or "")

    def _set_depth(self) -> None:
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

    async def _refresh_loop(self) -> None:
        while self.page.session is not None:
            self._render()
            await asyncio.sleep(0.1)

    def _render(self) -> None:
        snap = self.engine.snapshot()
        self.mode_text.value = f"Mode: {snap.mode_text}"
        self.status_value_text.value = snap.status_value_text
        self.primary_text.value = snap.primary_value_text
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
        self._apply_phase_colors(snap)

        log_lines = self.engine.state.ui_log[-30:]
        if log_lines != self._last_log_rendered:
            self.log_view.controls = [ft.Text(line, selectable=True, size=13) for line in log_lines]
            self._last_log_rendered = log_lines

        self.page.update()

    def _apply_phase_colors(self, snap) -> None:
        self.status_label_text.color = self.DEFAULT_TEXT_COLOR
        self.status_value_text.color = self._kind_color(snap.status_value_kind)
        self.primary_text.color = self._kind_color(snap.primary_value_kind)
        self.remaining_text.color = self.DEFAULT_TEXT_COLOR
        self.detail_text.color = self.MUTED_TEXT_COLOR
        self.mode_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_timer_text.color = self._kind_color(snap.depth_timer_kind)
        self.test_time_text.color = self.MUTED_TEXT_COLOR

        self.summary_prefix_text.color = self.DEFAULT_TEXT_COLOR
        self.summary_value_text.color = self._kind_color(snap.summary_value_kind)

    def _kind_color(self, kind: str) -> str:
        if kind == "o2":
            return self.O2_COLOR
        if kind == "air_break":
            return self.AIR_BREAK_COLOR
        return self.DEFAULT_TEXT_COLOR

    def _card(self, content: ft.Control, *, emphasized: bool = False, expand: bool = False) -> ft.Container:
        return ft.Container(
            expand=expand,
            border_radius=18,
            padding=16,
            bgcolor=self.SURFACE_CARD if emphasized else self.CONTROL_CARD,
            border=ft.border.all(1, self.CARD_BORDER),
            content=content,
        )


def main(page: ft.Page) -> None:
    MobileDiveStopwatchApp(page).mount()
