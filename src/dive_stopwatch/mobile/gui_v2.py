from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import traceback

import flet as ft

from ..engine_v2.contracts.modes import DecoProfile, DivingMode
from ..engine_v2.projection.presentation_builder import PresentationModel
from ..engine_v2.runtime.session import EngineV2Session


@dataclass(frozen=True)
class UiSnapshot:
    mode_text: str
    profile_schedule_text: str
    status_value_text: str
    status_value_kind: str
    primary_value_text: str
    primary_value_kind: str
    depth_text: str
    depth_timer_text: str
    depth_timer_kind: str
    remaining_text: str
    summary_text: str
    summary_value_kind: str
    detail_text: str
    primary_button_label: str
    secondary_button_label: str
    primary_button_enabled: bool
    secondary_button_enabled: bool


class MobileDiveStopwatchV2App:
    O2_COLOR = ft.Colors.GREEN_700
    AIR_BREAK_COLOR = ft.Colors.RED_700
    WARNING_COLOR = ft.Colors.RED_700
    CAUTION_COLOR = ft.Colors.ORANGE_700
    SURD_TRAVEL_COLOR = "#5DA9FF"
    SURD_GLOW = "#0E2742"
    MODE_AIR_O2_ACCENT = "#2DE3A0"
    MODE_AIR_O2_GLOW = "#11392B"
    MODE_MIXED_GAS_ACCENT = "#A77A45"
    MODE_MIXED_GAS_GLOW = "#2A1C0D"
    MODE_CHAMBER_ACCENT = ft.Colors.RED_700
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
    BRAND_FONT = "VintageHand"
    READY_LAUNCH_OPTIONS = (
        (DivingMode.AIR, DecoProfile.AIR),
        (DivingMode.AIR, DecoProfile.O2),
        (DivingMode.AIR, DecoProfile.SURD),
        (DivingMode.MIXED_GAS, DecoProfile.MIXED_GAS),
        (DivingMode.MIXED_GAS, DecoProfile.SURD),
        (DivingMode.CHAMBER, DecoProfile.AIR),
    )

    def __init__(self, page: ft.Page, session: EngineV2Session | None = None) -> None:
        self.page = page
        self.session = session or EngineV2Session(diving_mode=DivingMode.AIR, deco_profile=DecoProfile.AIR)
        self.recall_active = False
        self._last_log_rendered: tuple[str, ...] = ()
        self._last_error_message: str | None = None
        self.depth_input = ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER,
            width=64,
            dense=True,
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
        self.relief_depth_input = ft.TextField(
            keyboard_type=ft.KeyboardType.NUMBER,
            width=84,
            dense=True,
            hint_text="relief",
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
            on_change=lambda _: self._sync_relief_depth_input(),
        )
        self.gas_mix_input = ft.TextField(
            width=96,
            dense=True,
            hint_text="",
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
            on_change=lambda _: self._sync_gas_mix_input(),
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
            on_click=lambda _: self._cycle_mode(),
            content=self.mode_label_text,
        )
        self.recall_button = ft.OutlinedButton(
            "Recall",
            on_click=lambda _: self._toggle_recall(),
            expand=True,
            height=48,
            style=self._utility_button_style(),
        )
        self.reset_button = ft.OutlinedButton(
            "Reset",
            on_click=lambda _: self._dispatch_named("RESET"),
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
        self.relief_unit_text = ft.Text("relief", size=18, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.gas_mix_unit_text = ft.Text("% O2", size=18, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.depth_input_row = ft.Row(
            spacing=8,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.depth_input, self.depth_unit_text],
        )
        self.relief_input_row = ft.Row(
            spacing=8,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.relief_depth_input, self.relief_unit_text],
        )
        self.gas_mix_input_row = ft.Row(
            spacing=8,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.gas_mix_input, self.gas_mix_unit_text],
        )
        self.depth_separator_text = ft.Text("|", size=18, weight=ft.FontWeight.W_600, color=self.MUTED_TEXT_COLOR, visible=False, font_family=self.INSTRUMENT_FONT)
        self.depth_timer_text = ft.Text(size=20, weight=ft.FontWeight.W_600, visible=False, font_family=self.INSTRUMENT_FONT)
        self.depth_row = ft.Row(
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.depth_text, self.depth_input_row, self.gas_mix_input_row, self.relief_input_row, self.depth_separator_text, self.depth_timer_text],
        )
        self.remaining_text = ft.Text(size=16, weight=ft.FontWeight.W_500, font_family=self.INSTRUMENT_FONT)
        self.summary_prefix_text = ft.Text(size=17, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.summary_value_text = ft.Text(size=17, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.summary_text = ft.Text(size=17, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.summary_row = ft.Row(
            spacing=0,
            wrap=True,
            controls=[self.summary_prefix_text, self.summary_value_text, self.summary_text],
        )
        self.detail_text = ft.Text(size=14, italic=True, font_family=self.INSTRUMENT_FONT)
        self.error_text = ft.Text(
            size=13,
            color=self.WARNING_COLOR,
            visible=False,
            font_family=self.INSTRUMENT_FONT,
        )
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
        self.recall_header_label = ft.Text("Dive Log", size=16, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR)
        self.recall_schedule_text = ft.Text(size=16, weight=ft.FontWeight.W_700, color=self.MUTED_TEXT_COLOR, font_family=self.INSTRUMENT_FONT)
        self.primary_button = ft.FilledButton(
            text="Primary",
            on_click=lambda _: self._dispatch_primary(),
            expand=True,
            height=58,
            style=self._primary_button_style(),
        )
        self.secondary_button = ft.OutlinedButton(
            text="-",
            on_click=lambda _: self._dispatch_secondary(),
            expand=True,
            height=58,
            style=self._secondary_button_style("", self._default_secondary_style()),
        )
        self.primary_header = ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            controls=[self.mode_label_chip, self.recall_timer_text],
        )
        self.primary_live_body = ft.Column(
            spacing=14,
            controls=[
                ft.Row(spacing=8, controls=[self.status_label_text, self.status_value_text]),
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
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[self.recall_header_label, self.recall_schedule_text],
                ),
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
            controls=[self.primary_header, self.primary_body_switcher],
        )

    def mount(self) -> None:
        self.page.title = "CAISSON Instruments Mobile"
        self.page.padding = 14
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.fonts = {
            self.INSTRUMENT_FONT: str(Path(__file__).resolve().parents[3] / "assets" / "fonts" / "CaissonCockpit.ttf"),
            self.BRAND_FONT: str(Path(__file__).resolve().parents[3] / "assets" / "fonts" / "vintage_hand_type.otf"),
        }
        self.page.window_min_width = 360
        self.page.window_min_height = 720
        self.page.window_width = 430
        self.page.bgcolor = self.APP_BACKGROUND
        self.page.appbar = ft.AppBar(
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    ft.Container(
                        padding=ft.padding.only(top=4),
                        content=ft.Text(
                            "Caisson",
                            size=40,
                            weight=ft.FontWeight.W_400,
                            font_family=self.BRAND_FONT,
                            color=self.DEFAULT_TEXT_COLOR,
                            style=ft.TextStyle(letter_spacing=2.0),
                        ),
                    ),
                    ft.Container(
                        padding=ft.padding.only(left=1, bottom=11.4),
                        content=ft.Text(
                            "Instruments",
                            size=26,
                            weight=ft.FontWeight.W_700,
                            font_family=self.INSTRUMENT_FONT,
                            color=self.DEFAULT_TEXT_COLOR,
                            style=ft.TextStyle(letter_spacing=0.4),
                        ),
                    ),
                ],
            ),
            center_title=False,
            bgcolor=self.APPBAR_BACKGROUND,
            color=self.DEFAULT_TEXT_COLOR,
            elevation=2,
        )
        self.test_time_card = self._card(
            ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[self.test_time_label, self.test_time_text],
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
        )
        self.page.add(
            ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    self._card(self.primary_card_body, emphasized=True),
                    self._card(
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Controls", size=15, weight=ft.FontWeight.W_700, color=self.DEFAULT_TEXT_COLOR, font_family=self.INSTRUMENT_FONT),
                                ft.Row(controls=[self.primary_button, self.secondary_button]),
                                ft.Row(controls=[self.recall_button, self.reset_button]),
                                self.error_text,
                            ],
                        ),
                    ),
                    self.test_time_card,
                ],
            )
        )
        self.page.run_task(self._refresh_loop)
        self._render()

    def _sync_depth_input(self) -> None:
        self.session.set_depth_text(self.depth_input.value or "")

    def _sync_relief_depth_input(self) -> None:
        self.session.set_relief_depth_text(self.relief_depth_input.value or "")

    def _sync_gas_mix_input(self) -> None:
        self.session.set_bottom_mix_text(self.gas_mix_input.value or "")

    def _dispatch_primary(self) -> None:
        model = self.session.presentation_model()
        if model.primary_action is not None:
            self._dispatch_named(model.primary_action.action_name)

    def _dispatch_secondary(self) -> None:
        model = self.session.presentation_model()
        if model.secondary_action is not None:
            self._dispatch_named(model.secondary_action.action_name)
            return

    def _dispatch_named(self, action_name: str) -> None:
        self._run_and_render(
            self._sync_depth_input,
            self._sync_gas_mix_input,
            self._sync_relief_depth_input,
            lambda: self.session.dispatch(action_name),
        )

    def _advance_test_time(self, delta_seconds: float) -> None:
        self._run_and_render(lambda: self.session.advance_test_time(delta_seconds))

    def _toggle_recall(self) -> None:
        self.recall_active = not self.recall_active
        self._render()

    def _run_and_render(self, *actions) -> None:
        try:
            for action in actions:
                action()
            self._last_error_message = None
            self._render()
        except Exception as exc:
            self._handle_ui_error(exc)

    def _cycle_mode(self) -> None:
        current_option = (self.session.diving_mode, self.session.deco_profile)
        options = self.READY_LAUNCH_OPTIONS
        try:
            current_index = options.index(current_option)
        except ValueError:
            current_index = 0
        next_mode, next_profile = options[(current_index + 1) % len(options)]
        depth_text = self.session.depth_input_text()
        bottom_mix_text = self.session.bottom_mix_input_text()
        relief_text = self.session.relief_depth_input_text()
        self.session.launch(next_mode, next_profile)
        if depth_text:
            self.session.set_depth_text(depth_text)
        if bottom_mix_text:
            self.session.set_bottom_mix_text(bottom_mix_text)
        if relief_text:
            self.session.set_relief_depth_text(relief_text)
        self.recall_active = False
        self._render()

    async def _refresh_loop(self) -> None:
        while self.page.session is not None:
            try:
                self._render()
            except Exception as exc:
                self._handle_ui_error(exc)
            await asyncio.sleep(0.1)

    def _render(self) -> None:
        model = self.session.presentation_model()
        snap = self._snapshot_from_presentation(model)
        editable_depth = self._editable_depth(model)
        editable_gas_mix = self._editable_gas_mix(model)
        editable_relief = self._editable_relief(model)
        self.depth_input.value = self.session.depth_input_text()
        self.gas_mix_input.value = self.session.bottom_mix_input_text()
        self.relief_depth_input.value = self.session.relief_depth_input_text()
        self._render_mode_tile(snap.mode_text)
        self.status_value_text.value = snap.status_value_text
        self.primary_text.value = snap.primary_value_text
        self.depth_input_row.visible = editable_depth
        self.gas_mix_input_row.visible = editable_gas_mix
        self.relief_input_row.visible = editable_relief
        self.depth_text.visible = not editable_depth and not editable_gas_mix and not editable_relief
        self.depth_text.value = snap.depth_text
        self.depth_separator_text.visible = bool(snap.depth_timer_text)
        self.depth_timer_text.visible = bool(snap.depth_timer_text)
        self.depth_timer_text.value = snap.depth_timer_text
        self.remaining_text.value = snap.remaining_text
        self.remaining_text.visible = bool(snap.remaining_text)
        self.detail_text.value = snap.detail_text
        self.detail_text.visible = bool(snap.detail_text)
        self.error_text.value = "" if self._last_error_message is None else self._last_error_message
        self.error_text.visible = self._last_error_message is not None
        self.test_time_text.value = self.session.test_time_label()
        self.test_time_card.visible = True
        self.primary_button.text = snap.primary_button_label or "-"
        self.primary_button.disabled = not snap.primary_button_enabled
        self.secondary_button.text = snap.secondary_button_label or "-"
        self.secondary_button.disabled = not snap.secondary_button_enabled
        self._render_summary(snap)
        self.summary_row.visible = bool(snap.summary_text)
        self._apply_phase_colors(snap)
        self._apply_button_styles(snap)
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
        self.recall_schedule_text.value = snap.profile_schedule_text
        self.recall_schedule_text.visible = bool(self.recall_schedule_text.value)

        log_lines = self._recall_lines(model)
        if log_lines != self._last_log_rendered:
            self.log_text.value = "\n".join(log_lines)
            self._last_log_rendered = log_lines

        self.page.update()

    def _handle_ui_error(self, exc: Exception) -> None:
        traceback.print_exc()
        self._last_error_message = f"{type(exc).__name__}: {exc}"
        self.error_text.value = self._last_error_message
        self.error_text.visible = True
        try:
            self.page.update()
        except Exception:
            traceback.print_exc()

    def _editable_depth(self, model: PresentationModel) -> bool:
        if self.session.diving_mode is DivingMode.AIR:
            return model.phase_label in {"Ready", "Bottom"}
        if self.session.diving_mode is DivingMode.MIXED_GAS:
            return model.phase_label == "Ready"
        return False

    def _editable_gas_mix(self, model: PresentationModel) -> bool:
        return self.session.diving_mode is DivingMode.MIXED_GAS and model.phase_label == "Ready"

    def _editable_relief(self, model: PresentationModel) -> bool:
        return self.session.diving_mode is DivingMode.CHAMBER and model.phase_label == "At 60 Waiting Table Selection"

    def _snapshot_from_presentation(self, model: PresentationModel) -> UiSnapshot:
        mode_text = self._mode_tile_label()
        primary_value_kind = self._primary_value_kind(model)
        status_value_kind = self._status_value_kind(model)
        depth_timer_kind = self._depth_timer_kind(model)
        summary_value_kind = self._summary_value_kind(model)
        profile_schedule_text = model.schedule_label
        secondary_button_label = "" if model.secondary_action is None else model.secondary_action.label
        secondary_button_enabled = model.secondary_action is not None
        secondary_button_dispatch_enabled = model.secondary_action is not None and model.secondary_action.action_name != ""
        return UiSnapshot(
            mode_text=mode_text,
            profile_schedule_text=profile_schedule_text,
            status_value_text=model.status_value_text,
            status_value_kind=status_value_kind,
            primary_value_text=model.primary_value,
            primary_value_kind=primary_value_kind,
            depth_text=model.depth_inline_text or "",
            depth_timer_text=model.depth_timer_label or "",
            depth_timer_kind=depth_timer_kind,
            remaining_text=model.remaining_label or "",
            summary_text=model.summary_text,
            summary_value_kind=model.summary_kind,
            detail_text=model.detail_text,
            primary_button_label="" if model.primary_action is None else model.primary_action.label,
            secondary_button_label=secondary_button_label,
            primary_button_enabled=model.primary_action is not None and model.primary_action.action_name != "",
            secondary_button_enabled=secondary_button_dispatch_enabled,
        )

    def _recall_lines(self, model: PresentationModel) -> tuple[str, ...]:
        return tuple(f"{row.at_label}  {row.summary}" for row in model.log_rows)

    def _primary_value_kind(self, model: PresentationModel) -> str:
        if model.mode_name == "CHAMBER" and model.gas_label == "Air Break":
            return "default"
        if model.gas_label == "Air Break":
            return "air_break"
        if model.gas_label == "On O2":
            return "o2"
        if model.mode_name == "SURD" and model.gas_label == "Surface":
            return "surd_travel"
        return "default"

    def _breathing_mix_kind(self, model: PresentationModel) -> str:
        if model.mode_name == "CHAMBER" and model.gas_label == "Air Break":
            return "default"
        if model.gas_label == "Air Break":
            return "air_break"
        if model.mode_name in {"SURD", "CHAMBER"} and model.gas_label == "Waiting On O2":
            return "default"
        if model.gas_label in {"On O2", "Waiting On O2"}:
            return "o2"
        if model.gas_label == "Off O2":
            return "off_o2"
        if model.mode_name == "MIXED_GAS":
            if model.gas_label == "Bottom Mix":
                return "bottom_mix"
            if model.gas_label in {"Heliox 50 50", "Waiting On 50 50"}:
                return "heliox_50_50"
        if model.mode_name == "SURD" and model.gas_label == "Surface":
            return "surd_travel"
        return "default"

    def _status_value_kind(self, model: PresentationModel) -> str:
        alert_kind = self._alert_kind(model)
        mix_kind = self._breathing_mix_kind(model)
        if mix_kind == "o2":
            return mix_kind
        if alert_kind == "caution" and mix_kind in {"bottom_mix", "heliox_50_50"}:
            return mix_kind
        if alert_kind is not None:
            return alert_kind
        return mix_kind

    def _alert_kind(self, model: PresentationModel) -> str | None:
        if not model.warning_labels:
            return None
        if "Surface Interval Penalty" in model.warning_labels:
            return "caution"
        return "error"

    def _depth_timer_kind(self, model: PresentationModel) -> str:
        if model.mode_name == "CHAMBER" and model.gas_label == "Air Break":
            return "default"
        if model.gas_label == "Air Break":
            return "air_break"
        if model.gas_label == "On O2":
            return "o2"
        return "default"

    def _summary_value_kind(self, model: PresentationModel) -> str:
        return model.summary_kind

    def _apply_phase_colors(self, snap: UiSnapshot) -> None:
        self.status_label_text.color = self.DEFAULT_TEXT_COLOR
        self.status_value_text.color = self._kind_color(snap.status_value_kind)
        self.primary_text.color = self.AIR_BREAK_COLOR if snap.status_value_kind == "off_o2" else self._kind_color(snap.primary_value_kind)
        self.remaining_text.color = self.DEFAULT_TEXT_COLOR
        self.detail_text.color = self.MUTED_TEXT_COLOR
        self.depth_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_input.color = self.DEFAULT_TEXT_COLOR
        self.relief_depth_input.color = self.DEFAULT_TEXT_COLOR
        self.depth_unit_text.color = self.DEFAULT_TEXT_COLOR
        self.depth_timer_text.color = self._kind_color(snap.depth_timer_kind)
        self.test_time_text.color = self.MUTED_TEXT_COLOR
        self.recall_timer_text.color = self.AIR_BREAK_COLOR if snap.status_value_kind == "off_o2" else self._kind_color(snap.primary_value_kind)
        self.summary_prefix_text.color = self.DEFAULT_TEXT_COLOR
        self.summary_value_text.color = self._kind_color(snap.summary_value_kind) if self.summary_prefix_text.visible else self.DEFAULT_TEXT_COLOR
        self.summary_text.color = self._kind_color(snap.summary_value_kind)

    def _apply_button_styles(self, snap: UiSnapshot) -> None:
        self.primary_button.style = self._primary_button_style()
        self.secondary_button.style = self._secondary_button_style(snap.secondary_button_label, self._default_secondary_style())

    def _render_mode_tile(self, mode_text: str) -> None:
        theme = self._mode_chip_theme(mode_text)
        self.mode_label_text.value = mode_text
        self.mode_label_text.color = self._mode_tile_text_color(mode_text)
        self.mode_label_chip.bgcolor = self.PRIMARY_BUTTON_BG
        self.mode_label_chip.border = ft.border.all(1, theme["border"])
        self.mode_label_chip.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=theme["blur_radius"],
            color=theme["glow"],
            offset=ft.Offset(0, 4),
        )

    def _render_summary(self, snap: UiSnapshot) -> None:
        prefix, value, plain = self._summary_parts(snap.summary_text)
        if prefix is not None:
            self.summary_prefix_text.visible = True
            self.summary_prefix_text.value = prefix
            self.summary_value_text.visible = True
            self.summary_value_text.value = value
            self.summary_value_text.italic = snap.summary_text == "Next: Input Max Depth for table/schedule"
            self.summary_text.visible = False
            self.summary_text.value = ""
            self.summary_text.italic = False
            return
        self.summary_prefix_text.visible = False
        self.summary_prefix_text.value = ""
        self.summary_value_text.visible = False
        self.summary_value_text.value = ""
        self.summary_value_text.italic = False
        self.summary_text.visible = True
        self.summary_text.value = plain
        self.summary_text.italic = snap.summary_text == "Next: Input Max Depth for table/schedule"

    def _kind_color(self, kind: str) -> str:
        return {
            "default": self.DEFAULT_TEXT_COLOR,
            "o2": self.O2_COLOR,
            "bottom_mix": self.MODE_MIXED_GAS_ACCENT,
            "heliox_50_50": "#C79B64",
            "warning": self.WARNING_COLOR,
            "caution": self.CAUTION_COLOR,
            "air_break": self.AIR_BREAK_COLOR,
            "error": self.AIR_BREAK_COLOR,
            "surd_travel": self.SURD_TRAVEL_COLOR,
            "off_o2": self.DEFAULT_TEXT_COLOR,
        }.get(kind, self.DEFAULT_TEXT_COLOR)

    def _mode_chip_theme(self, mode_text: str) -> dict[str, str | int]:
        if mode_text == "AIR/O2":
            return {"border": self.MODE_AIR_O2_ACCENT, "glow": self.MODE_AIR_O2_GLOW, "blur_radius": 14}
        if mode_text.endswith("/SURD"):
            return {"border": self.SURD_TRAVEL_COLOR, "glow": self.SURD_GLOW, "blur_radius": 14}
        if mode_text.startswith("Mixed Gas"):
            return {"border": self.MODE_MIXED_GAS_ACCENT, "glow": self.MODE_MIXED_GAS_GLOW, "blur_radius": 10}
        if mode_text == "CHAMBER":
            return {"border": self.MODE_CHAMBER_ACCENT, "glow": self.BUTTON_SHADOW, "blur_radius": 10}
        return {"border": self.OUTLINE_ACCENT, "glow": self.BUTTON_SHADOW, "blur_radius": 10}

    def _mode_tile_text_color(self, mode_text: str) -> str:
        if mode_text in {"Mixed Gas", "Mixed/SURD"}:
            return self.MODE_MIXED_GAS_ACCENT
        return self.PRIMARY_BUTTON_TEXT

    def _secondary_button_style(self, label: str, default_style: ft.ButtonStyle) -> ft.ButtonStyle:
        if label == "On Bottom-mix":
            return ft.ButtonStyle(
                side=ft.BorderSide(2, self.MODE_MIXED_GAS_ACCENT),
                shape=ft.RoundedRectangleBorder(radius=14),
                color=self.MODE_MIXED_GAS_ACCENT,
                bgcolor=self.BUTTON_SURFACE,
                padding=ft.padding.symmetric(vertical=14, horizontal=16),
                shadow_color=self.BUTTON_SHADOW,
                elevation=4,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
            )
        if label == "Confirm 50/50":
            lighter_buff = "#C79B64"
            return ft.ButtonStyle(
                side=ft.BorderSide(2, lighter_buff),
                shape=ft.RoundedRectangleBorder(radius=14),
                color=lighter_buff,
                bgcolor=self.BUTTON_SURFACE,
                padding=ft.padding.symmetric(vertical=14, horizontal=16),
                shadow_color=self.BUTTON_SHADOW,
                elevation=4,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
            )
        if label != "On O2":
            return default_style
        return ft.ButtonStyle(
            side=ft.BorderSide(2, self.O2_COLOR),
            shape=ft.RoundedRectangleBorder(radius=14),
            color=self.O2_COLOR,
            bgcolor=self.BUTTON_SURFACE,
            padding=ft.padding.symmetric(vertical=14, horizontal=16),
            shadow_color=self.BUTTON_SHADOW,
            elevation=4,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
        )

    def _mode_tile_label(self) -> str:
        diving_mode = self.session.diving_mode
        deco_profile = self.session.deco_profile
        if deco_profile is DecoProfile.TREATMENT or diving_mode is DivingMode.CHAMBER:
            return "CHAMBER"
        if diving_mode is DivingMode.AIR and deco_profile is DecoProfile.O2:
            return "AIR/O2"
        if diving_mode is DivingMode.AIR and deco_profile is DecoProfile.SURD:
            return "AIR/SURD"
        if diving_mode is DivingMode.MIXED_GAS and deco_profile is DecoProfile.SURD:
            return "Mixed/SURD"
        if diving_mode is DivingMode.MIXED_GAS:
            return "Mixed Gas"
        return "AIR"

    def _summary_parts(self, text: str) -> tuple[str | None, str, str]:
        if text.startswith("Next: "):
            return "Next: ", text.removeprefix("Next: "), ""
        return None, "", text

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
            color=self.DEFAULT_TEXT_COLOR,
            bgcolor="#121922",
            shadow_color=self.BUTTON_SHADOW,
            elevation=4,
            text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600, font_family=self.INSTRUMENT_FONT),
        )

    def _primary_button_style(self) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=14),
            bgcolor=self.PRIMARY_BUTTON_BG,
            color=self.PRIMARY_BUTTON_TEXT,
            padding=ft.padding.symmetric(vertical=14, horizontal=16),
            shadow_color=self.BUTTON_SHADOW,
            elevation=8,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
        )

    def _default_secondary_style(self) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            side=ft.BorderSide(1, self.OUTLINE_ACCENT),
            shape=ft.RoundedRectangleBorder(radius=14),
            color=self.DEFAULT_TEXT_COLOR,
            bgcolor=self.BUTTON_SURFACE,
            padding=ft.padding.symmetric(vertical=14, horizontal=16),
            shadow_color=self.BUTTON_SHADOW,
            elevation=4,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700, font_family=self.INSTRUMENT_FONT),
        )


def main(page: ft.Page) -> None:
    MobileDiveStopwatchV2App(page).mount()
