from __future__ import annotations


def linear_depth_fsw(
    *,
    start_depth_fsw: int,
    end_depth_fsw: int,
    elapsed_sec: float,
    rate_fsw_per_sec: float,
) -> int:
    if rate_fsw_per_sec <= 0:
        return start_depth_fsw
    distance = max(elapsed_sec, 0.0) * rate_fsw_per_sec
    if start_depth_fsw <= end_depth_fsw:
        return min(int(round(start_depth_fsw + distance)), end_depth_fsw)
    return max(int(start_depth_fsw - distance), end_depth_fsw)


def depth_label(depth_fsw: int | None) -> str | None:
    if depth_fsw is None:
        return None
    if depth_fsw <= 0:
        return "Surface"
    return f"{depth_fsw} fsw"
