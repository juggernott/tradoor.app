"""Read-only public market snapshots, with closed-bar and staleness checks."""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

import ccxt
import pandas as pd


FREQUENCIES = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400}
EXCHANGES = {"binance", "kraken"}


@dataclass
class Snapshot:
    frame: pd.DataFrame
    prices: dict[str, float]
    signal_ts: str
    observed_at: float


class PublicMarket:
    def __init__(self):
        self.exchanges = {}

    def daily_history(self, exchange_id, symbols, bars):
        if exchange_id not in EXCHANGES or not 500<=bars<=800:
            raise ValueError("Choose a supported exchange and 500–800 daily bars")
        exchange = getattr(ccxt,exchange_id)({"enableRateLimit":True,"timeout":15000})
        now=time.time()
        rows=[]
        for symbol in symbols:
            candles=exchange.fetch_ohlcv(symbol,timeframe="1d",since=int((now-(bars+4)*86400)*1000),limit=bars+4)
            for ts,_o,_h,_l,close,_v in candles:
                if ts/1000+86400<=now:
                    rows.append((pd.Timestamp(ts,unit="ms",tz="UTC"),symbol,float(close)))
        frame=pd.DataFrame(rows,columns=["ts","symbol","close"]).drop_duplicates(["ts","symbol"])
        panel=frame.pivot(index="ts",columns="symbol",values="close").sort_index().dropna()
        if len(panel)<bars or len(panel.columns)!=len(symbols):
            raise ValueError("Exchange did not return enough common closed daily bars")
        panel=panel.tail(bars)
        if not (panel.index.to_series().diff().dropna()==pd.Timedelta(days=1)).all():
            raise ValueError("Gap in exchange daily history")
        if time.time()-panel.index[-1].timestamp()-86400>86520:
            raise ValueError("Historical feed is not current")
        output=panel.stack().rename("close").reset_index()
        output["date"]=output["ts"].dt.strftime("%Y-%m-%d")
        return output[["date","symbol","close"]].to_csv(index=False)

    def snapshot(self, exchange_id, symbols, frequency, lookback):
        if exchange_id not in EXCHANGES or frequency not in FREQUENCIES:
            raise ValueError("Unsupported public market or frequency")
        if exchange_id not in self.exchanges:
            self.exchanges[exchange_id] = getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 15000})
        exchange = self.exchanges[exchange_id]
        period = FREQUENCIES[frequency]
        now = time.time()
        rows, prices = [], {}
        for symbol in symbols:
            # No account keys are configured; this object only calls public methods.
            candles = exchange.fetch_ohlcv(symbol, timeframe=frequency, since=int((now-(lookback+5)*period)*1000), limit=lookback+5)
            closed = [r for r in candles if r[0]/1000 + period <= now]
            if len(closed) < lookback+1:
                raise ValueError(f"Insufficient closed candles for {symbol}")
            for ts, _o, _h, _l, close, _v in closed:
                if not math.isfinite(float(close)) or close <= 0:
                    raise ValueError("Invalid market close")
                rows.append((pd.Timestamp(ts, unit="ms", tz="UTC"), symbol, float(close)))
            ticker = exchange.fetch_ticker(symbol)
            ts = ticker.get("timestamp")
            if ts is None or now-ts/1000 > 120 or ts/1000-now > 5:
                raise ValueError(f"Missing or stale quote timestamp for {symbol}")
            mark = ticker.get("last") or ticker.get("close")
            if mark is None or not math.isfinite(float(mark)) or mark <= 0:
                raise ValueError("Invalid market mark")
            prices[symbol] = float(mark)
        frame = pd.DataFrame(rows, columns=["ts", "symbol", "price.ohlcv.close"]).drop_duplicates(["ts", "symbol"]).set_index(["ts", "symbol"]).sort_index()
        panel = frame["price.ohlcv.close"].unstack("symbol").dropna()
        if len(panel) < lookback+1 or len(panel.columns) != len(symbols):
            raise ValueError("Incomplete common signal history")
        expected_step = pd.Timedelta(seconds=period)
        if not (panel.index.to_series().diff().dropna().tail(lookback) == expected_step).all():
            raise ValueError("Gap in signal history")
        latest = panel.index[-1]
        age = now-latest.timestamp()-period
        if age < 0 or age > period+120 or time.time()-now > 120:
            raise ValueError("Stale or incomplete market snapshot")
        frame = frame.loc[frame.index.get_level_values("ts").isin(panel.index)]
        return Snapshot(frame, prices, latest.isoformat(), time.time())


class FrozenMarks:
    """Give every simulated order in a tick the same validated prices."""
    def __init__(self, prices):
        self.prices = prices

    def fetch_ticker(self, symbol):
        return {"last": self.prices[symbol]}
