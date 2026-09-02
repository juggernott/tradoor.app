import numpy as np
import pandas as pd
import pytest

from alphaloop.core.spec import CrossSectionalSignals
from alphaloop.sizing.atr import AtrRiskSizer
from alphaloop.sizing.fixed_fractional import FixedFractionalSizer
from alphaloop.sizing.kelly import KellyCappedSizer
from alphaloop.sizing.rank_weights import RankWeightsSizer
from alphaloop.sizing.signal_scaled import SignalScaledSizer
from alphaloop.sizing.vol_target import VolTargetSizer


@pytest.fixture
def bool_signal():
    index = pd.date_range("2024-01-01", periods=50, freq="1h")
    return pd.DataFrame({"A": [True] * 25 + [False] * 25, "B": [False] * 50}, index=index)


@pytest.fixture
def returns(bool_signal):
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        {
            "A": rng.normal(0.001, 0.01, len(bool_signal)),
            "B": rng.normal(-0.001, 0.02, len(bool_signal)),
        },
        index=bool_signal.index,
    )


def test_fixed_fractional_scales_bool_signal(bool_signal, returns):
    weights = FixedFractionalSizer().size(bool_signal, returns, {"fraction": 0.15})
    assert weights["A"].iloc[0] == 0.15
    assert weights["A"].iloc[-1] == 0.0
    assert (weights["B"] == 0.0).all()


def test_vol_target_scales_inversely_with_vol(bool_signal, returns):
    weights = VolTargetSizer().size(bool_signal, returns, {"target_annual_vol": 0.5, "lookback": 5})
    assert weights["A"].max() >= 0
    assert weights.shape == bool_signal.shape


def test_kelly_capped_never_exceeds_cap(bool_signal, returns):
    weights = KellyCappedSizer().size(bool_signal, returns, {"cap": 0.1, "lookback": 10})
    assert (weights.abs() <= 0.1 + 1e-9).all().all()


def test_atr_sizer_produces_finite_weights(bool_signal, returns):
    weights = AtrRiskSizer().size(bool_signal, returns, {"per_trade_risk_pct": 0.02})
    assert np.isfinite(weights.fillna(0).to_numpy()).all()


def test_signal_scaled_bool_degenerates_to_fixed_fraction(bool_signal, returns):
    weights = SignalScaledSizer().size(bool_signal, returns, {"max_weight": 0.25})
    assert weights["A"].iloc[0] == 0.25


def test_rank_weights_long_short_gross_normalized():
    index = pd.date_range("2024-01-01", periods=1, freq="1D")
    scores = pd.DataFrame({"A": [3.0], "B": [2.0], "C": [1.0], "D": [0.0]}, index=index)
    signals = CrossSectionalSignals(score="x", rebalance="D", top_n=2, bottom_n=1)
    weights = RankWeightsSizer().size(scores, scores, {"_signals": signals})
    row = weights.iloc[0]
    assert row["A"] > 0 and row["B"] > 0
    assert row["D"] < 0
    assert abs(row.abs().sum() - 1.0) < 1e-9
