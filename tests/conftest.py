from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaloop.core.registry import Registry
from alphaloop.core.spec import (
    CostModel,
    CrossSectionalSignals,
    DataWindow,
    RiskLimits,
    SizerConfig,
    StrategySpec,
    SymbolUniverse,
    TimeseriesSignals,
)


def _synthetic_ohlcv(
    symbols: list[str], periods: int = 400, freq: str = "1h", seed: int = 0
) -> pd.DataFrame:
    """A deterministic, mildly-trending random walk per symbol for tests."""

    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=periods, freq=freq, tz="UTC")
    frames = []
    for i, symbol in enumerate(symbols):
        drift = 0.0002 * (1 if i % 2 == 0 else -1)
        rets = rng.normal(loc=drift, scale=0.01, size=periods)
        close = 100 * np.cumprod(1 + rets)
        high = close * (1 + rng.uniform(0, 0.005, periods))
        low = close * (1 - rng.uniform(0, 0.005, periods))
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        volume = rng.uniform(100, 1000, periods)
        df = pd.DataFrame(
            {
                "price.ohlcv.open": open_,
                "price.ohlcv.high": high,
                "price.ohlcv.low": low,
                "price.ohlcv.close": close,
                "price.ohlcv.volume": volume,
            },
            index=index,
        )
        df.index.name = "ts"
        df["symbol"] = symbol
        frames.append(df.set_index("symbol", append=True))
    return pd.concat(frames).sort_index()


class MockAdapter:
    name = "mock"
    provides = {"price.ohlcv"}
    point_in_time = True

    def __init__(self, data: pd.DataFrame | None = None):
        self._data = data

    def fetch(self, features, universe, start, end, freq):  # noqa: ANN001
        data = self._data if self._data is not None else _synthetic_ohlcv(universe, freq=freq)
        mask = data.index.get_level_values("symbol").isin(universe)
        ts = data.index.get_level_values("ts")
        mask &= (ts >= pd.Timestamp(start, tz="UTC")) & (ts < pd.Timestamp(end, tz="UTC"))
        return data[mask]


class NonPitAdapter:
    name = "nonpit"
    provides = {"onchain.smart_money_netflow"}
    point_in_time = False

    def fetch(self, features, universe, start, end, freq):  # noqa: ANN001
        raise AssertionError("should never be called in a backtest-mode test")


@pytest.fixture
def synthetic_ohlcv():
    return _synthetic_ohlcv


@pytest.fixture
def mock_registry():
    registry = Registry()
    registry.register("alphaloop.adapters", "mock", MockAdapter)
    registry.register("alphaloop.adapters", "nonpit", NonPitAdapter)
    from alphaloop.backtest.vectorbt_engine import VectorbtEngine
    from alphaloop.sizing.atr import AtrRiskSizer
    from alphaloop.sizing.fixed_fractional import FixedFractionalSizer
    from alphaloop.sizing.kelly import KellyCappedSizer
    from alphaloop.sizing.rank_weights import RankWeightsSizer
    from alphaloop.sizing.signal_scaled import SignalScaledSizer
    from alphaloop.sizing.vol_target import VolTargetSizer
    from alphaloop.validate.grades import RequiredChecksValidator

    registry.register("alphaloop.engines", "vectorbt", VectorbtEngine)
    for cls in (
        FixedFractionalSizer,
        VolTargetSizer,
        KellyCappedSizer,
        AtrRiskSizer,
        SignalScaledSizer,
        RankWeightsSizer,
    ):
        registry.register("alphaloop.sizers", cls.name, cls)
    registry.register("alphaloop.validators", "required_checks", RequiredChecksValidator)
    return registry


@pytest.fixture
def timeseries_spec() -> StrategySpec:
    return StrategySpec(
        name="test-momentum",
        hypothesis="Price above its rolling mean predicts continuation.",
        kind="timeseries",
        universe=SymbolUniverse(symbols=["BTC/USDT", "ETH/USDT"]),
        features=["price.ohlcv:1h"],
        signals=TimeseriesSignals(
            entry="close > close.rolling(20).mean()",
            exit="close < close.rolling(20).mean()",
        ),
        sizer=SizerConfig(name="vol_target", params={"target_annual_vol": 0.3, "lookback": 10}),
        risk=RiskLimits(),
        costs=CostModel(),
        data_window=DataWindow(start="2024-01-01", end="2024-01-17", freq="1h"),
        venue="binance",
    )


@pytest.fixture
def crosssectional_spec() -> StrategySpec:
    return StrategySpec(
        name="test-xsect-momentum",
        hypothesis="Recent winners keep winning across the universe.",
        kind="crosssectional",
        universe=SymbolUniverse(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]),
        features=["price.ohlcv:1h"],
        signals=CrossSectionalSignals(
            score="close.pct_change(24)", rebalance="D", top_n=2, bottom_n=1
        ),
        sizer=SizerConfig(name="rank_weights", params={}),
        risk=RiskLimits(max_position_pct=0.5),
        costs=CostModel(),
        data_window=DataWindow(start="2024-01-01", end="2024-01-17", freq="1h"),
        venue="binance",
    )
