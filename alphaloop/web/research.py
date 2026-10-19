"""Bounded web request and dataset schemas shared with the private v12 adapter."""
from __future__ import annotations

import io
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(default="Momentum baseline", min_length=1, max_length=80)
    mode: Literal["momentum", "reversal"] = "momentum"
    capital: float = Field(default=100000, ge=100, le=1e9)
    lookback: int = Field(default=20, ge=1, le=200)
    selection: int = Field(default=1, ge=1, le=10)
    feeBps: float = Field(default=5, ge=0, le=500)
    slippageBps: float = Field(default=2, ge=0, le=500)


def csv_frame(csv: str):
    if len(csv.encode()) > 5_000_000:
        raise ValueError("CSV exceeds 5 MB")
    frame = pd.read_csv(io.StringIO(csv), dtype={"symbol": str})
    if list(frame.columns) != ["date", "symbol", "close"] or not 10 <= len(frame) <= 100000:
        raise ValueError("Expected 10–100,000 rows with header date,symbol,close")
    dates = frame["date"].astype(str)
    if not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("Dates must use YYYY-MM-DD")
    frame["ts"] = pd.to_datetime(dates, format="%Y-%m-%d", utc=True)
    if not frame["symbol"].str.fullmatch(r"[A-Za-z0-9._/-]{1,24}").fillna(False).all():
        raise ValueError("Invalid symbol")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    if not np.isfinite(frame["close"]).all() or (frame["close"] <= 0).any():
        raise ValueError("Prices must be finite and positive")
    if frame.duplicated(["ts", "symbol"]).any():
        raise ValueError("Duplicate date and symbol")
    prices = frame.pivot(index="ts", columns="symbol", values="close").sort_index()
    if not 2 <= len(prices.columns) <= 20 or not 5 <= len(prices) <= 5000 or prices.isna().any().any():
        raise ValueError("Need 2–20 assets, 5–5,000 dates, and a complete daily panel")
    if not (prices.index.to_series().diff().dropna() == pd.Timedelta(days=1)).all():
        raise ValueError("Dates must be consecutive daily bars")
    return frame.set_index(["ts", "symbol"])[["close"]].rename(columns={"close": "price.ohlcv.close"}).sort_index()


