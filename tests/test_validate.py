import numpy as np
import pandas as pd
import pytest

from alphaloop.validate.deflated_sharpe import deflated_sharpe_ratio, expected_max_sharpe
from alphaloop.validate.grades import (
    RequiredChecksValidator,
    ValidationEvidence,
    grade_for,
)
from alphaloop.validate.trials import TrialRegistry
from alphaloop.validate.walkforward import (
    max_drawdown,
    regime_labels,
    regime_table,
    sharpe,
    walk_forward_splits,
)


def test_expected_max_sharpe_increases_with_trials():
    assert expected_max_sharpe(1.0, 100) > expected_max_sharpe(1.0, 2)


def test_expected_max_sharpe_zero_for_single_trial():
    assert expected_max_sharpe(1.0, 1) == 0.0


def test_deflated_sharpe_more_trials_lowers_significance():
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0.002, 0.01, 500))
    few = deflated_sharpe_ratio(returns, n_trials=1)
    many = deflated_sharpe_ratio(returns, n_trials=1000)
    assert many.deflated_sharpe_ratio <= few.deflated_sharpe_ratio
    assert many.deflated_sharpe_value <= few.deflated_sharpe_value


def test_deflated_sharpe_handles_degenerate_input():
    result = deflated_sharpe_ratio(pd.Series([0.0, 0.0, 0.0]), n_trials=1)
    assert result.deflated_sharpe_ratio == 0.0


def test_grade_bands():
    assert grade_for(0.5) == "F"
    assert grade_for(0.8) == "D"
    assert grade_for(1.2) == "C"
    assert grade_for(1.4) == "B"
    assert grade_for(1.6) == "A"
    assert grade_for(1.8) == "S"
    assert grade_for(2.0) == "SS"
    assert grade_for(2.5) == "SSS"


def test_grade_nan_is_f():
    assert grade_for(float("nan")) == "F"


def test_walk_forward_splits_expanding():
    index = pd.date_range("2024-01-01", periods=120, freq="1h")
    splits = walk_forward_splits(index, n_splits=3, embargo=2)
    assert len(splits) == 3
    for s in splits:
        assert s.train[-1] < s.test[0]
        assert len(s.test) > 0


def test_walk_forward_too_few_obs_raises():
    with pytest.raises(ValueError):
        walk_forward_splits(pd.date_range("2024-01-01", periods=3, freq="1h"), n_splits=5)


def test_sharpe_and_drawdown():
    returns = pd.Series([0.01, -0.02, 0.03, -0.01])
    assert sharpe(returns) != 0
    equity = (1 + returns).cumprod()
    assert max_drawdown(equity) < 0


def test_regime_table_partitions_all_periods():
    index = pd.date_range("2024-01-01", periods=200, freq="1h")
    btc = pd.Series(100 + np.linspace(0, 20, 200), index=index)
    labels = regime_labels(btc, trend_window=10)
    returns = pd.Series(0.001, index=index)
    table = regime_table(returns, labels)
    assert table["n_periods"].sum() <= len(index)
    assert set(table["regime"]) == {"bull", "bear", "chop"}


def test_trial_registry_persists(tmp_path):
    path = tmp_path / "trials.json"
    registry = TrialRegistry(path)
    assert registry.trial_count("abc") == 0
    assert registry.record_trial("abc") == 1
    assert registry.record_trial("abc") == 2

    reloaded = TrialRegistry(path)
    assert reloaded.trial_count("abc") == 2


def test_required_checks_missing_evidence_fails():
    from alphaloop.validate.deflated_sharpe import DeflatedSharpeResult

    nan_dsr = DeflatedSharpeResult(
        observed_sharpe=float("nan"),
        benchmark_sharpe=float("nan"),
        n_trials=1,
        n_obs=0,
        skew=float("nan"),
        kurtosis=float("nan"),
        deflated_sharpe_ratio=0.0,
        deflated_sharpe_value=float("nan"),
    )
    evidence = ValidationEvidence(
        oos_dsr=nan_dsr,
        oos_max_drawdown=float("nan"),
        cost_adjusted_return=float("nan"),
        data_coverage=float("nan"),
    )
    report = RequiredChecksValidator().validate(evidence)
    assert report.verdict == "KILL"
    assert not report.all_required_passed


def test_grade_never_overrides_failed_check():
    from alphaloop.validate.deflated_sharpe import DeflatedSharpeResult

    great_grade_but_failing = DeflatedSharpeResult(
        observed_sharpe=3.0,
        benchmark_sharpe=0.5,
        n_trials=1,
        n_obs=1000,
        skew=0.0,
        kurtosis=3.0,
        deflated_sharpe_ratio=0.5,  # below the 0.95 required threshold
        deflated_sharpe_value=2.5,  # would grade SSS
    )
    evidence = ValidationEvidence(
        oos_dsr=great_grade_but_failing,
        oos_max_drawdown=0.05,
        cost_adjusted_return=0.10,
        data_coverage=1.0,
    )
    report = RequiredChecksValidator().validate(evidence)
    assert report.grade == "SSS"
    assert report.verdict == "KILL"  # DSR probability check failed despite the grade
