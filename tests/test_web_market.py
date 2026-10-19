import time

import pytest

from alphaloop.web.market import PublicMarket


class PublicExchange:
    def __init__(self, now):
        self.now = now
        self.quote_age = 0
        self.gap = False

    def fetch_ohlcv(self, symbol, **kwargs):
        last_open = int(self.now//86400)*86400
        rows = [[(last_open+i*86400)*1000, 100, 101, 99, 100+i, 100] for i in range(-6,1)]
        return rows if not self.gap else [r for i,r in enumerate(rows) if i!=4]

    def fetch_ticker(self, symbol):
        return {"timestamp": int((self.now-self.quote_age)*1000), "last": 100}


def test_market_excludes_unclosed_candles_and_requires_complete_history():
    now = time.time()
    ex = PublicExchange(now)
    market = PublicMarket()
    market.exchanges["binance"] = ex
    snapshot = market.snapshot("binance", ["BTC/USDT", "ETH/USDT"], "1d", 2)
    assert snapshot.frame.index.get_level_values("ts").max().timestamp()+86400 <= now
    assert len(snapshot.frame) == 12
    ex.gap = True
    with pytest.raises(ValueError, match="Gap"):
        market.snapshot("binance", ["BTC/USDT", "ETH/USDT"], "1d", 2)


def test_market_rejects_stale_and_future_quotes():
    ex = PublicExchange(time.time())
    market = PublicMarket()
    market.exchanges["binance"] = ex
    for age in [500, -60]:
        ex.quote_age = age
        with pytest.raises(ValueError, match="stale quote"):
            market.snapshot("binance", ["BTC/USDT", "ETH/USDT"], "1d", 2)
