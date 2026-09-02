"""Default BacktestEngine: vectorbt for timeseries, pandas for crosssectional.

vectorbt's per-symbol signal vectorization is a good fit for
``kind="timeseries"`` (per-asset entry/exit), but doesn't map cleanly onto
rank-weighted rebalancing across a universe, so ``kind="crosssectional"``
is delegated to :mod:`alphaloop.backtest.crosssectional`, which is
plain pandas.

Requires the ``vectorbt`` extra (``pip install alphaloop[vectorbt]``).
vectorbt currently only imports cleanly with ``plotly==5.18.0`` pinned —
see the comment on the ``vectorbt`` extra in ``pyproject.toml``.
"""

from __future__ import annotations

import hashlib
from typing import cast

import pandas as pd

from alphaloop.backtest.base import BacktestResult
from alphaloop.backtest.costs import apply_funding_cost
from alphaloop.backtest.crosssectional import run_crosssectional
from alphaloop.backtest.signals import evaluate_signal
from alphaloop.core.registry import Registry, default_registry
from alphaloop.core.spec import StrategySpec, TimeseriesSignals
from alphaloop.risk.limits import clamp_weights


def _position_intent(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    """True while "in position": from an entry bar up to (not including) its exit bar."""

    state = pd.DataFrame(False, index=entries.index, columns=entries.columns)
    for col in entries.columns:
        in_pos = False
        col_state = []
        for e, x in zip(entries[col], exits[col], strict=True):
            if not in_pos and bool(e):
                in_pos = True
            elif in_pos and bool(x):
                in_pos = False
            col_state.append(in_pos)
        state[col] = col_state
    return state


def _data_hash(data: pd.DataFrame) -> str:
    hashed = pd.util.hash_pandas_object(data, index=True).to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()[:16]


class VectorbtEngine:
    name = "vectorbt"

    def __init__(self, registry: Registry = default_registry) -> None:
        self._registry = registry

    def run(self, spec: StrategySpec, data: pd.DataFrame) -> BacktestResult:
        data_hash = _data_hash(data)
        if spec.kind == "crosssectional":
            return run_crosssectional(spec, data, data_hash, registry=self._registry)
        return self._run_timeseries(spec, data, data_hash)

    def _run_timeseries(
        self, spec: StrategySpec, data: pd.DataFrame, data_hash: str
    ) -> BacktestResult:
        try:
            import vectorbt as vbt  # imported lazily: heavy optional dependency
        except ImportError as e:
            raise ImportError(
                "timeseries backtests require the 'vectorbt' extra: "
                "pip install 'alphaloop[vectorbt]'. crosssectional specs don't need it — "
                "see docs/adapters.md and README.md for what's optional."
            ) from e

        assert isinstance(spec.signals, TimeseriesSignals)
        symbols = sorted(data.index.get_level_values("symbol").unique())

        close_frames, entries_frames, exits_frames = {}, {}, {}
        funding_frames = {}
        for symbol in symbols:
            frame = cast(pd.DataFrame, data.xs(symbol, level="symbol"))
            close_col = next((c for c in frame.columns if c.endswith("ohlcv.close")), None)
            if close_col is None:
                raise ValueError("timeseries backtest requires a price.ohlcv.close feature")
            close_frames[symbol] = frame[close_col]
            entries_frames[symbol] = (
                evaluate_signal(spec.signals.entry, frame).fillna(False).astype(bool)
            )
            exits_frames[symbol] = (
                evaluate_signal(spec.signals.exit, frame).fillna(False).astype(bool)
            )
            funding_col = next((c for c in frame.columns if c.endswith("funding.rate")), None)
            if funding_col is not None:
                funding_frames[symbol] = frame[funding_col]

        close = pd.DataFrame(close_frames).sort_index()
        entries = pd.DataFrame(entries_frames).reindex(close.index).fillna(False)
        exits = pd.DataFrame(exits_frames).reindex(close.index).fillna(False)
        returns_df = close.pct_change().fillna(0.0)

        # v1 limitation: timeseries entry/exit signals are long-only — the
        # spec has no "short entry" concept distinct from "entry". A short
        # timeseries strategy needs a crosssectional spec (which does
        # support a short leg) or a custom engine.
        position_intent = _position_intent(entries, exits)
        sizer = self._registry.instantiate("alphaloop.sizers", spec.sizer.name)
        raw_weights = sizer.size(position_intent, returns_df, dict(spec.sizer.params))
        target_weights = clamp_weights(raw_weights.fillna(0.0), spec.risk)

        fee_frac = (spec.costs.fee_bps + spec.costs.slippage_bps) / 10_000
        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            # 'targetpercent' isn't supported by this vectorbt version's
            # grouped/cash-shared signal simulator; 'percent' (fraction of
            # currently free cash allocated at the entry bar) is the
            # closest supported size_type given entries/exits only ever
            # open/close a position once each (no mid-position rebalance —
            # see _position_intent above), so it behaves equivalently to a
            # target weight for this engine's signal shape.
            size=target_weights.abs(),
            size_type="percent",
            direction="longonly",
            fees=fee_frac,
            freq=spec.data_window.freq,
            init_cash=1.0,
            cash_sharing=True,
            group_by=True,
        )

        equity = pf.value()
        if isinstance(equity, pd.DataFrame):
            equity = equity.iloc[:, 0]
        returns = equity.pct_change().fillna(0.0)

        weights = pf.asset_value(group_by=False).div(equity, axis=0).fillna(0.0)
        exposure = weights.abs().sum(axis=1)

        if funding_frames and spec.costs.funding:
            funding_df = pd.DataFrame(funding_frames).reindex(close.index)
            funding_drag = pd.Series(0.0, index=close.index)
            for symbol in symbols:
                if symbol in funding_df.columns:
                    funding_drag = funding_drag.add(
                        apply_funding_cost(weights[symbol], funding_df[symbol], spec.costs),
                        fill_value=0.0,
                    )
            returns = returns - funding_drag
            equity = (1 + returns).cumprod()

        trades_df = pf.trades.records_readable
        positions = weights.stack().reset_index()
        positions.columns = ["ts", "symbol", "weight"]

        return BacktestResult(
            equity=equity,
            returns=returns,
            positions=positions,
            trades=trades_df,
            exposure=exposure,
            spec=spec,
            data_hash=data_hash,
        )
