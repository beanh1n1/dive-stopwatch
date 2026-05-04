from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from dive_stopwatch.engine_v2.contracts.surd_handoff import InWaterToSurdHandoff, SurdEntryKind
from dive_stopwatch.engine_v2.modes.surd.engine import SurdEngine


class EngineV2SurdScaffoldTests(unittest.TestCase):
    def test_surface_interval_uses_shared_timer_primitive(self) -> None:
        current = {"now": datetime(2026, 4, 25, 12, 0, 0)}
        engine = SurdEngine(now_provider=lambda: current["now"])
        handoff = InWaterToSurdHandoff(
            entry_kind=SurdEntryKind.L40_NORMAL,
            source_mode="SURD",
            input_depth_fsw=120,
            input_bottom_time_min=90,
            source_table_depth_fsw=120,
            source_table_bottom_time_min=90,
            left_water_stop_depth_fsw=40,
            remaining_in_water_obligation_sec=0.0,
            handed_off_at=current["now"],
        )

        engine.start_handoff(handoff)
        current["now"] += timedelta(minutes=6)

        view = engine.view()
        self.assertEqual(view.phase_name, "SURFACE_ASCENT_FROM_WATER_STOP")
        self.assertIsNotNone(view.active_timer)
        self.assertEqual(view.active_timer.role.name, "SURFACE_INTERVAL")
        self.assertEqual(view.active_timer.elapsed_sec, 6 * 60)


if __name__ == "__main__":
    unittest.main()
