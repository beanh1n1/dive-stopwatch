"""AIR v2 redesign scaffold.

This package is the endstate-oriented replacement for the current AIR runtime
prototype. It is intentionally separated into state, reducer, queries,
projection, and event modules so legacy UI compatibility does not leak back
into core runtime truth.
"""

from .actions import AirV2Action
from .events import AirV2Event, AirV2EventKind
from .queries import AirV2SemanticView, derive_semantic_view
from .reducer import reduce_action
from .state import (
    AirV2AvailableAction,
    AirV2GasState,
    AirV2Obligation,
    AirV2Phase,
    AirV2Plan,
    AirV2State,
    AirV2Timer,
    AirV2TimerKind,
    make_initial_state,
)

__all__ = [
    "AirV2Action",
    "AirV2AvailableAction",
    "AirV2Event",
    "AirV2EventKind",
    "AirV2GasState",
    "AirV2Obligation",
    "AirV2Phase",
    "AirV2Plan",
    "AirV2SemanticView",
    "AirV2State",
    "AirV2Timer",
    "AirV2TimerKind",
    "derive_semantic_view",
    "make_initial_state",
    "reduce_action",
]
