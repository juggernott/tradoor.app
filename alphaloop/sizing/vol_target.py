"""Weight = target_annual_vol / realized_vol, clamped to a max leverage.

Default sizer for ``timeseries`` specs. Realized vol is a rolling
annualized std of returns; positions in low-vol regimes size up (bounded
by ``max_leverage``), high-vol regimes size down.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from alphaloop.sizing.base import is_bool_frame


class VolTargetSizer:
    name = "vol_target"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        target_annual_vol = float(params.get("target_annual_vol", 0.20))
        lookback = int(params.get("lookback", 30))
        periods_per_year = float(params.get("periods_per_year", 365 * 24))
        max_leverage = float(params.get("max_leverage", 3.0))

        realized_vol = returns.rolling(lookback).std() * np.sqrt(periods_per_year)
        realized_vol = realized_vol.replace(0.0, np.nan)
        scale = (target_annual_vol / realized_vol).clip(upper=max_leverage).fillna(0.0)

        direction: pd.DataFrame
        if is_bool_frame(signal):
            direction = signal.astype(float)
        else:
            direction = signal.fillna(0.0).apply(np.sign)
        result = (direction * scale.reindex_like(direction).fillna(0.0)).fillna(0.0)
        return cast(pd.DataFrame, result)
