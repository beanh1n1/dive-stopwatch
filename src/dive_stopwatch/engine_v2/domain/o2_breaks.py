from __future__ import annotations


def break_due(
    *,
    continuous_elapsed_sec: float,
    remaining_o2_obligation_sec: float | None,
    trigger_sec: float = 30 * 60,
    required_remaining_exceeds_sec: float,
) -> bool:
    if remaining_o2_obligation_sec is None or remaining_o2_obligation_sec <= required_remaining_exceeds_sec:
        return False
    return max(continuous_elapsed_sec, 0.0) >= trigger_sec


def break_due_remaining_sec(
    *,
    continuous_elapsed_sec: float,
    remaining_o2_obligation_sec: float | None,
    trigger_sec: float = 30 * 60,
    required_remaining_exceeds_sec: float,
) -> float | None:
    if remaining_o2_obligation_sec is None or remaining_o2_obligation_sec <= required_remaining_exceeds_sec:
        return None
    return max(trigger_sec - max(continuous_elapsed_sec, 0.0), 0.0)
