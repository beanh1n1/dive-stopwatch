from __future__ import annotations

from enum import Enum, auto


class DivingMode(Enum):
    AIR = auto()
    MIXED_GAS = auto()
    CHAMBER = auto()


class DecoProfile(Enum):
    AIR = auto()
    O2 = auto()
    SURD = auto()
    MIXED_GAS = auto()
    TREATMENT = auto()


VALID_PROFILES: dict[DivingMode, tuple[DecoProfile, ...]] = {
    DivingMode.AIR: (DecoProfile.AIR, DecoProfile.O2, DecoProfile.SURD),
    DivingMode.MIXED_GAS: (DecoProfile.MIXED_GAS, DecoProfile.SURD),
    DivingMode.CHAMBER: (DecoProfile.AIR, DecoProfile.TREATMENT),
}
