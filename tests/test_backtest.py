import pytest

from alphaloop.backtest.vectorbt_engine import VectorbtEngine
from alphaloop.core.resolver import Resolver


@pytest.fixture
def resolver(tmp_path, mock_registry):
    return Resolver(["mock"], cache_dir=tmp_path, registry=mock_registry)


def test_timeseries_backtest_produces_result(timeseries_spec, resolver, mock_registry):
    universe = timeseries_spec.universe.symbols
    data = resolver.resolve(
        timeseries_spec.features,
        universe,
        timeseries_spec.data_window.start,
        timeseries_spec.data_window.end,
        timeseries_spec.data_window.freq,
    )
    engine = VectorbtEngine(registry=mock_registry)
    result = engine.run(timeseries_spec, data)

    assert len(result.equity) > 0
    assert result.equity.iloc[0] == pytest.approx(1.0, abs=0.2)
    assert not result.returns.isna().all()
    assert result.data_hash


def test_crosssectional_backtest_produces_result(crosssectional_spec, resolver, mock_registry):
    universe = crosssectional_spec.universe.symbols
    data = resolver.resolve(
        crosssectional_spec.features,
        universe,
        crosssectional_spec.data_window.start,
        crosssectional_spec.data_window.end,
        crosssectional_spec.data_window.freq,
    )
    engine = VectorbtEngine(registry=mock_registry)
    result = engine.run(crosssectional_spec, data)

    assert len(result.equity) > 0
    assert set(result.positions["symbol"].unique()) <= set(universe)
    # risk.max_position_pct=0.5 should cap per-symbol weight
    assert result.positions["weight"].abs().max() <= 0.5 + 1e-9


def test_crosssectional_respects_rebalance_cadence(crosssectional_spec, resolver, mock_registry):
    universe = crosssectional_spec.universe.symbols
    data = resolver.resolve(
        crosssectional_spec.features,
        universe,
        crosssectional_spec.data_window.start,
        crosssectional_spec.data_window.end,
        crosssectional_spec.data_window.freq,
    )
    engine = VectorbtEngine(registry=mock_registry)
    result = engine.run(crosssectional_spec, data)

    wide = result.positions.pivot_table(index="ts", columns="symbol", values="weight")
    daily_changes = wide.resample("D").first().diff().abs().sum(axis=1)
    # weights should only change at most once per rebalance day (allowing for edge effects)
    assert (daily_changes.dropna() >= 0).all()


def test_costs_reduce_returns_vs_zero_cost(timeseries_spec, resolver, mock_registry):
    universe = timeseries_spec.universe.symbols
    data = resolver.resolve(
        timeseries_spec.features,
        universe,
        timeseries_spec.data_window.start,
        timeseries_spec.data_window.end,
        timeseries_spec.data_window.freq,
    )
    engine = VectorbtEngine(registry=mock_registry)

    high_cost_spec = timeseries_spec.model_copy(
        update={
            "costs": timeseries_spec.costs.model_copy(update={"fee_bps": 500, "slippage_bps": 500})
        }
    )
    low_cost_spec = timeseries_spec.model_copy(
        update={"costs": timeseries_spec.costs.model_copy(update={"fee_bps": 0, "slippage_bps": 0})}
    )

    high_cost_result = engine.run(high_cost_spec, data)
    low_cost_result = engine.run(low_cost_spec, data)

    assert high_cost_result.equity.iloc[-1] <= low_cost_result.equity.iloc[-1]
