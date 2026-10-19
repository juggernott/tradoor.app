"""Actual private-engine integration. Skip when its source is not configured."""
import numpy as np
import pandas as pd
import pytest

from alphaloop.web.engine import source_root
from alphaloop.web.research import Config, csv_frame

pytestmark = pytest.mark.skipif(not source_root(), reason="Private Alphacore v12 source is not configured")


@pytest.fixture
def v12():
    pytest.importorskip("polars")
    from alphaloop.web.alphacore_v12 import AlphacoreV12
    return AlphacoreV12()


@pytest.fixture
def prices_csv():
    rng = np.random.default_rng(4521)
    values = np.cumprod(1+rng.normal(.0002,.015,(600,2)),axis=0)*100
    return "date,symbol,close\n"+"\n".join(f"{d.date()},{s},{values[i,j]}" for i,d in enumerate(pd.date_range("2024-01-01",periods=600)) for j,s in enumerate(["BTC/USDT","ETH/USDT"]))


def test_actual_v12_backtest_calls_private_kernel_and_matches_shifted_returns(v12, prices_csv, monkeypatch):
    calls = []
    original = v12.validation.backtest_v2
    def observed(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(v12.validation,"backtest_v2",observed)
    config = Config().model_dump()
    result = v12.backtest(prices_csv,config,"private-test","Synthetic integration fixture")
    assert len(calls)==2
    assert all(c["annualisation"]==365 and c["lag_days"]==0 for c in calls)
    prices, weights = v12.weight_history(csv_frame(prices_csv),config)
    held = weights.shift(1,fill_value=0)
    returns = (held*prices.pct_change().fillna(0)).sum(axis=1) - held.diff().fillna(0).abs().sum(axis=1)*.0007
    expected = 100000*(1+returns).cumprod()
    np.testing.assert_allclose([p["equity"] for p in result["curve"]],expected,rtol=1e-12)
    assert result["engine"].startswith("alphacore-v12@")
    assert len(result["source_sha256"])==64
    assert result["evaluation"]["out_of_sample"]["bars"]==180


def test_v12_cannot_see_future_prices(v12,prices_csv):
    frame = csv_frame(prices_csv)
    original = frame.copy()
    dates = frame.index.get_level_values("ts").unique().sort_values()
    frame.loc[frame.index.get_level_values("ts")>dates[300],"price.ohlcv.close"] *= 10
    _, before = v12.weight_history(original,Config().model_dump())
    _, after = v12.weight_history(frame,Config().model_dump())
    pd.testing.assert_frame_equal(before.iloc[:301],after.iloc[:301])


def test_v12_forward_target_equals_backtest_signal_at_same_closed_bar(v12,prices_csv):
    frame=csv_frame(prices_csv)
    config=Config().model_dump()
    _,history=v12.weight_history(frame,config)
    short_frame=frame.groupby(level="symbol").tail(2*config["lookback"]+6)
    assert v12.weights(short_frame,config,"1d")==history.iloc[-1].to_dict()


def test_v12_minimum_history_is_enforced(v12, prices_csv):
    short="\n".join(prices_csv.splitlines()[:801])
    with pytest.raises(ValueError,match="500"):
        v12.backtest(short,Config().model_dump(),"short","fixture")
