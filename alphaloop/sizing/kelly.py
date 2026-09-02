"""Kelly-fraction sizing from a rolling win-rate/payoff estimate, capped.

Uses the simplified Kelly formula ``f* = W - (1-W)/R`` where ``W`` is the
rolling win rate and ``R`` is the average win / average loss ratio,
estimated over ``lookback`` periods of realized returns while a position
was signaled. Always capped at ``cap`` (default 0.25) — full Kelly is
famously too aggressive for the assumption errors real strategies have.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from alphaloop.sizing.base import is_bool_frame


def _rolling_kelly(rets: pd.Series, lookback: int) -> pd.Series:
    def kelly(window: np.ndarray) -> float:
        wins = window[window > 0]
        losses = window[window < 0]
        if len(wins) == 0 or len(losses) == 0:
            return 0.0
        win_rate = len(wins) / len(window)
        payoff = wins.mean() / abs(losses.mean())
        if payoff == 0:
            return 0.0
        return win_rate - (1 - win_rate) / payoff

    return rets.rolling(lookback).apply(kelly, raw=True)


class KellyCappedSizer:
    name = "kelly"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        cap = float(params.get("cap", 0.25))
        lookback = int(params.get("lookback", 60))

        direction: pd.DataFrame
        if is_bool_frame(signal):
            direction = signal.astype(float)
        else:
            direction = signal.fillna(0.0).apply(np.sign)

        weights = pd.DataFrame(index=signal.index, columns=signal.columns, dtype=float)
        for col in signal.columns:
            f = _rolling_kelly(returns[col], lookback).clip(lower=0.0, upper=cap).fillna(0.0)
            weights[col] = direction[col] * f
        return weights
