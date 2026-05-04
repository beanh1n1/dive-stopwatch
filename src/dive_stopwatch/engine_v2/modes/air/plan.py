from __future__ import annotations

import math

from ...domain.air_o2_profiles import DecoMode, DiveProfile, build_profile, next_stop_after


def build_air_plan(*, mode: DecoMode, depth_fsw: int, bottom_elapsed_sec: float) -> DiveProfile:
    bottom_time_min = max(math.ceil(bottom_elapsed_sec / 60), 1)
    return build_profile(mode, depth_fsw, bottom_time_min)


def next_required_stop(profile: DiveProfile, current_stop_index: int | None):
    return next_stop_after(profile, current_stop_index)
