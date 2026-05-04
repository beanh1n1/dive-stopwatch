from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dive_stopwatch.engine_v2 import EngineAction, MixedGasEngine
from dive_stopwatch.engine_v2.contracts.timers import TimerState
from dive_stopwatch.engine_v2.modes.mixed_gas.plan import build_mixed_gas_plan
from dive_stopwatch.engine_v2.modes.mixed_gas.state import MixedGasPlan, MixedGasStop, MixedGasTimer, MixedGasTimerKind


_HEADER = ",".join(
    (
        "depth_fsw",
        "bottom_time_min",
        "gas_mix",
        "time_to_first_stop",
        "stop_190",
        "stop_180",
        "stop_170",
        "stop_160",
        "stop_150",
        "stop_140",
        "stop_130",
        "stop_120",
        "stop_110",
        "stop_100",
        "stop_90",
        "stop_80",
        "stop_70",
        "stop_60",
        "stop_50",
        "stop_40",
        "stop_30",
        "stop_20",
        "total_ascent_time",
        "chamber_o2_periods",
        "section",
        "source_page",
        "notes",
    )
)


class EngineV2MixedGasPlanTests(unittest.TestCase):
    def test_build_plan_returns_none_when_review_csv_has_no_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write(data_dir / "mixed_gas_table_12_4_schedules.csv", _HEADER + "\n")

            plan = build_mixed_gas_plan(
                depth_fsw=150,
                bottom_time_min=20,
                bottom_mix_o2_percent=18.4,
                data_dir=data_dir,
            )

        self.assertIsNone(plan)

    def test_build_plan_loads_exact_reviewed_schedule_and_derives_stop_gases(self) -> None:
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write(
                data_dir / "mixed_gas_table_12_4_schedules.csv",
                "\n".join(
                    [
                        _HEADER,
                        self._row(
                            depth_fsw=150,
                            bottom_time_min=20,
                            gas_mix="18.4-20.1",
                            time_to_first_stop="03:00",
                            section="decompression",
                            source_page="123",
                            notes="fixture",
                            stop_90="3",
                            stop_30="12",
                            stop_20="25",
                        ),
                    ]
                )
                + "\n",
            )

            plan = build_mixed_gas_plan(
                depth_fsw=150,
                bottom_time_min=20,
                bottom_mix_o2_percent=18.4,
                data_dir=data_dir,
            )

        assert plan is not None
        self.assertEqual(plan.table_depth_fsw, 150)
        self.assertEqual(plan.table_bottom_time_min, 20)
        self.assertFalse(plan.is_no_decompression)
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops],
            [(90, 3, "50_50"), (30, 12, "o2"), (20, 25, "o2")],
        )

    def test_build_plan_rejects_bottom_mix_outside_reviewed_range(self) -> None:
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write(
                data_dir / "mixed_gas_table_12_4_schedules.csv",
                "\n".join(
                    [
                        _HEADER,
                        self._row(
                            depth_fsw=150,
                            bottom_time_min=20,
                            gas_mix="18.4-20.1",
                            section="no_decompression",
                            source_page="123",
                            notes="fixture",
                        ),
                    ]
                )
                + "\n",
            )

            plan = build_mixed_gas_plan(
                depth_fsw=150,
                bottom_time_min=20,
                bottom_mix_o2_percent=18.3,
                data_dir=data_dir,
            )

        self.assertIsNone(plan)

    def test_build_plan_ignores_zero_duration_stop_values(self) -> None:
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write(
                data_dir / "mixed_gas_table_12_4_schedules.csv",
                "\n".join(
                    [
                        _HEADER,
                        self._row(
                            depth_fsw=180,
                            bottom_time_min=10,
                            gas_mix="14.0-20.1",
                            time_to_first_stop="03:40",
                            section="decompression",
                            source_page="123",
                            notes="fixture",
                            stop_80="7",
                            stop_70="0",
                            stop_60="10",
                            stop_50="10",
                            stop_30="9",
                            stop_20="14",
                        ),
                    ]
                )
                + "\n",
            )

            plan = build_mixed_gas_plan(
                depth_fsw=180,
                bottom_time_min=10,
                bottom_mix_o2_percent=18.4,
                data_dir=data_dir,
            )

        assert plan is not None
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min) for stop in plan.stops],
            [(80, 7), (60, 10), (50, 10), (30, 9), (20, 14)],
        )

    def test_build_plan_loads_reviewed_repo_table_by_default(self) -> None:
        plan = build_mixed_gas_plan(
            depth_fsw=180,
            bottom_time_min=10,
            bottom_mix_o2_percent=18.4,
        )

        assert plan is not None
        self.assertEqual(plan.table_depth_fsw, 180)
        self.assertEqual(plan.table_bottom_time_min, 10)
        self.assertFalse(plan.is_no_decompression)
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops],
            [
                (70, 7, "50_50"),
                (50, 10, "50_50"),
                (40, 10, "50_50"),
                (30, 9, "o2"),
                (20, 14, "o2"),
            ],
        )

    def test_build_plan_snaps_up_to_next_supported_bottom_time_row(self) -> None:
        plan = build_mixed_gas_plan(
            depth_fsw=220,
            bottom_time_min=14,
            bottom_mix_o2_percent=14.0,
        )

        assert plan is not None
        self.assertEqual(plan.table_depth_fsw, 220)
        self.assertEqual(plan.table_bottom_time_min, 20)
        self.assertEqual(
            [(stop.depth_fsw, stop.duration_min, stop.gas) for stop in plan.stops[:3]],
            [(90, 7, "50_50"), (70, 3, "50_50"), (60, 7, "50_50")],
        )

    def test_build_plan_snaps_depth_up_to_next_supported_table_depth(self) -> None:
        plan = build_mixed_gas_plan(
            depth_fsw=199,
            bottom_time_min=10,
            bottom_mix_o2_percent=14.0,
        )

        assert plan is not None
        self.assertEqual(plan.table_depth_fsw, 200)
        self.assertEqual(plan.table_bottom_time_min, 10)

    def test_build_plan_snaps_bottom_times_under_ten_minutes_to_ten_minute_row(self) -> None:
        plan = build_mixed_gas_plan(
            depth_fsw=220,
            bottom_time_min=5,
            bottom_mix_o2_percent=14.0,
        )

        assert plan is not None
        self.assertEqual(plan.table_depth_fsw, 220)
        self.assertEqual(plan.table_bottom_time_min, 10)
        self.assertEqual((plan.stops[0].depth_fsw, plan.stops[0].duration_min), (80, 7))

    def test_leave_bottom_passes_bottom_mix_into_plan_lookup(self) -> None:
        current = {"now": datetime(2026, 4, 29, 12, 0, 0)}
        engine = MixedGasEngine(now_provider=lambda: current["now"])
        engine.state = replace(
            engine.state,
            phase=engine.state.phase.BOTTOM,
            depth_fsw=150,
            bottom_mix_o2_percent=18.4,
            bottom_timer=MixedGasTimer(
                kind=MixedGasTimerKind.BOTTOM,
                timer=TimerState(started_at=current["now"] - timedelta(minutes=20)),
            ),
        )
        plan = MixedGasPlan(
            input_depth_fsw=150,
            input_bottom_time_min=20,
            table_depth_fsw=150,
            table_bottom_time_min=20,
            stops=(MixedGasStop(index=1, depth_fsw=90, gas="50_50", duration_min=3),),
        )

        with patch(
            "dive_stopwatch.engine_v2.modes.mixed_gas.transitions.descent.build_mixed_gas_plan",
            return_value=plan,
        ) as mocked:
            engine.dispatch(EngineAction.LEAVE_BOTTOM)

        mocked.assert_called_once_with(
            depth_fsw=150,
            bottom_time_min=20,
            bottom_mix_o2_percent=18.4,
        )

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content)

    def _row(self, **overrides: str | int) -> str:
        values = {
            "depth_fsw": "",
            "bottom_time_min": "",
            "gas_mix": "",
            "time_to_first_stop": "",
            "stop_190": "",
            "stop_180": "",
            "stop_170": "",
            "stop_160": "",
            "stop_150": "",
            "stop_140": "",
            "stop_130": "",
            "stop_120": "",
            "stop_110": "",
            "stop_100": "",
            "stop_90": "",
            "stop_80": "",
            "stop_70": "",
            "stop_60": "",
            "stop_50": "",
            "stop_40": "",
            "stop_30": "",
            "stop_20": "",
            "total_ascent_time": "",
            "chamber_o2_periods": "",
            "section": "",
            "source_page": "",
            "notes": "",
        }
        values.update({key: str(value) for key, value in overrides.items()})
        ordered = [values[column] for column in _HEADER.split(",")]
        return ",".join(ordered)


if __name__ == "__main__":
    unittest.main()
