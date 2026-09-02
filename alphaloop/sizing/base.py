"""The Sizer protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Sizer(Protocol):
    """Converts a raw signal into target weights, pre-risk-clamp.

    Args passed to :meth:`size`:
        signal: for ``timeseries`` specs, a boolean DataFrame of "in
            position" intent (index=ts, columns=symbol), already the
            entry-to-exit span. For ``crosssectional`` specs, a float
            DataFrame of per-symbol scores (NaN where unranked).
        returns: realized per-period returns for the same symbols/index,
            for sizers that need volatility or win/loss stats.
        params: ``spec.sizer.params``, forwarded verbatim.

    Returns:
        A DataFrame of target weights, same index/columns as ``signal``,
        NOT yet clamped by the risk layer.
    """

    name: str

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame: ...


def is_bool_frame(signal: pd.DataFrame) -> bool:
    """True when ``signal`` is the boolean "in position" form (timeseries), not scores."""

    return bool((signal.dtypes.astype(str) == "bool").all())
