from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from .tables import build_basic_decompression_profile, build_basic_decompression_profile_for_session

from .dive_controller import DivePhase
from .facts import DiveFacts


class ProfileResolver:
    def __init__(self) -> None:
        self._cached_key: tuple[Any, ...] | None = None
        self._cached_profile = None

    def invalidate(self) -> None:
        self._cached_key = None
        self._cached_profile = None

    def resolve(self, facts: DiveFacts) -> Any:
        key = self._cache_key(facts)
        if key == self._cached_key:
            return self._cached_profile
        profile = self._build_profile(facts)
        self._cached_key = key
        self._cached_profile = profile
        return profile

    def _cache_key(self, facts: DiveFacts) -> tuple[Any, ...]:
        session_signature = tuple(
            sorted((code, event.timestamp) for code, event in facts.dive.session.events.items())
        )
        bottom_minutes = None
        if facts.phase is DivePhase.BOTTOM:
            ls = facts.dive.session.events.get("LS")
            if ls is not None:
                bottom_minutes = math.ceil((facts.now - ls.timestamp).total_seconds() / 60.0)
        return (
            facts.mode,
            facts.deco_mode,
            facts.phase,
            facts.parsed_depth_fsw,
            session_signature,
            bottom_minutes,
        )

    @staticmethod
    def _build_profile(facts: DiveFacts):
        depth = facts.parsed_depth_fsw
        if depth is None:
            return None
        if facts.phase is DivePhase.BOTTOM:
            ls = facts.dive.session.events.get("LS")
            if ls is None:
                return None
            minutes = math.ceil((facts.now - ls.timestamp).total_seconds() / 60.0)
            return build_basic_decompression_profile(facts.deco_mode, depth, minutes)
        if facts.dive.session.events.get("LB") is None:
            return None
        return build_basic_decompression_profile_for_session(
            facts.deco_mode,
            depth,
            facts.dive.session,
        )
