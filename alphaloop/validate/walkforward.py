"""Walk-forward split generation, embargo, and a bull/bear/chop regime table."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class WalkForwardSplit:
    train: pd.Index
    test: pd.Index


def walk_forward_splits(
    index: pd.Index, n_splits: int = 5, embargo: int = 0
) -> list[WalkForwardSplit]:
    """Expanding-window walk-forward splits with an embargo gap between train/test.

    ``embargo`` is a number of bars purged from the end of each train fold
    (and the start of its test fold is unaffected — the embargo exists so
    a feature with a rolling lookback computed near the train/test boundary
    can't leak into the test fold via autocorrelation).
    """

    n = len(index)
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    fold_size = n // (n_splits + 1)
    if fold_size < 1:
        raise ValueError(f"not enough observations ({n}) for {n_splits} walk-forward splits")

    splits = []
    for i in range(1, n_splits + 1):
        train_end = fold_size * i
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, n)
        if test_start >= test_end:
            continue
        splits.append(WalkForwardSplit(train=index[:train_end], test=index[test_start:test_end]))
    return splits


def sharpe(returns: pd.Series, periods_per_year: float = 365 * 24) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 2 or clean.std(ddof=1) == 0:
        return float("nan")
    return float(clean.mean() / clean.std(ddof=1) * np.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    return float(drawdown.min())


def regime_labels(
    btc_close: pd.Series, trend_window: int = 50, chop_threshold: float = 0.02
) -> pd.Series:
    """Bull/bear/chop labels from a BTC-close trend filter.

    A period is "bull" when price is > trend by more than ``chop_threshold``,
    "bear" when < trend by more than ``chop_threshold``, else "chop".
    """

    trend = btc_close.rolling(trend_window).mean()
    deviation = (btc_close - trend) / trend
    labels = pd.Series("chop", index=btc_close.index)
    labels[deviation > chop_threshold] = "bull"
    labels[deviation < -chop_threshold] = "bear"
    return labels


def regime_table(
    returns: pd.Series, labels: pd.Series, periods_per_year: float = 365 * 24
) -> pd.DataFrame:
    aligned_labels = labels.reindex(returns.index).ffill()
    rows = []
    for regime in ["bull", "bear", "chop"]:
        mask = aligned_labels == regime
        subset = returns[mask]
        equity = (1 + subset).cumprod()
        rows.append(
            {
                "regime": regime,
                "n_periods": int(mask.sum()),
                "sharpe": sharpe(subset, periods_per_year),
                "total_return": float(equity.iloc[-1] - 1) if len(equity) else float("nan"),
                "max_drawdown": max_drawdown(equity) if len(equity) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def turnover_cost_diagnostics(positions: pd.DataFrame, costs_bps: float) -> dict[str, float]:
    """Average per-period turnover and its annualized cost drag, in bps of equity."""

    if "weight" not in positions.columns:
        return {"avg_turnover": float("nan"), "annualized_cost_drag_bps": float("nan")}
    wide = positions.pivot_table(
        index="ts", columns="symbol", values="weight", aggfunc="last"
    ).fillna(0.0)
    turnover = wide.diff().abs().sum(axis=1).fillna(0.0)
    avg_turnover = float(turnover.mean())
    return {
        "avg_turnover": avg_turnover,
        "annualized_cost_drag_bps": avg_turnover * costs_bps * len(wide),
    }
