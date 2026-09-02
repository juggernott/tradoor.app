"""Elfa AI adapter — social mentions, sentiment, trending, smart-mentions.

TODO(verify): Elfa's public docs (as of this writing) describe a
``/v2/data/social-mentions`` style REST surface authenticated by an
``x-elfa-api-key`` header, but the exact response envelope (pagination
shape, field names for sentiment score, whether historical endpoints
return point-in-time-safe data or a rolling live snapshot) is not something
this codebase can verify without a sample response. Do not guess it.

Historical/backfill endpoints are treated as point-in-time; the live
"trending now" endpoint is not (it reflects current, not historical, state)
and should be wired to :mod:`alphaloop.events` if ever exposed live rather
than exposed as a backtestable feature.

To finish this adapter: capture one real response per endpoint (with the
key redacted) and hand it to whoever picks up this TODO.
"""

from __future__ import annotations

import os

import pandas as pd

from alphaloop.adapters.base import AdapterConfigError


class ElfaAdapter:
    name = "elfa"
    provides = {"social.mentions", "social.sentiment", "social.trending", "social.smart_mentions"}
    # Historical endpoints only. See module docstring re: "social.trending".
    point_in_time = True

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ALPHALOOP_ELFA_API_KEY")
        if not self.api_key:
            raise AdapterConfigError(
                "elfa adapter requires an API key: set ALPHALOOP_ELFA_API_KEY "
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
            "elfa adapter is a verified-skeleton only: response shape is TODO(verify). "
            "See alphaloop/adapters/elfa.py module docstring."
        )
