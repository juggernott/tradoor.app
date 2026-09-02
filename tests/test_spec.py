import pytest
from pydantic import ValidationError

from alphaloop.core.spec import (
    CrossSectionalSignals,
    DataWindow,
    SizerConfig,
    StrategySpec,
    SymbolUniverse,
    TimeseriesSignals,
)


def test_yaml_roundtrip(timeseries_spec):
    text = timeseries_spec.to_yaml()
    restored = StrategySpec.from_yaml(text)
    assert restored == timeseries_spec


def test_kind_signals_mismatch_rejected():
    with pytest.raises(ValidationError, match="kind='timeseries'"):
        StrategySpec(
            name="bad",
            hypothesis="x",
            kind="timeseries",
            universe=SymbolUniverse(symbols=["BTC/USDT"]),
            features=["price.ohlcv:1h"],
            signals=CrossSectionalSignals(score="close", rebalance="D", top_n=1),
            sizer=SizerConfig(name="vol_target"),
            data_window=DataWindow(start="2024-01-01", end="2024-01-02"),
            venue="binance",
        )


def test_crosssectional_requires_top_n_or_pct():
    with pytest.raises(ValidationError):
        CrossSectionalSignals(score="close", rebalance="D")


def test_crosssectional_rejects_both_n_and_pct():
    with pytest.raises(ValidationError):
        CrossSectionalSignals(score="close", rebalance="D", top_n=1, top_pct=0.1)


def test_data_window_start_before_end():
    with pytest.raises(ValidationError):
        DataWindow(start="2024-01-10", end="2024-01-01")


def test_feature_id_pattern_rejects_bad_format():
    with pytest.raises(ValidationError):
        StrategySpec(
            name="bad",
            hypothesis="x",
            kind="timeseries",
            universe=SymbolUniverse(symbols=["BTC/USDT"]),
            features=["not a valid feature id"],
            signals=TimeseriesSignals(entry="close > 0", exit="close < 0"),
            sizer=SizerConfig(name="vol_target"),
            data_window=DataWindow(start="2024-01-01", end="2024-01-02"),
            venue="binance",
        )


def test_content_hash_stable_across_name_change(timeseries_spec):
    renamed = timeseries_spec.model_copy(update={"name": "different-name"})
    assert renamed.content_hash() == timeseries_spec.content_hash()


def test_content_hash_changes_with_signal(timeseries_spec):
    changed = timeseries_spec.model_copy(
        update={
            "signals": TimeseriesSignals(entry="close > close.rolling(50).mean()", exit="close < 0")
        }
    )
    assert changed.content_hash() != timeseries_spec.content_hash()


def test_spec_is_frozen(timeseries_spec):
    with pytest.raises(ValidationError):
        timeseries_spec.name = "mutated"


def test_load_save_roundtrip(tmp_path, timeseries_spec):
    path = tmp_path / "spec.yaml"
    timeseries_spec.save(path)
    restored = StrategySpec.load(path)
    assert restored == timeseries_spec
