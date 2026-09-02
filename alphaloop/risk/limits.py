"""Risk limit clamps and the drawdown kill-switch check.

``clamp_weights`` runs on every sizer's output, in both backtest and
live/paper, so a spec cannot bypass risk limits by choosing a permissive
sizer. It is pure/stateless; the drawdown kill-switch
(:func:`drawdown_breach`) is stateful only in that it needs the equity
curve so far, which the caller (backtest loop or live runner) supplies.
"""

from __future__ import annotations

import pandas as pd

from alphaloop.core.spec import RiskLimits


def clamp_weights(weights: pd.DataFrame, risk: RiskLimits) -> pd.DataFrame:
    """Apply per-position, gross, and net exposure limits, in that order."""

    clamped = weights.clip(lower=-risk.max_position_pct, upper=risk.max_position_pct)

    gross = clamped.abs().sum(axis=1)
    gross_scale = (risk.max_gross_exposure / gross).clip(upper=1.0).fillna(1.0)
    clamped = clamped.mul(gross_scale, axis=0)

    net = clamped.sum(axis=1)
    over_net = net.abs() > risk.max_net_exposure
    if over_net.any():
        net_scale = pd.Series(1.0, index=clamped.index)
        net_scale[over_net] = (risk.max_net_exposure / net[over_net].abs()).clip(upper=1.0)
        clamped = clamped.mul(net_scale, axis=0)

    return clamped


def drawdown_breach(equity: pd.Series, risk: RiskLimits) -> pd.Series:
    """Boolean Series: True at each timestamp where peak-to-trough drawdown

    exceeds ``risk.drawdown_halt_pct``. The live runner treats the first
    True as a kill-switch trip (see ``alphaloop.execute.runner``); the
    backtester reports it as a diagnostic in the scorecard.
    """

    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    return drawdown <= -risk.drawdown_halt_pct
