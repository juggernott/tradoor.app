"""The DataAdapter protocol — plugin contract for all feature sources.

Implement this to add a new data source. The backtester REFUSES to run on
features from an adapter with ``point_in_time = False`` (see
``alphaloop.core.resolver``); such adapters may still be used in paper/live
mode, where look-ahead bias cannot occur because there is no future to look
ahead into.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class DataAdapter(Protocol):
    """A source of one or more namespaced features.

    Attributes:
        name: unique adapter id, matches its entry-point name.
        provides: the set of feature-namespace prefixes this adapter can
            fetch (e.g. ``{"price.ohlcv", "price.funding"}``). The resolver
            matches a spec's ``features`` against this set, ignoring the
            optional ``:suffix`` (interval/param) on each feature id.
        point_in_time: if False, the backtester refuses to use this
            adapter's data — see ``alphaloop.core.resolver.Resolver``.
    """

    name: str
    provides: set[str]
    point_in_time: bool

    def fetch(
        self,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
    ) -> pd.DataFrame:
        """Return a DataFrame indexed by ``MultiIndex(ts, symbol)``.

        One column per requested feature. Implementations must raise
        (never silently drop) when a requested feature isn't in
        ``provides``, and must not return data outside ``[start, end)``.
        """
        ...


class AdapterConfigError(RuntimeError):
    """Raised when an adapter is invoked without required configuration.

    Message should name exactly which env var / config key is missing so
    ``alphaloop doctor`` and the resolver's error text stay actionable.
    """
