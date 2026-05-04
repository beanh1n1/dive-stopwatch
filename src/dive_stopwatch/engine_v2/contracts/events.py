from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class AuditEventKind(Enum):
    MODE_LAUNCHED = auto()
    INPUT_UPDATED = auto()
    ACTION_DISPATCHED = auto()
    TEST_TIME_ADVANCED = auto()
    TEST_TIME_RESET = auto()
    CHAMBER_COMPLETE_RELIEF_AT_60 = auto()
    CHAMBER_NO_COMPLETE_RELIEF_AT_60 = auto()
    CHAMBER_WORSENING_AT_60 = auto()
    LEFT_SURFACE = auto()
    HOLD_STARTED = auto()
    HOLD_ENDED = auto()
    REACHED_BOTTOM = auto()
    LEFT_BOTTOM = auto()
    REACHED_STOP = auto()
    LEFT_STOP = auto()
    REACHED_SURFACE = auto()
    GAS_INTERRUPTED = auto()
    DELAY_STARTED = auto()
    DELAY_RESOLVED = auto()
    HANDOFF_CREATED = auto()
    INVALID_ACTION = auto()


@dataclass(frozen=True)
class AuditEvent:
    kind: AuditEventKind
    at: datetime
    payload: dict[str, object] = field(default_factory=dict)


def invalid_action_event(now: datetime, action_name: str) -> AuditEvent:
    return AuditEvent(kind=AuditEventKind.INVALID_ACTION, at=now, payload={"action": action_name})
