import pandas as pd

from alphaloop.core.spec import RiskLimits
from alphaloop.risk.limits import clamp_weights, drawdown_breach


def test_clamp_position_limit():
    weights = pd.DataFrame({"A": [0.5], "B": [-0.9]})
    risk = RiskLimits(max_position_pct=0.2, max_gross_exposure=10, max_net_exposure=10)
    clamped = clamp_weights(weights, risk)
    assert clamped["A"].iloc[0] == 0.2
    assert clamped["B"].iloc[0] == -0.2


def test_clamp_gross_exposure():
    weights = pd.DataFrame({"A": [0.6], "B": [0.6]})
    risk = RiskLimits(max_position_pct=1.0, max_gross_exposure=0.6, max_net_exposure=10)
    clamped = clamp_weights(weights, risk)
    assert clamped.abs().sum(axis=1).iloc[0] <= 0.6 + 1e-9


def test_clamp_net_exposure():
    weights = pd.DataFrame({"A": [0.8], "B": [0.1]})
    risk = RiskLimits(max_position_pct=1.0, max_gross_exposure=10, max_net_exposure=0.5)
    clamped = clamp_weights(weights, risk)
    assert abs(clamped.sum(axis=1).iloc[0]) <= 0.5 + 1e-9


def test_drawdown_breach_detects_trough():
    equity = pd.Series([1.0, 1.1, 1.2, 0.8, 0.7, 0.9])
    risk = RiskLimits(drawdown_halt_pct=0.3)
    breach = drawdown_breach(equity, risk)
    assert breach.iloc[4]  # (0.7-1.2)/1.2 = -0.4167, breaches 0.3
    assert not breach.iloc[1]


def test_no_position_untouched_by_clamps():
    weights = pd.DataFrame({"A": [0.0]})
    risk = RiskLimits()
    clamped = clamp_weights(weights, risk)
    assert clamped["A"].iloc[0] == 0.0
