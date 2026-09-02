"""The EventAdapter protocol and the Event record it returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Event:
    ts: datetime
    entities: list[str]
    headline: str
    sentiment: float | None
    source: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EventAdapter(Protocol):
    """A live/near-live stream of market-relevant events.

    Unlike :class:`alphaloop.adapters.base.DataAdapter`, there is no
    ``fetch(start, end)`` for a historical range — event adapters are
    polled for what's new since the last poll, and are used only in
    paper/live mode (see module docstring).
    """

    name: str
    point_in_time: bool  # almost always False; declared for symmetry with DataAdapter

    def poll(self, watchlist: list[str], since: datetime | None) -> list[Event]:
        """Return events for entities in ``watchlist`` newer than ``since``."""
        ...
