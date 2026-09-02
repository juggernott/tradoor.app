import pytest

from alphaloop.core.resolver import NonPointInTimeError, Resolver, ResolverError


def test_resolves_and_caches(tmp_path, mock_registry):
    resolver = Resolver(["mock"], cache_dir=tmp_path, registry=mock_registry)
    df = resolver.resolve(["price.ohlcv:1h"], ["BTC/USDT"], "2024-01-01", "2024-01-05", "1h")
    assert not df.empty
    assert "price.ohlcv.close" in df.columns

    cache_files = list((tmp_path / "mock").glob("*.parquet"))
    assert len(cache_files) == 1

    # second call should hit cache, not raise even though MockAdapter would
    # otherwise regenerate different random data for a different call count
    df2 = resolver.resolve(["price.ohlcv:1h"], ["BTC/USDT"], "2024-01-01", "2024-01-05", "1h")
    assert df.equals(df2)


def test_missing_adapter_raises_actionable_error(tmp_path, mock_registry):
    resolver = Resolver(["mock"], cache_dir=tmp_path, registry=mock_registry)
    with pytest.raises(ResolverError, match="no configured adapter provides"):
        resolver.resolve(["onchain.mvrv:1d"], ["BTC/USDT"], "2024-01-01", "2024-01-05", "1h")


def test_non_pit_refused_in_backtest_mode(tmp_path, mock_registry):
    resolver = Resolver(["nonpit"], cache_dir=tmp_path, registry=mock_registry)
    with pytest.raises(NonPointInTimeError):
        resolver.resolve(
            ["onchain.smart_money_netflow:1h"],
            ["BTC/USDT"],
            "2024-01-01",
            "2024-01-05",
            "1h",
            mode="backtest",
        )


def test_non_pit_allowed_in_live_mode(tmp_path, mock_registry):
    resolver = Resolver(["nonpit"], cache_dir=tmp_path, registry=mock_registry)
    with pytest.raises(AssertionError):
        # NonPitAdapter.fetch itself asserts it's never called in this test
        # suite's backtest-only fixtures — this confirms the resolver at
        # least *tries* to call it in live mode instead of refusing.
        resolver.resolve(
            ["onchain.smart_money_netflow:1h"],
            ["BTC/USDT"],
            "2024-01-01",
            "2024-01-05",
            "1h",
            mode="live",
        )
