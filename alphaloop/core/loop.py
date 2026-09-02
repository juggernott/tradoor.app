"""The orchestrator: spec -> resolved data -> backtest -> validation -> journal.

This is what ``alphaloop run`` (and the agent's ``run`` tool) actually
calls. It is intentionally a thin composition of already-independent
pieces (resolver, engine, validator, journal) rather than a place where
new logic should live — if you're adding behavior here, it probably
belongs in one of those modules instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from alphaloop.backtest.base import BacktestEngine, BacktestResult
from alphaloop.backtest.signals import evaluate_signal
from alphaloop.core.registry import Registry, default_registry
from alphaloop.core.resolver import Resolver
from alphaloop.core.spec import CrossSectionalSignals, StrategySpec, TimeseriesSignals
from alphaloop.risk.limits import clamp_weights, drawdown_breach
from alphaloop.sizing.rank_weights import rank_weights_from_scores
from alphaloop.validate.deflated_sharpe import deflated_sharpe_ratio
from alphaloop.validate.grades import ValidationEvidence, ValidationReport
from alphaloop.validate.trials import TrialRegistry
from alphaloop.validate.walkforward import (
    max_drawdown,
    turnover_cost_diagnostics,
    walk_forward_splits,
)


@dataclass
class RunOutcome:
    result: BacktestResult
    report: ValidationReport
    expected_bars: int
    actual_bars: int


def run_backtest(
    spec: StrategySpec,
    resolver: Resolver,
    engine: BacktestEngine | None = None,
    n_splits: int = 5,
    embargo: int = 0,
    trial_registry: TrialRegistry | None = None,
    registry: Registry = default_registry,
) -> RunOutcome:
    """Resolve data, run the backtest engine, walk-forward validate, grade.

    The OOS evidence fed to the validator is the concatenation of every
    walk-forward test fold's returns/equity — not the single last fold —
    so the reported OOS Sharpe reflects performance across the whole
    walk-forward schedule, not just however the most recent regime went.
    """

    universe = _universe_symbols(spec)
    data = resolver.resolve(
        spec.features,
        universe,
        spec.data_window.start,
        spec.data_window.end,
        spec.data_window.freq,
        mode="backtest",
    )

    expected_bars = len(
        pd.date_range(spec.data_window.start, spec.data_window.end, freq=spec.data_window.freq)
    )
    actual_bars = len(data.index.get_level_values("ts").unique())
    coverage = actual_bars / expected_bars if expected_bars else 0.0

    engine = engine or registry.instantiate("alphaloop.engines", "vectorbt")
    result = engine.run(spec, data)

    trial_registry = trial_registry or TrialRegistry()
    n_trials = trial_registry.record_trial(result.data_hash)

    splits = walk_forward_splits(result.returns.index, n_splits=n_splits, embargo=embargo)
    oos_returns = (
        pd.concat([result.returns.reindex(s.test).dropna() for s in splits])
        if splits
        else result.returns
    )
    oos_equity = (1 + oos_returns).cumprod()

    dsr = deflated_sharpe_ratio(oos_returns, n_trials=n_trials)
    oos_dd = max_drawdown(oos_equity) if len(oos_equity) else float("nan")
    cost_adjusted_return = float(oos_equity.iloc[-1] - 1) if len(oos_equity) else float("nan")

    evidence = ValidationEvidence(
        oos_dsr=dsr,
        oos_max_drawdown=oos_dd,
        cost_adjusted_return=cost_adjusted_return,
        data_coverage=coverage,
    )
    validator = registry.instantiate("alphaloop.validators", "required_checks")
    report = validator.validate(evidence)

    return RunOutcome(
        result=result, report=report, expected_bars=expected_bars, actual_bars=actual_bars
    )


def kill_switch_status(result: BacktestResult, spec: StrategySpec) -> bool:
    """Whether the drawdown kill-switch would have tripped anywhere in this run."""

    return bool(drawdown_breach(result.equity, spec.risk).any())


def turnover_diagnostics(result: BacktestResult) -> dict[str, float]:
    return turnover_cost_diagnostics(result.positions, spec_costs_bps(result.spec))


def spec_costs_bps(spec: StrategySpec) -> float:
    return spec.costs.fee_bps + spec.costs.slippage_bps


def compute_live_target_weights(
    spec: StrategySpec,
    resolver: Resolver,
    lookback_bars: int = 500,
    registry: Registry = default_registry,
) -> dict[str, float]:
    """The target weights a paper/live runner tick should reconcile toward, right now.

    Fetches the last ``lookback_bars`` of each configured feature (enough
    history for the signal's rolling windows to warm up), evaluates the
    spec's signal expression(s), sizes and risk-clamps it exactly like the
    backtester does, and returns just the most recent bar's weights — the
    only thing a live tick needs.
    """

    from alphaloop.backtest.vectorbt_engine import _position_intent

    universe = _universe_symbols(spec)
    end = pd.Timestamp.now(tz="UTC")
    start = end - lookback_bars * pd.Timedelta(spec.data_window.freq)
    data = resolver.resolve(
        spec.features, universe, start.isoformat(), end.isoformat(),
        spec.data_window.freq, mode="live",
    )
    if data.empty:
        return dict.fromkeys(universe, 0.0)

    symbols = sorted(data.index.get_level_values("symbol").unique())
    sizer = registry.instantiate("alphaloop.sizers", spec.sizer.name)

    def _symbol_frame(symbol: str) -> pd.DataFrame:
        return cast(pd.DataFrame, data.xs(symbol, level="symbol"))

    def _close_series(frame: pd.DataFrame) -> pd.Series:
        close_col = next((c for c in frame.columns if c.endswith("ohlcv.close")), None)
        return frame[close_col] if close_col else frame[frame.columns[0]]

    if isinstance(spec.signals, TimeseriesSignals):
        entries, exits, closes = {}, {}, {}
        for symbol in symbols:
            frame = _symbol_frame(symbol)
            entries[symbol] = evaluate_signal(spec.signals.entry, frame).fillna(False).astype(bool)
            exits[symbol] = evaluate_signal(spec.signals.exit, frame).fillna(False).astype(bool)
            closes[symbol] = _close_series(frame)
        entries_df = pd.DataFrame(entries).sort_index()
        exits_df = pd.DataFrame(exits).reindex(entries_df.index).fillna(False)
        returns_df = (
            pd.DataFrame(closes).sort_index().reindex(entries_df.index).pct_change().fillna(0.0)
        )
        position_intent = _position_intent(entries_df, exits_df)
        raw_weights = sizer.size(position_intent, returns_df, dict(spec.sizer.params))
    else:
        assert isinstance(spec.signals, CrossSectionalSignals)
        scores, closes = {}, {}
        for symbol in symbols:
            frame = _symbol_frame(symbol)
            scores[symbol] = evaluate_signal(spec.signals.score, frame)
            closes[symbol] = _close_series(frame)
        score_df = pd.DataFrame(scores).sort_index()
        returns_df = (
            pd.DataFrame(closes).sort_index().reindex(score_df.index).pct_change().fillna(0.0)
        )
        if spec.sizer.name == "rank_weights":
            score_weighted = bool(spec.sizer.params.get("score_weighted", False))
            raw_weights = rank_weights_from_scores(
                score_df, spec.signals, score_weighted=score_weighted
            )
        else:
            params: dict[str, Any] = dict(spec.sizer.params)
            params["_signals"] = spec.signals
            raw_weights = sizer.size(score_df, returns_df, params)

    weights = clamp_weights(raw_weights.fillna(0.0), spec.risk)
    if weights.empty:
        return dict.fromkeys(universe, 0.0)
    last_row = weights.iloc[-1]
    return {str(symbol): float(w) for symbol, w in last_row.items()}


def _universe_symbols(spec: StrategySpec) -> list[str]:
    from alphaloop.core.spec import SymbolUniverse

    if isinstance(spec.universe, SymbolUniverse):
        return spec.universe.symbols
    raise NotImplementedError(
        "screen-based universes are not yet resolved by core.loop — "
        "provide an explicit universe.symbols list for now."
    )
