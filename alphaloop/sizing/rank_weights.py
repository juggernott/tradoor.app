"""Rank-based long/short basket weights. Default sizer for crosssectional specs.

Given per-symbol scores, ranks the cross-section at each timestamp and
assigns equal (or score-weighted) weight to the top ``top_n``/``top_pct``
(long) and bottom ``bottom_n``/``bottom_pct`` (short), gross-normalized to
1.0 (0.5 long / 0.5 short when both legs are active).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from alphaloop.core.spec import CrossSectionalSignals


def rank_weights_from_scores(
    score_df: pd.DataFrame, signals: CrossSectionalSignals, score_weighted: bool = False
) -> pd.DataFrame:
    symbols = list(score_df.columns)
    weights = pd.DataFrame(0.0, index=score_df.index, columns=symbols)
    for ts, row in score_df.iterrows():
        row = row.dropna()
        n = len(row)
        if n == 0:
            continue
        ranked = row.rank(ascending=False)
        top_n = signals.top_n or max(1, round(n * (signals.top_pct or 0)))
        bottom_n = signals.bottom_n or (
            max(1, round(n * signals.bottom_pct)) if signals.bottom_pct else 0
        )
        longs = ranked[ranked <= top_n].index
        shorts = ranked[ranked > n - bottom_n].index if bottom_n else pd.Index([])

        long_budget = 0.5 if len(shorts) else 1.0
        short_budget = 0.5 if len(shorts) else 0.0

        w = pd.Series(0.0, index=symbols)
        if len(longs):
            if score_weighted:
                raw = row[longs].clip(lower=0)
                w[longs] = (
                    (raw / raw.sum() * long_budget) if raw.sum() > 0 else long_budget / len(longs)
                )
            else:
                w[longs] = long_budget / len(longs)
        if len(shorts):
            if score_weighted:
                raw = (-row[shorts]).clip(lower=0)
                w[shorts] = (
                    -(raw / raw.sum() * short_budget)
                    if raw.sum() > 0
                    else -short_budget / len(shorts)
                )
            else:
                w[shorts] = -short_budget / len(shorts)
        weights.loc[ts] = w
    return weights


class RankWeightsSizer:
    """Adapts :func:`rank_weights_from_scores` to the Sizer protocol.

    Note: unlike the other sizers, this one needs ``spec.signals`` (for
    top_n/bottom_n) rather than just ``signal``/``returns``/``params``, so
    it also accepts ``signals`` via ``params["_signals"]`` — set by
    :mod:`alphaloop.backtest.crosssectional`, which is the only caller.
    """

    name = "rank_weights"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        signals: CrossSectionalSignals = params["_signals"]
        score_weighted = bool(params.get("score_weighted", False))
        return rank_weights_from_scores(signal, signals, score_weighted=score_weighted)
