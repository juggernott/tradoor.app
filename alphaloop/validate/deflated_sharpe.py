"""Deflated Sharpe Ratio (Bailey & López de Prado, 2014).

Reported wherever plain Sharpe is (project principle #4: "deflated Sharpe
reported wherever plain Sharpe is"). Two steps:

1. Estimate the expected maximum Sharpe ratio achievable by chance alone
   across ``n_trials`` independent attempts (``expected_max_sharpe``).
2. Compute the Probabilistic Sharpe Ratio of the observed strategy against
   that chance benchmark, correcting for the return distribution's
   skewness and kurtosis (``deflated_sharpe_ratio``) — a fat-tailed,
   negatively-skewed return stream needs a *higher* observed Sharpe to
   reach the same confidence as a normal one.

The result is a probability in [0, 1]: "probability the true Sharpe ratio
exceeds zero, after deflating for the number of trials and the return
distribution's higher moments." Not a p-value in the frequentist sense,
but used the same way — higher is more trustworthy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

_EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(trial_sharpe_std: float, n_trials: int) -> float:
    """E[max SR] under ``n_trials`` iid trials with SR ~ N(0, trial_sharpe_std^2).

    ``trial_sharpe_std`` is the cross-trial standard deviation of Sharpe
    ratios one would expect from noise alone — in the absence of a richer
    trial history, the observed strategy's own per-period Sharpe estimate's
    standard error is used as a stand-in (see :func:`deflated_sharpe_ratio`).
    """

    if n_trials <= 1:
        return 0.0
    z1 = float(stats.norm.ppf(1 - 1 / n_trials))
    z2 = float(stats.norm.ppf(1 - 1 / (n_trials * math.e)))
    return trial_sharpe_std * ((1 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)


@dataclass
class DeflatedSharpeResult:
    observed_sharpe: float
    benchmark_sharpe: float
    n_trials: int
    n_obs: int
    skew: float
    kurtosis: float
    deflated_sharpe_ratio: float  # probability, in [0, 1] — used for the required pass/fail check
    deflated_sharpe_value: float  # annualized Sharpe units — used for the letter grade bands


def deflated_sharpe_ratio(
    returns: pd.Series, n_trials: int, periods_per_year: float = 365 * 24
) -> DeflatedSharpeResult:
    """Compute the DSR for a per-period returns series.

    Args:
        returns: per-period (not annualized) net returns.
        n_trials: trial count for this dataset-hash, from
            :class:`alphaloop.validate.trials.TrialRegistry`.
        periods_per_year: for annualizing the observed Sharpe in the report
            (the DSR calculation itself works in per-period units).
    """

    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    n_obs = len(clean)
    if n_obs < 2 or clean.std(ddof=1) == 0:
        return DeflatedSharpeResult(
            observed_sharpe=float("nan"),
            benchmark_sharpe=float("nan"),
            n_trials=n_trials,
            n_obs=n_obs,
            skew=float("nan"),
            kurtosis=float("nan"),
            deflated_sharpe_ratio=0.0,
            deflated_sharpe_value=float("nan"),
        )

    sr = clean.mean() / clean.std(ddof=1)
    skew = float(stats.skew(clean, bias=False))
    kurt = float(stats.kurtosis(clean, fisher=False, bias=False))  # non-excess; normal == 3

    # Standard error of the Sharpe ratio estimate (Mertens 2002 / Lo 2002),
    # used as the cross-trial noise scale absent a richer trial history.
    sr_std = math.sqrt(max(1e-12, (1 - skew * sr + (kurt - 1) / 4 * sr**2) / (n_obs - 1)))
    sr0 = expected_max_sharpe(sr_std, n_trials)

    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    z = (sr - sr0) * math.sqrt(n_obs - 1) / denom
    dsr = float(stats.norm.cdf(z))

    observed_annualized = float(sr * math.sqrt(periods_per_year))
    benchmark_annualized = float(sr0 * math.sqrt(periods_per_year))

    return DeflatedSharpeResult(
        observed_sharpe=observed_annualized,
        benchmark_sharpe=benchmark_annualized,
        n_trials=n_trials,
        n_obs=n_obs,
        skew=skew,
        kurtosis=kurt,
        deflated_sharpe_ratio=dsr,
        # Point-estimate deflation: discount the observed Sharpe by however
        # much of it chance alone would explain given n_trials. Floored at
        # 0 (never negative benchmark credit) and can go below zero if the
        # strategy underperforms its own chance-benchmark.
        deflated_sharpe_value=observed_annualized - max(0.0, benchmark_annualized),
    )
