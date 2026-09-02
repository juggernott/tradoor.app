"""ccxt-backed OHLCV + funding adapter. Free, no API key, point-in-time.

This is the only adapter guaranteed to work out of the box — every example
spec in ``examples/`` uses it so the demo never depends on a paid data
subscription.
"""

from __future__ import annotations

import time

import ccxt
import pandas as pd

_MS_PER_UNIT = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}


def _freq_to_ms(freq: str) -> int:
    unit = freq[-1]
    if unit not in _MS_PER_UNIT:
        raise ValueError(f"unsupported freq {freq!r}; expected e.g. '1h', '15m', '1d'")
    return int(freq[:-1]) * _MS_PER_UNIT[unit]


class CcxtDataAdapter:
    """Fetches OHLCV and perpetual funding rates via ccxt.

    Args:
        exchange_id: any ccxt exchange id, e.g. ``"binance"``, ``"binanceusdm"``.
        exchange: pre-constructed ccxt exchange instance, for tests (mocks)
            or to reuse an already-authenticated client. Overrides
            ``exchange_id`` when given.
    """

    name = "ccxt"
    provides = {"price.ohlcv", "price.funding"}
    point_in_time = True

    def __init__(self, exchange_id: str = "binance", exchange: ccxt.Exchange | None = None) -> None:
        self.exchange_id = exchange_id
        self._exchange = exchange or getattr(ccxt, exchange_id)({"enableRateLimit": True})

    def fetch(
        self,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
    ) -> pd.DataFrame:
        namespaces = {f.split(":")[0] for f in features}
        unknown = namespaces - self.provides
        if unknown:
            raise ValueError(
                f"{self.name} adapter cannot provide {unknown}; provides {self.provides}"
            )

        frames = []
        if "price.ohlcv" in namespaces:
            frames.append(self._fetch_ohlcv(universe, start, end, freq))
        if "price.funding" in namespaces:
            frames.append(self._fetch_funding(universe, start, end))
        if not frames:
            return pd.DataFrame(index=pd.MultiIndex.from_arrays([[], []], names=["ts", "symbol"]))

        out = frames[0]
        for f in frames[1:]:
            out = out.join(f, how="outer")
        return out.sort_index()

    def _fetch_ohlcv(self, universe: list[str], start: str, end: str, freq: str) -> pd.DataFrame:
        start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
        step_ms = _freq_to_ms(freq)

        rows: list[tuple[pd.Timestamp, str, float, float, float, float, float]] = []
        for symbol in universe:
            cursor = start_ms
            while cursor < end_ms:
                batch = self._exchange.fetch_ohlcv(symbol, timeframe=freq, since=cursor, limit=1000)
                if not batch:
                    break
                for ts_ms, o, h, low, c, v in batch:
                    if ts_ms >= end_ms:
                        break
                    rows.append((pd.Timestamp(ts_ms, unit="ms", tz="UTC"), symbol, o, h, low, c, v))
                last_ts = batch[-1][0]
                if last_ts < cursor:
                    break
                cursor = last_ts + step_ms
                if self._exchange.rateLimit:
                    time.sleep(self._exchange.rateLimit / 1000)

        df = pd.DataFrame(
            rows,
            columns=[
                "ts",
                "symbol",
                "price.ohlcv.open",
                "price.ohlcv.high",
                "price.ohlcv.low",
                "price.ohlcv.close",
                "price.ohlcv.volume",
            ],
        )
        return df.set_index(["ts", "symbol"])

    def _fetch_funding(self, universe: list[str], start: str, end: str) -> pd.DataFrame:
        start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)

        rows: list[tuple[pd.Timestamp, str, float]] = []
        for symbol in universe:
            if not self._exchange.has.get("fetchFundingRateHistory"):
                continue
            history = self._exchange.fetchFundingRateHistory(symbol, since=start_ms, limit=1000)
            for entry in history:
                ts_ms = entry["timestamp"]
                if ts_ms is None or not (start_ms <= ts_ms < end_ms):
                    continue
                rows.append(
                    (pd.Timestamp(ts_ms, unit="ms", tz="UTC"), symbol, float(entry["fundingRate"]))
                )
        df = pd.DataFrame(rows, columns=["ts", "symbol", "price.funding.rate"])
        return df.set_index(["ts", "symbol"])
