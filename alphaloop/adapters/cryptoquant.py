"""CryptoQuant adapter — exchange reserves, stablecoin supply, miner flows.

TODO(verify): CryptoQuant's REST API (``api.cryptoquant.com/v1``) response
shape, series granularity (some series are daily-only, some hourly), and
revision policy for miner-flow attribution are not verifiable from public
docs alone. CryptoQuant's daily aggregate series are widely treated as
point-in-time-safe once the day closes, but that assumption should be
confirmed with a real response before this adapter is trusted in a
backtest.

To finish this adapter: capture one real response per endpoint (key
redacted) and confirm per-series revision policy.
"""

from __future__ import annotations

import os

import pandas as pd

from alphaloop.adapters.base import AdapterConfigError


class CryptoQuantAdapter:
    name = "cryptoquant"
    provides = {"onchain.exchange_reserves", "onchain.stablecoin_supply", "onchain.miner_flows"}
    point_in_time = True

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ALPHALOOP_CRYPTOQUANT_API_KEY")
        if not self.api_key:
            raise AdapterConfigError(
                "cryptoquant adapter requires an API key: set ALPHALOOP_CRYPTOQUANT_API_KEY "
                "or pass api_key= explicitly."
            )

    def fetch(
        self,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "cryptoquant adapter is a verified-skeleton only: response shape is "
            "TODO(verify). See module docstring."
        )
