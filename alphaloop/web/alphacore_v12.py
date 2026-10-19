"""Glue for the user's private v12 library; contains no copied v12 source.

Uses the actual rate_of_change factor and validation.backtest_v2. Basket ranking
and aggregation are explicitly Tradoor's baseline adapter, not v12's locked live
roster, HRP allocator, HMM regime engine, or a production promotion verdict.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import sys
import types
import warnings

import numpy as np
import pandas as pd
import polars as pl

from alphaloop.web.engine import EngineUnavailable, source_root
from alphaloop.web.research import Config, csv_frame

SOURCE_FILES = ("backtest.py", "validation.py", "datasource.py", "eda.py", "factor.py", "normalisers.py", "signals.py", "__init__.py")


class AlphacoreV12:
    minimum_bars = 500
    warmup_multiplier = 2
    def __init__(self, root=None):
        configured = str(root or source_root())
        if not configured:
            raise EngineUnavailable("Alphacore v12 source is not configured. Set TRADOOR_ALPHACORE_ROOT or state/engine.json.")
        root = Path(configured).resolve()
        lib = root/"research"/"lib"
        if not all((lib/name).is_file() for name in SOURCE_FILES):
            raise EngineUnavailable("Alphacore v12 research library is missing or incomplete")
        digest = hashlib.sha256()
        self.provenance = {}
        for name in SOURCE_FILES:
            content = (lib/name).read_bytes()
            digest.update(name.encode()+b"\0"+content)
            self.provenance["research/lib/"+name] = hashlib.sha256(content).hexdigest()
        self.source_sha256 = digest.hexdigest()
        self.name = "alphacore-v12@"+self.source_sha256[:12]
        # Unique package namespace prevents collision with other projects' generic
        # `research` packages. Do not import the private live API or its .env loader.
        namespace = "_tradoor_private_v12_"+self.source_sha256[:12]
        if namespace not in sys.modules:
            package = types.ModuleType(namespace)
            package.__path__ = [str(root/"research")]
            sys.modules[namespace] = package
        with warnings.catch_warnings():
            self.validation = importlib.import_module(namespace+".lib.validation")
            self.factor = importlib.import_module(namespace+".lib.factor")

    def weight_history(self, frame, config):
        config = Config.model_validate(config)
        prices = frame["price.ohlcv.close"].unstack("symbol").sort_index().sort_index(axis=1)
        if prices.isna().any().any() or config.selection*2>len(prices.columns):
            raise ValueError("Complete price panel and non-overlapping baskets are required")
        scores = np.column_stack([self.factor.rate_of_change(pl.Series(prices[s].to_numpy()), config.lookback).to_numpy() for s in prices.columns])
        if config.mode == "reversal":
            scores = -scores
        weights = np.zeros_like(scores, dtype=float)
        # A full ROC/std window is used for forward/backtest consistency; warmup is flat.
        for i in range(2*config.lookback, len(prices)):
            row = scores[i]
            if not np.isfinite(row).all():
                raise ValueError("V12 returned a non-finite score")
            if np.allclose(row, 0, atol=1e-14):
                continue
            order = np.argsort(-row, kind="stable")
            weights[i,order[:config.selection]] = .5/config.selection
            weights[i,order[-config.selection:]] = -.5/config.selection
        return prices, pd.DataFrame(weights,index=prices.index,columns=prices.columns)

    def weights(self, frame, config, frequency):
        if frequency != "1d":
            raise ValueError("The current v12 adapter supports daily price baselines only")
        if len(frame.index.get_level_values("ts").unique()) < 2*int(config["lookback"])+1:
            raise ValueError("Insufficient v12 closed-bar warmup history")
        _prices, weights = self.weight_history(frame, config)
        return {str(s): float(w) for s,w in weights.iloc[-1].items()}

    def backtest(self, csv, config, identifier, source):
        request = Config.model_validate(config)
        frame = csv_frame(csv)
        prices, weights = self.weight_history(frame, config)
        if len(prices)<max(500, 2*request.lookback+3):
            raise ValueError("V12 research requires at least 500 daily bars and a complete signal warmup")
        timestamps = prices.index.tz_convert(None).to_pydatetime().tolist()
        returns = np.zeros(len(prices))
        legs, trades = [], []
        for symbol in prices.columns:
            leg = self.validation.backtest_v2(
                pl.DataFrame({"timestamp":timestamps,"close":prices[symbol].to_numpy()}),
                pl.Series(weights[symbol].to_numpy()), lag_days=0,
                fee_rate=request.feeBps/10000,slippage=request.slippageBps/10000,
                funding=None,annualisation=365.0,
            )
            if "error" in leg:
                raise ValueError("V12 could not evaluate an asset sleeve")
            returns += np.asarray(leg["returns"],dtype=float)
            legs.append({"symbol":str(symbol),**{k:v for k,v in leg.items() if k not in {"returns","timestamps"}}})
            executed = weights[symbol].shift(1,fill_value=0)
            delta = executed.diff().fillna(executed.iloc[0])
            for ts, change in delta[delta.abs()>1e-12].items():
                trades.append({"date":ts.isoformat(),"symbol":str(symbol),"weight_change":float(change),"basis":"v12 shifted target-weight change"})
        if not np.isfinite(returns).all() or (returns <= -1).any():
            raise ValueError("Portfolio became insolvent or produced invalid returns")
        equity = request.capital*np.cumprod(1+returns)
        curve = [{"date":ts.isoformat(),"equity":float(v)} for ts,v in zip(prices.index,equity,strict=True)]
        peak = np.maximum.accumulate(np.r_[request.capital,equity])
        drawdown = 1-np.r_[request.capital,equity]/peak
        std = float(np.std(returns,ddof=1))
        split = int(len(returns)*.7)
        def period_stats(r):
            std = float(np.std(r,ddof=1))
            return {"return":float(np.prod(1+r)-1),"sharpe":float(np.mean(r)/std*np.sqrt(365)) if std>1e-12 else None,"bars":len(r)}
        return {"id":identifier,"engine":self.name,"name":request.name,"config":config,"source":source,
            "status":"completed","equity":float(equity[-1]),"curve":curve,
            "metrics":{"totalReturn":float(equity[-1]/request.capital-1),"maxDrawdown":float(drawdown.max()),
                       "sharpe":float(np.mean(returns)/std*np.sqrt(365)) if std>1e-12 else None,"bars":len(prices)},
            "evaluation":{"in_sample":period_stats(returns[:split]),"out_of_sample":period_stats(returns[split:]),"split":"70/30 chronological; descriptive, not a selection-adjusted verdict"},
            "legs":legs,"trades":trades,"weights":[{"date":ts.isoformat(),"symbol":str(s),"weight":float(w)} for ts,row in weights.iterrows() for s,w in row.items()],
            "source_sha256":self.source_sha256,"source_files":self.provenance,"csv_sha256":hashlib.sha256(csv.encode()).hexdigest(),
            "assumptions":"Actual v12 rate_of_change factor and backtest_v2 per asset; Tradoor ranks and sums sleeve returns. One-bar signal shift with close-to-close returns, 365-day annualization, configured turnover fees/slippage. Price-only: no publication lag, funding, borrow, margin, liquidation or next-open fills. Final positions marked, not liquidated. No production roster, HMM/HRP allocation, alpha grade or promotion is implied."}


def create_engine():
    return AlphacoreV12()
