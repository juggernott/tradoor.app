"""Required checks, letter grades, and the PROMOTE/ITERATE/KILL verdict.

Grades are *relayed evidence*, never a promotion decision — a grade never
overrides a failed required check (project principle #4). Missing/NaN
evidence is treated as a failure everywhere in this module.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from alphaloop.validate.deflated_sharpe import DeflatedSharpeResult

Grade = Literal["F", "D", "C", "B", "A", "S", "SS", "SSS"]
Verdict = Literal["PROMOTE", "ITERATE", "KILL"]

# (lower_bound_inclusive, grade), ascending. A deflated Sharpe *value*
# (annualized Sharpe units, see DeflatedSharpeResult.deflated_sharpe_value)
# below the first bound is "F".
_GRADE_BANDS: list[tuple[float, Grade]] = [
    (0.8, "D"),
    (1.2, "C"),
    (1.4, "B"),
    (1.6, "A"),
    (1.8, "S"),
    (2.0, "SS"),
    (2.2, "SSS"),
]


def grade_for(deflated_sharpe_value: float) -> Grade:
    if deflated_sharpe_value is None or not math.isfinite(deflated_sharpe_value):
        return "F"
    grade: Grade = "F"
    for lower, band in _GRADE_BANDS:
        if deflated_sharpe_value >= lower:
            grade = band
    return grade


@dataclass
class RequiredCheckThresholds:
    min_dsr_probability: float = 0.95
    max_drawdown_limit: float = 0.35  # strategy's OOS max drawdown must be shallower than this
    min_cost_adjusted_return: float = 0.0
    min_data_coverage: float = 0.98  # fraction of expected bars actually present


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationEvidence:
    """Everything the required-checks validator and the scorecard need."""

    oos_dsr: DeflatedSharpeResult
    oos_max_drawdown: float
    cost_adjusted_return: float
    data_coverage: float


@dataclass
class ValidationReport:
    checks: list[CheckResult]
    grade: Grade
    verdict: Verdict
    evidence: ValidationEvidence = field(repr=False)

    @property
    def all_required_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def _finite_or_fail(value: float, name: str, predicate: Callable[[float], bool]) -> CheckResult:
    if value is None or not math.isfinite(value):
        return CheckResult(name, False, f"{name} is missing/non-finite — treated as fail")
    return CheckResult(name, bool(predicate(value)), f"{name}={value:.4f}")


class RequiredChecksValidator:
    """The default (and currently only) required-checks validator plugin."""

    name = "required_checks"

    def __init__(self, thresholds: RequiredCheckThresholds | None = None) -> None:
        self.thresholds = thresholds or RequiredCheckThresholds()

    def validate(self, evidence: ValidationEvidence) -> ValidationReport:
        t = self.thresholds
        checks = [
            _finite_or_fail(
                evidence.oos_dsr.deflated_sharpe_ratio,
                "oos_deflated_sharpe_probability",
                lambda v: v > t.min_dsr_probability,
            ),
            _finite_or_fail(
                evidence.oos_max_drawdown,
                "oos_max_drawdown",
                lambda v: abs(v) < t.max_drawdown_limit,
            ),
            _finite_or_fail(
                evidence.cost_adjusted_return,
                "cost_adjusted_return",
                lambda v: v > t.min_cost_adjusted_return,
            ),
            _finite_or_fail(
                evidence.data_coverage, "data_coverage", lambda v: v >= t.min_data_coverage
            ),
        ]

        grade = grade_for(evidence.oos_dsr.deflated_sharpe_value)
        all_passed = all(c.passed for c in checks)

        if not all_passed:
            verdict: Verdict = "KILL"
        elif grade in ("F", "D"):
            verdict = "ITERATE"
        else:
            verdict = "PROMOTE"

        return ValidationReport(checks=checks, grade=grade, verdict=verdict, evidence=evidence)
