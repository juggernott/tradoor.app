"""Glassnode adapter — MVRV, SOPR, active addresses.

Unlike the other on-chain adapters, Glassnode's metrics API has a
long-stable, publicly documented shape: ``GET
https://api.glassnode.com/v1/metrics/<category>/<metric>?a=<ASSET>&api_key=...``
returns a JSON array of ``{"t": <unix_seconds>, "v": <float>}`` points, one
per (metric, asset, timestamp). Daily on-chain aggregates are point-in-time
once the day closes, so this adapter is implemented for real rather than
left as a skeleton.

TODO(verify): confirm the exact ``category/metric`` path and any
asset-symbol mapping quirks (Glassnode uses e.g. ``BTC``/``ETH`` short
codes, not exchange trading pairs) for any feature beyond the three wired
below before trusting it in a backtest.
"""

from __future__ import annotations

import os

import pandas as pd
import requests

from alphaloop.adapters.base import AdapterConfigError

_METRIC_PATHS = {
    "onchain.mvrv": "market/mvrv",
    "onchain.sopr": "indicators/sopr",
    "onchain.active_addresses": "addresses/active_count",
}

_BASE_URL = "https://api.glassnode.com/v1/metrics"


def _symbol_to_asset(symbol: str) -> str:
    """'BTC/USDT' -> 'BTC'. Glassnode addresses assets by short code, not pair."""
    return symbol.split("/")[0].upper()


class GlassnodeAdapter:
    name = "glassnode"
    provides = set(_METRIC_PATHS)
    point_in_time = True

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self.api_key = api_key or os.environ.get("ALPHALOOP_GLASSNODE_API_KEY")
        if not self.api_key:
            raise AdapterConfigError(
                "glassnode adapter requires an API key: set ALPHALOOP_GLASSNODE_API_KEY "
                "or pass api_key= explicitly."
            )
        self._session = session or requests.Session()

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

        since = int(pd.Timestamp(start, tz="UTC").timestamp())
        until = int(pd.Timestamp(end, tz="UTC").timestamp())

        frames = []
        for feature in namespaces:
            path = _METRIC_PATHS[feature]
            for symbol in universe:
                asset = _symbol_to_asset(symbol)
                resp = self._session.get(
                    f"{_BASE_URL}/{path}",
                    params={
                        "a": asset,
                        "api_key": self.api_key,
                        "s": since,
                        "u": until,
                        "i": freq,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                points = resp.json()
                if not points:
                    continue
                df = pd.DataFrame(points)
                df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
                df["symbol"] = symbol
                df = df.rename(columns={"v": feature}).set_index(["ts", "symbol"])[[feature]]
                frames.append(df)

        if not frames:
            return pd.DataFrame(index=pd.MultiIndex.from_arrays([[], []], names=["ts", "symbol"]))
        out = frames[0]
        for f in frames[1:]:
            out = out.join(f, how="outer")
        return out.sort_index()
