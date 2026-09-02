"""Cross-sectional backtest: rank the universe, long top / short bottom, rebalance.

Implemented directly in pandas rather than through vectorbt's signal API —
cross-sectional rank-weighted portfolios with configurable rebalance cadence
and turnover accounting don't map cleanly onto vectorbt's per-symbol
``from_signals``, and a explicit loop here is easier to audit for
correctness (this is exactly the kind of code a validation gate is meant to
be skeptical of).
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd

from alphaloop.backtest.base import BacktestResult
from alphaloop.backtest.costs import apply_funding_cost, apply_trade_costs
from alphaloop.backtest.signals import evaluate_signal
from alphaloop.core.registry import Registry, default_registry
from alphaloop.core.spec import CrossSectionalSignals, StrategySpec
from alphaloop.risk.limits import clamp_weights


def _rebalance_dates(index: pd.Index, rule: str) -> pd.Index:
    """``rule`` is a pandas offset alias, e.g. 'D', 'W', '4H'."""

    marker = pd.Series(1, index=index).resample(rule).first()
    return marker.dropna().index.intersection(index)


def run_crosssectional(
    spec: StrategySpec, data: pd.DataFrame, data_hash: str, registry: Registry = default_registry
) -> BacktestResult:
    assert isinstance(spec.signals, CrossSectionalSignals)
    signals = spec.signals
    symbols = sorted(data.index.get_level_values("symbol").unique())

    scores = {}
    closes = {}
    for symbol in symbols:
        frame = cast(pd.DataFrame, data.xs(symbol, level="symbol"))
        scores[symbol] = evaluate_signal(signals.score, frame)
        close_col = next((c for c in frame.columns if c.endswith("ohlcv.close")), None)
        if close_col is None:
            raise ValueError("crosssectional backtest requires a price.ohlcv.close feature")
        closes[symbol] = frame[close_col]

    score_df = pd.DataFrame(scores).sort_index()
    close_df = pd.DataFrame(closes).sort_index().reindex(score_df.index)
    funding_df = None
    funding_cols = [c for c in data.columns if c.endswith("funding.rate")]
    if funding_cols and spec.costs.funding:
        funding_df = pd.DataFrame(
            {
                s: data.xs(s, level="symbol")[funding_cols[0]]
                for s in symbols
                if funding_cols[0] in data.xs(s, level="symbol").columns
            }
        ).reindex(score_df.index)

    rebal_dates = _rebalance_dates(score_df.index, signals.rebalance)

    # Hold each rebalance date's score constant until the next rebalance —
    # the sizer only ever sees "the score as of the last rebalance", so it
    # can't accidentally react to scores intraperiod.
    held_scores = score_df.loc[score_df.index.isin(rebal_dates)].reindex(score_df.index).ffill()

    returns_df = close_df.pct_change().fillna(0.0)

    sizer_params: dict[str, Any] = dict(spec.sizer.params)
    sizer_params["_signals"] = signals
    sizer = registry.instantiate("alphaloop.sizers", spec.sizer.name)
    raw_weights = sizer.size(held_scores, returns_df, sizer_params)
    weights = clamp_weights(raw_weights.fillna(0.0), spec.risk)

    gross_returns = (weights.shift(1).fillna(0.0) * returns_df).sum(axis=1)

    turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
    trade_notional = turnover  # weights are already fractions of equity==1
    cost_drag = apply_trade_costs(trade_notional, spec.costs)

    funding_drag = pd.Series(0.0, index=score_df.index)
    if funding_df is not None:
        for symbol in symbols:
            if symbol in funding_df.columns:
                funding_drag = funding_drag.add(
                    apply_funding_cost(weights[symbol], funding_df[symbol], spec.costs),
                    fill_value=0.0,
                )

    net_returns = gross_returns - cost_drag - funding_drag
    equity = (1 + net_returns).cumprod()
    exposure = weights.abs().sum(axis=1)

    trades = weights.diff().fillna(weights.iloc[0] if len(weights) else pd.Series(dtype=float))
    trades = trades[(trades != 0).any(axis=1)].stack().reset_index()
    trades.columns = ["ts", "symbol", "weight_change"]

    positions = weights.stack().reset_index()
    positions.columns = ["ts", "symbol", "weight"]

    return BacktestResult(
        equity=equity,
        returns=net_returns,
        positions=positions,
        trades=trades,
        exposure=exposure,
        spec=spec,
        data_hash=data_hash,
    )
