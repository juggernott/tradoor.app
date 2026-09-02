"""StrategySpec: the one typed contract everything else in Alphaloop hangs off.

A spec is a file, not a database row. It round-trips to YAML byte-for-byte
meaningfully (``StrategySpec.to_yaml`` / ``.from_yaml``), is hand-editable,
and the LLM compiler in :mod:`alphaloop.compile` is a convenience that
produces one — never a dependency for using Alphaloop.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

FeatureId = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9_]+\.[a-z0-9_]+(:[a-zA-Z0-9]+)?$",
        description="Namespaced feature id, e.g. 'price.ohlcv:1h' or 'onchain.mvrv'.",
    ),
]


class SymbolUniverse(BaseModel):
    """A fixed, explicit list of symbols."""

    symbols: list[str] = Field(min_length=1)


class ScreenUniverse(BaseModel):
    """A rule-based universe, resolved at run time against a data adapter.

    ``rules`` is intentionally an opaque dict here — the resolver hands it to
    whichever adapter/engine understands screening; core does not interpret
    it. Keeping it opaque is what lets a private repo define new screen
    grammars without a core release.
    """

    screen: dict[str, object] = Field(min_length=1)


class TimeseriesSignals(BaseModel):
    """Per-asset entry/exit rule identifiers, resolved by the backtest engine."""

    entry: str
    exit: str


class CrossSectionalSignals(BaseModel):
    """Rank-the-universe, long top / short bottom, periodic rebalance."""

    score: str
    rebalance: str
    top_n: int | None = Field(default=None, gt=0)
    top_pct: float | None = Field(default=None, gt=0, le=1)
    bottom_n: int | None = Field(default=None, gt=0)
    bottom_pct: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def _one_of_n_or_pct(self) -> CrossSectionalSignals:
        if self.top_n is not None and self.top_pct is not None:
            raise ValueError("set either top_n or top_pct, not both")
        if self.bottom_n is not None and self.bottom_pct is not None:
            raise ValueError("set either bottom_n or bottom_pct, not both")
        if self.top_n is None and self.top_pct is None:
            raise ValueError("crosssectional signals require top_n or top_pct")
        return self


class SizerConfig(BaseModel):
    name: str
    params: dict[str, float | int | str | bool] = Field(default_factory=dict)


class RiskLimits(BaseModel):
    """Always-on clamps applied to sizer output. See alphaloop.risk.limits."""

    max_position_pct: float = Field(default=0.10, gt=0, le=1)
    max_gross_exposure: float = Field(default=1.0, gt=0)
    max_net_exposure: float = Field(default=1.0, gt=0)
    per_trade_risk_pct: float = Field(default=0.02, gt=0, le=1)
    drawdown_halt_pct: float = Field(
        default=0.25, gt=0, le=1, description="Peak-to-trough drawdown that trips the kill-switch."
    )


class CostModel(BaseModel):
    fee_bps: float = Field(default=7.5, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    funding: bool = True


class DataWindow(BaseModel):
    start: str
    end: str
    freq: str = "1h"

    @model_validator(mode="after")
    def _start_before_end(self) -> DataWindow:
        import pandas as pd

        if pd.Timestamp(self.start) >= pd.Timestamp(self.end):
            raise ValueError(f"data_window.start ({self.start}) must be before end ({self.end})")
        return self


class StrategySpec(BaseModel):
    """The typed, serializable description of one strategy idea.

    Instances are immutable once created (``model_config.frozen``); build a
    new spec (e.g. via ``model_copy(update=...)``) rather than mutating one
    that has already been journaled, so journal entries stay honest replays
    of what actually ran.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    kind: Literal["timeseries", "crosssectional"]
    universe: SymbolUniverse | ScreenUniverse
    features: list[FeatureId] = Field(min_length=1)
    signals: TimeseriesSignals | CrossSectionalSignals
    sizer: SizerConfig
    risk: RiskLimits = Field(default_factory=RiskLimits)
    costs: CostModel = Field(default_factory=CostModel)
    data_window: DataWindow
    venue: str
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kind_matches_signals(self) -> StrategySpec:
        if self.kind == "timeseries" and not isinstance(self.signals, TimeseriesSignals):
            raise ValueError("kind='timeseries' requires signals.entry/signals.exit")
        if self.kind == "crosssectional" and not isinstance(self.signals, CrossSectionalSignals):
            raise ValueError(
                "kind='crosssectional' requires signals.score/signals.rebalance "
                "and one of top_n/top_pct"
            )
        return self

    # -- serialization -----------------------------------------------------

    def to_yaml(self) -> str:
        data = self.model_dump(mode="json", exclude_none=True)
        return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

    @classmethod
    def from_yaml(cls, text: str) -> StrategySpec:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("spec YAML must deserialize to a mapping")
        return cls.model_validate(data)

    @classmethod
    def load(cls, path: str | Path) -> StrategySpec:
        return cls.from_yaml(Path(path).read_text())

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_yaml())

    # -- identity ------------------------------------------------------

    def content_hash(self) -> str:
        """Stable hash of the spec's economically-meaningful content.

        Used by the trial registry (one counter per dataset-hash) and by
        journal dedup — two specs with the same hash are the same
        hypothesis for accounting purposes, even if ``name``/``hypothesis``
        prose differs.
        """

        payload = self.model_dump_json(exclude={"name", "hypothesis", "tags"})
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
