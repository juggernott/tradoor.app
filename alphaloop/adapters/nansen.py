"""Nansen adapter — smart-money netflow, holder profile, exchange flows.

TODO(verify): Nansen's Query/Smart Money APIs require a paid API key and
their response schema (per-chain vs per-token addressing, netflow window
granularity, whether "smart money" labels are recomputed retroactively —
which would make this data NON-point-in-time even for "historical" pulls)
cannot be verified from public docs alone. That last point matters: if
labels are retroactively revised, this adapter must report
``point_in_time = False`` regardless of endpoint, or the backtester will
silently admit look-ahead bias. Confirm with Nansen support or a sample
response before flipping this flag or implementing ``fetch``.

To finish this adapter: capture one real response per endpoint (key
redacted) and confirm the label-revision behavior above.
"""

from __future__ import annotations

import os

import pandas as pd

from alphaloop.adapters.base import AdapterConfigError


class NansenAdapter:
    name = "nansen"
    provides = {"onchain.smart_money_netflow", "onchain.holder_profile", "onchain.exchange_flows"}
    # Conservative default until label-revision behavior is confirmed (see
    # module docstring) — a wrong True here is a silent look-ahead-bias bug.
    point_in_time = False

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ALPHALOOP_NANSEN_API_KEY")
        if not self.api_key:
            raise AdapterConfigError(
                "nansen adapter requires an API key: set ALPHALOOP_NANSEN_API_KEY "
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
            "nansen adapter is a verified-skeleton only: response shape and "
            "point-in-time behavior are TODO(verify). See module docstring."
        )
