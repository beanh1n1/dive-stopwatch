from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.core import EngineV2
from dive_stopwatch.v2.models import IntentV2
from dive_stopwatch.v2.runtime_context import RuntimeContextBuilder


class V2RuntimeContextTests(unittest.TestCase):
    def test_context_builder_matches_engine_rule_flags(self) -> None:
        current = {"now": datetime(2026, 4, 12, 12, 0, 0)}
        engine = EngineV2(now_provider=lambda: current["now"])
        engine.set_depth_text("145")
        engine.dispatch(IntentV2.MODE)  # DIVE
        engine.dispatch(IntentV2.MODE)  # AIR/O2
        engine.dispatch(IntentV2.PRIMARY)  # LS
        current["now"] += timedelta(minutes=3)
        engine.dispatch(IntentV2.PRIMARY)  # RB
        current["now"] += timedelta(minutes=39)
        engine.dispatch(IntentV2.PRIMARY)  # LB

        now = engine.now()
        facts = engine._facts_builder.build(engine.state, now=now)
        profile = engine._active_profile(now, facts=facts)
        ctx = RuntimeContextBuilder().build(engine, now=now, facts=facts, profile=profile)

        self.assertEqual(ctx.decision_inputs.at_o2_stop, engine._is_at_o2_stop(profile))
        self.assertEqual(ctx.decision_inputs.can_start_air_break, engine._can_start_air_break(profile))
        self.assertEqual(ctx.decision_inputs.show_tsv, engine._show_tsv(profile))
        self.assertEqual(ctx.decision_inputs.start_reaches_surface, engine._start_reaches_surface(now))


if __name__ == "__main__":
    unittest.main()
