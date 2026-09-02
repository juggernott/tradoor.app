"""xAI Grok live-search news adapter for a symbol watchlist.

TODO(verify): xAI's Live Search / structured-output response envelope
(exact field names for citations, whether sentiment is returned directly
or must be derived, and rate-limit/pricing behavior for polling on a
schedule) is not verifiable from public docs alone without a live account.
Implement ``poll`` once a sample response is captured.
"""

from __future__ import annotations

import os
from datetime import datetime

from alphaloop.adapters.base import AdapterConfigError
from alphaloop.events.base import Event


class GrokNewsEventAdapter:
    name = "grok_news"
    point_in_time = False

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ALPHALOOP_XAI_API_KEY")
        if not self.api_key:
            raise AdapterConfigError(
                "grok_news adapter requires an API key: set ALPHALOOP_XAI_API_KEY "
                "or pass api_key= explicitly."
            )

    def poll(self, watchlist: list[str], since: datetime | None) -> list[Event]:
        raise NotImplementedError(
            "grok_news adapter is a verified-skeleton only: xAI Live Search "
            "response shape is TODO(verify). See module docstring."
        )
