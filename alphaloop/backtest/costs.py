"""Fee, slippage, and funding cost models. On by default (never opt-in)."""

from __future__ import annotations

import pandas as pd

from alphaloop.core.spec import CostModel


def apply_trade_costs(trade_notional: pd.Series, costs: CostModel) -> pd.Series:
    """Fee + slippage cost in quote currency for each trade's notional value.

    ``trade_notional`` should be the absolute dollar value traded (already
    signed away — costs are always a drag, never a credit).
    """

    bps = (costs.fee_bps + costs.slippage_bps) / 10_000
    return trade_notional.abs() * bps


def apply_funding_cost(
    position_notional: pd.Series, funding_rate: pd.Series, costs: CostModel
) -> pd.Series:
    """Per-period funding paid/received on a held perpetual position.

    A positive (long) position pays when ``funding_rate`` is positive, per
    standard perp convention. Returns zero when ``costs.funding`` is off.
    """

    if not costs.funding:
        return pd.Series(0.0, index=position_notional.index)
    aligned_rate = funding_rate.reindex(position_notional.index).fillna(0.0)
    return position_notional * aligned_rate
