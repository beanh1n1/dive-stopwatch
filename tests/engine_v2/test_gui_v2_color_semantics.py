from __future__ import annotations

import sys
from types import SimpleNamespace
import types
import unittest


class _FakeColors:
    GREEN_700 = "#0a0"
    RED_700 = "#a00"
    ORANGE_700 = "#fa0"
    WHITE = "#fff"


sys.modules.setdefault("flet", types.SimpleNamespace(Colors=_FakeColors))

from dive_stopwatch.engine_v2.contracts.modes import DecoProfile, DivingMode
from dive_stopwatch.mobile.gui_v2 import MobileDiveStopwatchV2App


class GuiV2ColorSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = object.__new__(MobileDiveStopwatchV2App)

    def _model(self, *, mode_name: str, gas_label: str, warning_labels: tuple[str, ...] = ()) -> SimpleNamespace:
        return SimpleNamespace(mode_name=mode_name, gas_label=gas_label, warning_labels=warning_labels)

    def test_status_kind_uses_bottom_mix_tint(self) -> None:
        model = self._model(mode_name="MIXED_GAS", gas_label="Bottom Mix")
        self.assertEqual(self.app._status_value_kind(model), "bottom_mix")

    def test_status_kind_uses_heliox_tint_while_waiting_on_50_50(self) -> None:
        model = self._model(mode_name="MIXED_GAS", gas_label="Waiting On 50 50")
        self.assertEqual(self.app._status_value_kind(model), "heliox_50_50")

    def test_status_kind_uses_heliox_tint_on_50_50(self) -> None:
        model = self._model(mode_name="MIXED_GAS", gas_label="Heliox 50 50")
        self.assertEqual(self.app._status_value_kind(model), "heliox_50_50")

    def test_status_kind_keeps_surd_waiting_on_o2_white_until_confirmed(self) -> None:
        model = self._model(mode_name="SURD", gas_label="Waiting On O2")
        self.assertEqual(self.app._status_value_kind(model), "default")

    def test_status_kind_keeps_chamber_waiting_on_o2_white_until_confirmed(self) -> None:
        model = self._model(mode_name="CHAMBER", gas_label="Waiting On O2")
        self.assertEqual(self.app._status_value_kind(model), "default")

    def test_chamber_air_break_stays_white(self) -> None:
        model = self._model(mode_name="CHAMBER", gas_label="Air Break")
        self.assertEqual(self.app._status_value_kind(model), "default")
        self.assertEqual(self.app._primary_value_kind(model), "default")
        self.assertEqual(self.app._depth_timer_kind(model), "default")

    def test_warning_overrides_gas_tint_as_error(self) -> None:
        model = self._model(mode_name="MIXED_GAS", gas_label="Bottom Mix", warning_labels=("unsupported",))
        self.assertEqual(self.app._status_value_kind(model), "error")

    def test_surface_interval_penalty_is_caution(self) -> None:
        model = self._model(mode_name="SURD", gas_label="Surface", warning_labels=("Surface Interval Penalty",))
        self.assertEqual(self.app._status_value_kind(model), "caution")

    def test_surface_interval_penalty_does_not_override_on_o2_green(self) -> None:
        model = self._model(mode_name="SURD", gas_label="On O2", warning_labels=("Surface Interval Penalty",))
        self.assertEqual(self.app._status_value_kind(model), "o2")

    def test_any_warning_does_not_override_on_o2_green(self) -> None:
        model = self._model(mode_name="SURD", gas_label="On O2", warning_labels=("AIR_BREAK_DUE",))
        self.assertEqual(self.app._status_value_kind(model), "o2")


class GuiV2ReadyModeTileTests(unittest.TestCase):
    def test_mode_tile_text_uses_buff_for_mixed_gas_tiles_only(self) -> None:
        app = object.__new__(MobileDiveStopwatchV2App)

        self.assertEqual(app._mode_tile_text_color("Mixed Gas"), app.MODE_MIXED_GAS_ACCENT)
        self.assertEqual(app._mode_tile_text_color("Mixed/SURD"), app.MODE_MIXED_GAS_ACCENT)
        self.assertEqual(app._mode_tile_text_color("AIR"), app.PRIMARY_BUTTON_TEXT)
        self.assertEqual(app._mode_tile_text_color("AIR/SURD"), app.PRIMARY_BUTTON_TEXT)

    def test_mode_tile_label_reflects_dedicated_ready_launch_tiles(self) -> None:
        app = object.__new__(MobileDiveStopwatchV2App)

        cases = (
            (DivingMode.AIR, DecoProfile.AIR, "AIR"),
            (DivingMode.AIR, DecoProfile.O2, "AIR/O2"),
            (DivingMode.AIR, DecoProfile.SURD, "AIR/SURD"),
            (DivingMode.MIXED_GAS, DecoProfile.MIXED_GAS, "Mixed Gas"),
            (DivingMode.MIXED_GAS, DecoProfile.SURD, "Mixed/SURD"),
            (DivingMode.CHAMBER, DecoProfile.AIR, "CHAMBER"),
        )

        for diving_mode, deco_profile, expected in cases:
            app.session = SimpleNamespace(diving_mode=diving_mode, deco_profile=deco_profile)
            self.assertEqual(app._mode_tile_label(), expected)

    def test_cycle_mode_advances_through_dedicated_ready_launch_options(self) -> None:
        app = object.__new__(MobileDiveStopwatchV2App)
        launches: list[tuple[DivingMode, DecoProfile]] = []

        class _FakeSession:
            def __init__(self) -> None:
                self.diving_mode = DivingMode.AIR
                self.deco_profile = DecoProfile.AIR

            def depth_input_text(self) -> str:
                return "150"

            def bottom_mix_input_text(self) -> str:
                return "18.4"

            def relief_depth_input_text(self) -> str:
                return ""

            def launch(self, diving_mode: DivingMode, deco_profile: DecoProfile) -> None:
                launches.append((diving_mode, deco_profile))
                self.diving_mode = diving_mode
                self.deco_profile = deco_profile

            def set_depth_text(self, _: str) -> None:
                pass

            def set_bottom_mix_text(self, _: str) -> None:
                pass

            def set_relief_depth_text(self, _: str) -> None:
                pass

        app.session = _FakeSession()
        app.recall_active = False
        app._render = lambda: None

        for _ in range(6):
            app._cycle_mode()

        self.assertEqual(
            launches,
            [
                (DivingMode.AIR, DecoProfile.O2),
                (DivingMode.AIR, DecoProfile.SURD),
                (DivingMode.MIXED_GAS, DecoProfile.MIXED_GAS),
                (DivingMode.MIXED_GAS, DecoProfile.SURD),
                (DivingMode.CHAMBER, DecoProfile.AIR),
                (DivingMode.AIR, DecoProfile.AIR),
            ],
        )


if __name__ == "__main__":
    unittest.main()
