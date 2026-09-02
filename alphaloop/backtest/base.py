"""The BacktestEngine protocol and its result type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from alphaloop.core.spec import StrategySpec


@dataclass
class BacktestResult:
    """Everything downstream (validation, scorecard, journal) needs.

    All series are indexed by timestamp (UTC). ``positions`` and
    ``trades`` carry a ``symbol`` column for multi-asset specs.
    """

    equity: pd.Series
    returns: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    exposure: pd.Series
    spec: StrategySpec
    data_hash: str


@runtime_checkable
class BacktestEngine(Protocol):
    """Runs one spec against pre-resolved data and returns a result.

    Implementations must apply ``spec.costs`` (fees, slippage, funding)
    themselves — costs are on by default (project principle #4) and are
    not layered on afterward by the caller.
    """

    name: str

    def run(self, spec: StrategySpec, data: pd.DataFrame) -> BacktestResult: ...
