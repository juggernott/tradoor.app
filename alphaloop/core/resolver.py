"""Feature resolution: spec.features -> configured adapters -> cached DataFrame.

The resolver is the single point where point-in-time integrity is
enforced (principle #3 in the project brief): in ``mode="backtest"`` it
refuses to fetch from any adapter with ``point_in_time = False``, with an
error naming the offending adapter and feature.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from alphaloop.adapters.base import DataAdapter
from alphaloop.core.registry import Registry, default_registry

Mode = Literal["backtest", "live"]

# Per-adapter cache TTL, in seconds. Adapters not listed use DEFAULT_TTL.
# ccxt OHLCV for closed candles never changes, so it's cached "forever"
# within a run; on-chain daily aggregates are refreshed daily by default.
_DEFAULT_TTL = 24 * 3600
_ADAPTER_TTL = {"ccxt": 30 * 24 * 3600}


@dataclass
class FeatureBinding:
    feature: str
    adapter_name: str


class ResolverError(RuntimeError):
    """Raised when a feature can't be bound to any configured adapter."""


class NonPointInTimeError(ResolverError):
    """Raised in backtest mode when a bound adapter is not point-in-time."""


class Resolver:
    """Binds spec features to adapters, with a parquet-on-disk cache.

    Args:
        adapter_names: adapter plugin names to consider, in priority order
            (config priority — see project brief principle... first match
            wins on ambiguity). Typically comes from user config, e.g.
            ``["ccxt", "glassnode"]``.
        cache_dir: root directory for the parquet cache. One file per
            ``(adapter, feature_namespace, universe_hash, start, end,
            freq)`` cache key.
        registry: plugin registry to resolve adapter names against.
    """

    def __init__(
        self,
        adapter_names: list[str],
        cache_dir: str | Path = "cache",
        registry: Registry = default_registry,
        adapter_kwargs: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self._registry = registry
        self._adapter_kwargs = adapter_kwargs or {}
        self._adapters: list[DataAdapter] = [
            registry.instantiate("alphaloop.adapters", name, **self._adapter_kwargs.get(name, {}))
            for name in adapter_names
        ]

    def _bind(self, feature: str) -> DataAdapter:
        namespace = feature.split(":")[0]
        for adapter in self._adapters:
            if namespace in adapter.provides:
                return adapter
        configured = [a.name for a in self._adapters]
        raise ResolverError(
            f"no configured adapter provides feature {feature!r} "
            f"(configured adapters: {configured or '(none)'}). "
            f"Run `alphaloop adapters` to see what's installed, and add the "
            f"one that provides this feature to your resolver config."
        )

    def resolve(
        self,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
        mode: Mode = "backtest",
    ) -> pd.DataFrame:
        by_adapter: dict[str, list[str]] = {}
        for feature in features:
            adapter = self._bind(feature)
            if mode == "backtest" and not adapter.point_in_time:
                raise NonPointInTimeError(
                    f"feature {feature!r} resolves to adapter {adapter.name!r}, which is "
                    f"NOT point-in-time (point_in_time=False). The backtester refuses "
                    f"non-PIT data to avoid look-ahead bias. This adapter may be used in "
                    f"paper/live mode (mode='live')."
                )
            by_adapter.setdefault(adapter.name, []).append(feature)

        frames = []
        for adapter in self._adapters:
            feats = by_adapter.get(adapter.name)
            if not feats:
                continue
            frames.append(self._fetch_cached(adapter, feats, universe, start, end, freq))

        if not frames:
            return pd.DataFrame(index=pd.MultiIndex.from_arrays([[], []], names=["ts", "symbol"]))
        out = frames[0]
        for f in frames[1:]:
            out = out.join(f, how="outer")
        return out.sort_index()

    def _cache_key(
        self,
        adapter_name: str,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
    ) -> Path:
        payload = json.dumps(
            {
                "adapter": adapter_name,
                "features": sorted(features),
                "universe": sorted(universe),
                "start": start,
                "end": end,
                "freq": freq,
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:24]
        return self.cache_dir / adapter_name / f"{digest}.parquet"

    def _fetch_cached(
        self,
        adapter: DataAdapter,
        features: list[str],
        universe: list[str],
        start: str,
        end: str,
        freq: str,
    ) -> pd.DataFrame:
        path = self._cache_key(adapter.name, features, universe, start, end, freq)
        ttl = _ADAPTER_TTL.get(adapter.name, _DEFAULT_TTL)
        if path.exists():
            import time

            age = time.time() - path.stat().st_mtime
            if age < ttl:
                return pd.read_parquet(path)

        df = adapter.fetch(features, universe, start, end, freq)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return df
