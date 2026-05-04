from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from ...domain.air_o2_profiles import SurfaceProfile, build_surface_profile


class SurdPenaltyKind(Enum):
    NONE = auto()
    PLUS_15_AT_50 = auto()
    EXCEEDED = auto()


@dataclass(frozen=True)
class SurdChamberSegment:
    segment_index: int
    period_number: int
    depth_fsw: int
    duration_sec: int


@dataclass(frozen=True)
class SurdChamberPlan:
    surface_profile: SurfaceProfile | None
    penalty_kind: SurdPenaltyKind
    segments: tuple[SurdChamberSegment, ...]


def build_surd_chamber_plan(*, input_depth_fsw: int, input_bottom_time_min: int, penalty_kind: SurdPenaltyKind) -> SurdChamberPlan:
    surface_profile = build_surface_profile(input_depth_fsw, input_bottom_time_min)
    return build_surd_chamber_plan_from_half_periods(
        chamber_o2_half_periods=surface_profile.chamber_o2_half_periods,
        penalty_kind=penalty_kind,
        surface_profile=surface_profile,
    )


def build_surd_chamber_plan_from_half_periods(
    *,
    chamber_o2_half_periods: int | None,
    penalty_kind: SurdPenaltyKind,
    surface_profile: SurfaceProfile | None = None,
) -> SurdChamberPlan:
    assert penalty_kind is not SurdPenaltyKind.EXCEEDED, (
        "EXCEEDED penalty must be handled by Coordinator handoff, not SURD plan builder"
    )
    base_half_periods = chamber_o2_half_periods or 0
    extra_half_periods = 1 if penalty_kind is SurdPenaltyKind.PLUS_15_AT_50 else 0
    total_half_periods = max(base_half_periods + extra_half_periods, 0)
    remaining_half_periods = total_half_periods
    segments: list[SurdChamberSegment] = []
    segment_index = 0

    first_50_half_periods = min(remaining_half_periods, 1 + extra_half_periods)
    if first_50_half_periods:
        segments.append(
            SurdChamberSegment(
                segment_index=segment_index,
                period_number=1,
                depth_fsw=50,
                duration_sec=first_50_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= first_50_half_periods

    first_40_half_periods = min(remaining_half_periods, 1)
    if first_40_half_periods:
        segments.append(
            SurdChamberSegment(
                segment_index=segment_index,
                period_number=1,
                depth_fsw=40,
                duration_sec=first_40_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= first_40_half_periods

    period_number = 2
    while remaining_half_periods > 0:
        period_half_periods = min(remaining_half_periods, 2)
        depth_fsw = 40 if period_number <= 4 else 30
        segments.append(
            SurdChamberSegment(
                segment_index=segment_index,
                period_number=period_number,
                depth_fsw=depth_fsw,
                duration_sec=period_half_periods * 15 * 60,
            )
        )
        segment_index += 1
        remaining_half_periods -= period_half_periods
        period_number += 1

    return SurdChamberPlan(
        surface_profile=surface_profile,
        penalty_kind=penalty_kind,
        segments=tuple(segments),
    )
