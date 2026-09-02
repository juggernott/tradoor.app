"""Risk-per-trade sizing: weight = per_trade_risk_pct / stop_distance_pct.

Uses rolling return std over ``atr_lookback`` periods as an ATR-equivalent
volatility proxy for the stop distance (a true ATR needs high/low/close;
this uses close-to-close std, which is a documented simplification — pass
real ATR via a feature and a custom sizer if you need the exact indicator).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from alphaloop.sizing.base import is_bool_frame


class AtrRiskSizer:
    name = "atr"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        per_trade_risk_pct = float(params.get("per_trade_risk_pct", 0.02))
        stop_multiple = float(params.get("stop_multiple", 2.0))
        atr_lookback = int(params.get("atr_lookback", 14))
        max_leverage = float(params.get("max_leverage", 3.0))

        stop_distance = returns.rolling(atr_lookback).std() * stop_multiple
        stop_distance = stop_distance.replace(0.0, np.nan)
        scale = (per_trade_risk_pct / stop_distance).clip(upper=max_leverage).fillna(0.0)

        direction: pd.DataFrame
        if is_bool_frame(signal):
            direction = signal.astype(float)
        else:
            direction = signal.fillna(0.0).apply(np.sign)
        return (direction * scale.reindex_like(direction).fillna(0.0)).fillna(0.0)
