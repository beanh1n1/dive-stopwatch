from datetime import datetime, timedelta
import unittest

from dive_stopwatch.v2.tables import DecompressionMode
from dive_stopwatch.v2.dive_controller import DiveController
from dive_stopwatch.v2.facts import FactsBuilder
from dive_stopwatch.v2.models import ModeV2, StateV2
from dive_stopwatch.v2.profile_resolver import ProfileResolver


class V2ProfileResolverTests(unittest.TestCase):
    def _build_bottom_facts(self, now: datetime):
        controller = DiveController()
        start = now - timedelta(minutes=5)
        controller.start(start)
        controller.start(start + timedelta(minutes=2))

        state = StateV2()
        state.mode = ModeV2.DIVE
        state.deco_mode = DecompressionMode.AIR
        state.depth_text = "120"
        state.dive = controller

        facts = FactsBuilder().build(state, now=now)
        return facts

    def test_resolve_uses_cached_profile_for_same_facts(self) -> None:
        now = datetime(2026, 4, 12, 10, 0, 0)
        facts = self._build_bottom_facts(now)
        resolver = ProfileResolver()

        first = resolver.resolve(facts)
        second = resolver.resolve(facts)

        self.assertIs(first, second)

    def test_invalidate_forces_rebuild(self) -> None:
        now = datetime(2026, 4, 12, 10, 0, 0)
        facts = self._build_bottom_facts(now)
        resolver = ProfileResolver()

        first = resolver.resolve(facts)
        resolver.invalidate()
        second = resolver.resolve(facts)

        self.assertIsNot(first, second)

    def test_bottom_elapsed_minute_changes_cache_key(self) -> None:
        now = datetime(2026, 4, 12, 10, 0, 0)
        resolver = ProfileResolver()

        first = resolver.resolve(self._build_bottom_facts(now))
        second = resolver.resolve(self._build_bottom_facts(now + timedelta(minutes=1)))

        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
