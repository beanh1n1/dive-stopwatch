from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ChamberTable(Enum):
    TT5 = auto()
    TT6 = auto()
    TT6A = auto()


class ChamberGas(Enum):
    AIR = auto()
    O2 = auto()
    TREATMENT_GAS = auto()
    TRAVEL = auto()


@dataclass(frozen=True)
class ChamberSegment:
    label: str
    depth_fsw: int
    duration_sec: float
    gas: ChamberGas
    extension_zone: str | None = None


def build_tt5_plan(*, extension_count_30: int = 0) -> tuple[ChamberSegment, ...]:
    plan = [
        ChamberSegment("TT5_60_O2_1", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT5_60_AIR_1", 60, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT5_60_O2_2", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("ASCENT_60_TO_30", 30, 30 * 60, ChamberGas.TRAVEL),
        ChamberSegment("TT5_30_O2_1", 30, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT5_30_AIR_1", 30, 5 * 60, ChamberGas.AIR),
    ]
    base_label = "TT5_30_O2_2"
    if extension_count_30 == 0:
        plan.append(ChamberSegment(base_label, 30, 20 * 60, ChamberGas.O2, extension_zone="30"))
    else:
        plan.append(ChamberSegment(base_label, 30, 20 * 60, ChamberGas.O2))
    for idx in range(extension_count_30):
        zone = "30" if idx == extension_count_30 - 1 else None
        plan.append(ChamberSegment(f"TT5_30_EXT_O2_{idx + 1}", 30, 20 * 60, ChamberGas.O2, extension_zone=zone))
    plan.append(ChamberSegment("ASCENT_30_TO_SURFACE", 0, 30 * 60, ChamberGas.TRAVEL))
    return tuple(plan)


def build_tt6_plan(*, extension_count_60: int = 0, extension_count_30: int = 0) -> tuple[ChamberSegment, ...]:
    plan = [
        ChamberSegment("TT6_60_O2_1", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT6_60_AIR_1", 60, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT6_60_O2_2", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT6_60_AIR_2", 60, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT6_60_O2_3", 60, 20 * 60, ChamberGas.O2),
    ]
    if extension_count_60 == 0:
        plan.append(ChamberSegment("TT6_60_AIR_3", 60, 5 * 60, ChamberGas.AIR, extension_zone="60"))
    else:
        plan.append(ChamberSegment("TT6_60_AIR_3", 60, 5 * 60, ChamberGas.AIR))
    for idx in range(extension_count_60):
        plan.append(ChamberSegment(f"TT6_60_EXT_O2_{idx + 1}", 60, 20 * 60, ChamberGas.O2))
        zone = "60" if idx == extension_count_60 - 1 else None
        plan.append(ChamberSegment(f"TT6_60_EXT_AIR_{idx + 1}", 60, 5 * 60, ChamberGas.AIR, extension_zone=zone))
    plan.extend(
        [
            ChamberSegment("ASCENT_60_TO_30", 30, 30 * 60, ChamberGas.TRAVEL),
            ChamberSegment("TT6_30_AIR_1", 30, 15 * 60, ChamberGas.AIR),
            ChamberSegment("TT6_30_O2_1", 30, 60 * 60, ChamberGas.O2),
            ChamberSegment("TT6_30_AIR_2", 30, 15 * 60, ChamberGas.AIR),
        ]
    )
    if extension_count_30 == 0:
        plan.append(ChamberSegment("TT6_30_O2_2", 30, 60 * 60, ChamberGas.O2, extension_zone="30"))
    else:
        plan.append(ChamberSegment("TT6_30_O2_2", 30, 60 * 60, ChamberGas.O2))
    for idx in range(extension_count_30):
        plan.append(ChamberSegment(f"TT6_30_EXT_AIR_{idx + 1}", 30, 15 * 60, ChamberGas.AIR))
        zone = "30" if idx == extension_count_30 - 1 else None
        plan.append(ChamberSegment(f"TT6_30_EXT_O2_{idx + 1}", 30, 60 * 60, ChamberGas.O2, extension_zone=zone))
    plan.append(ChamberSegment("ASCENT_30_TO_SURFACE", 0, 30 * 60, ChamberGas.TRAVEL))
    return tuple(plan)


def build_tt6a_plan(
    *,
    relief_depth_fsw: int,
    extension_count_60: int = 0,
    extension_count_30: int = 0,
) -> tuple[ChamberSegment, ...]:
    ascent_to_60_sec = ((relief_depth_fsw - 60) / 3.0) * 60.0
    plan = [
        ChamberSegment("TT6A_RELIEF_GAS_1", relief_depth_fsw, 25 * 60, ChamberGas.TREATMENT_GAS),
        ChamberSegment("TT6A_RELIEF_AIR_1", relief_depth_fsw, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT6A_RELIEF_GAS_2", relief_depth_fsw, 35 * 60, ChamberGas.TREATMENT_GAS),
        ChamberSegment("ASCENT_RELIEF_TO_60", 60, ascent_to_60_sec, ChamberGas.TREATMENT_GAS),
        ChamberSegment("TT6A_60_O2_1", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT6A_60_AIR_1", 60, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT6A_60_O2_2", 60, 20 * 60, ChamberGas.O2),
        ChamberSegment("TT6A_60_AIR_2", 60, 5 * 60, ChamberGas.AIR),
        ChamberSegment("TT6A_60_O2_3", 60, 20 * 60, ChamberGas.O2),
    ]
    if extension_count_60 == 0:
        plan.append(ChamberSegment("TT6A_60_AIR_3", 60, 5 * 60, ChamberGas.AIR, extension_zone="60"))
    else:
        plan.append(ChamberSegment("TT6A_60_AIR_3", 60, 5 * 60, ChamberGas.AIR))
    for idx in range(extension_count_60):
        plan.append(ChamberSegment(f"TT6A_60_EXT_O2_{idx + 1}", 60, 20 * 60, ChamberGas.O2))
        zone = "60" if idx == extension_count_60 - 1 else None
        plan.append(ChamberSegment(f"TT6A_60_EXT_AIR_{idx + 1}", 60, 5 * 60, ChamberGas.AIR, extension_zone=zone))
    plan.extend(
        [
            ChamberSegment("ASCENT_60_TO_30", 30, 30 * 60, ChamberGas.TRAVEL),
            ChamberSegment("TT6A_30_AIR_1", 30, 15 * 60, ChamberGas.AIR),
            ChamberSegment("TT6A_30_O2_1", 30, 60 * 60, ChamberGas.O2),
            ChamberSegment("TT6A_30_AIR_2", 30, 15 * 60, ChamberGas.AIR),
        ]
    )
    if extension_count_30 == 0:
        plan.append(ChamberSegment("TT6A_30_O2_2", 30, 60 * 60, ChamberGas.O2, extension_zone="30"))
    else:
        plan.append(ChamberSegment("TT6A_30_O2_2", 30, 60 * 60, ChamberGas.O2))
    for idx in range(extension_count_30):
        plan.append(ChamberSegment(f"TT6A_30_EXT_AIR_{idx + 1}", 30, 15 * 60, ChamberGas.AIR))
        zone = "30" if idx == extension_count_30 - 1 else None
        plan.append(ChamberSegment(f"TT6A_30_EXT_O2_{idx + 1}", 30, 60 * 60, ChamberGas.O2, extension_zone=zone))
    plan.append(ChamberSegment("ASCENT_30_TO_SURFACE", 0, 30 * 60, ChamberGas.TRAVEL))
    return tuple(plan)
