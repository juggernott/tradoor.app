# Writing a data adapter

A `DataAdapter` (`alphaloop/adapters/base.py`) is three things: a name, a
set of feature namespaces it provides, and a `point_in_time` flag. The
resolver (`alphaloop/core/resolver.py`) binds each of a spec's `features`
to the first configured adapter whose `provides` set contains that
feature's namespace, and the backtester **refuses** to run on any feature
resolved to an adapter with `point_in_time = False`.

## Minimal example (30 lines)

```python
from __future__ import annotations
import pandas as pd


class MyAdapter:
    name = "myapi"
    provides = {"myapi.some_metric"}
    point_in_time = True  # only if true historical values never change

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["ALPHALOOP_MYAPI_API_KEY"]

    def fetch(self, features, universe, start, end, freq) -> pd.DataFrame:
        rows = []
        for symbol in universe:
            for ts, value in my_api_call(symbol, start, end, freq):
                rows.append((ts, symbol, value))
        df = pd.DataFrame(rows, columns=["ts", "symbol", "myapi.some_metric"])
        return df.set_index(["ts", "symbol"])
```

Register it (in your own `pyproject.toml`, not this repo's — see
`docs/private-repo-guide.md`):

```toml
[project.entry-points."alphaloop.adapters"]
myapi = "my_package.adapters:MyAdapter"
```

## The point_in_time flag is load-bearing

Set it to `False` whenever you're not sure a "historical" pull can't be
retroactively revised (label re-classification, restated data, a rolling
"top N" that's recomputed). A wrong `True` is a silent look-ahead-bias bug
that the backtester cannot catch for you — it can only refuse adapters
that admit they're not safe. When in doubt, `False`; the adapter still
works fine for paper/live, where there's no future to look ahead into.

## Verified vs. skeleton adapters in this repo

`ccxt_data.py` and `glassnode.py` are real, tested implementations.
`elfa.py`, `nansen.py`, and `cryptoquant.py` are **verified-skeletons**:
they declare the right protocol shape and raise `NotImplementedError` with
a `TODO(verify)` docstring explaining exactly what's unverified (usually:
the response envelope, or — for Nansen specifically — whether "historical"
labels can be retroactively revised). This repo will never guess an
endpoint's response shape; if you're picking up one of these TODOs,
capture one real (key-redacted) response and use it to write the adapter
for real.

## Caching

The resolver caches every fetch to parquet, keyed by
`(adapter, features, universe, start, end, freq)`, with a per-adapter TTL
in `alphaloop/core/resolver.py` (`_ADAPTER_TTL`) — ccxt OHLCV for closed
candles is cached for 30 days by default since it never changes; other
adapters default to 24h. Add your adapter's name to `_ADAPTER_TTL` if the
default is wrong for its update cadence.
