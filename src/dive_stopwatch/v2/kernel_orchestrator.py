from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .decision_resolver import DecisionResolver
from .facts import FactsBuilder
from .profile_resolver import ProfileResolver
from .runtime_context import RuntimeContextBuilder
from .snapshot_composer import SnapshotComposer
from .presenter import build_snapshot
from .models import SnapshotV2


class _KernelOps(Protocol):
    def _active_profile(self, now: datetime, *, facts=None): ...


class KernelOrchestrator:
    def __init__(
        self,
        *,
        facts_builder: FactsBuilder,
        profile_resolver: ProfileResolver,
        runtime_context_builder: RuntimeContextBuilder,
        decision_resolver: DecisionResolver,
        snapshot_composer: SnapshotComposer,
    ) -> None:
        self._facts_builder = facts_builder
        self._profile_resolver = profile_resolver
        self._runtime_context_builder = runtime_context_builder
        self._decision_resolver = decision_resolver
        self._snapshot_composer = snapshot_composer

    def invalidate(self) -> None:
        self._profile_resolver.invalidate()
        self._decision_resolver.invalidate()

    def build_snapshot(self, engine: _KernelOps, *, state, now: datetime) -> SnapshotV2:
        # 1) Build a stable "facts" object from mutable runtime state.
        facts = self._facts_builder.build(state, now=now)
        # 2) Resolve decompression profile (cached when inputs are unchanged).
        profile = engine._active_profile(now, facts=facts)
        # 3) Derive runtime decision flags from current profile + state.
        context = self._runtime_context_builder.build(
            engine,
            now=now,
            facts=facts,
            profile=profile,
        )
        # 4) Resolve procedural decision (status, labels, enabled buttons).
        decision = self._decision_resolver.resolve(
            state=state,
            now=context.now,
            profile=context.profile,
            at_o2_stop=context.decision_inputs.at_o2_stop,
            active_air_break=context.decision_inputs.active_air_break,
            active_air_break_elapsed_seconds=context.decision_inputs.active_air_break_elapsed_seconds,
            can_start_air_break=context.decision_inputs.can_start_air_break,
            awaiting_first_o2_confirmation=context.decision_inputs.awaiting_first_o2_confirmation,
            active_o2_display_mode=context.decision_inputs.active_o2_display_mode,
            air_break_due_in_seconds=context.decision_inputs.air_break_due_in_seconds,
            show_tsv=context.decision_inputs.show_tsv,
            start_reaches_surface=context.decision_inputs.start_reaches_surface,
        )
        # 5) Build display fields (timers, depth text, detail line).
        fields = self._snapshot_composer.compose(
            engine,
            state=state,
            now=context.now,
            profile=context.profile,
        )
        # 6) Assemble immutable snapshot consumed by GUI.
        return build_snapshot(
            state=state,
            now=context.now,
            status=decision.status,
            timer_kind=decision.timer_kind,
            primary_text=fields.primary_text,
            depth_text=fields.depth_text,
            remaining_text=fields.remaining_text,
            summary_text=decision.summary_text,
            summary_targets_oxygen_stop=decision.summary_targets_oxygen_stop,
            detail_text=fields.detail_text,
            start_label=decision.start_label,
            secondary_label=decision.secondary_label,
            start_enabled=decision.start_enabled,
            secondary_enabled=decision.secondary_enabled,
        )
