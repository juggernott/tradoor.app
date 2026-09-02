"""Renders a ValidationReport + BacktestResult into markdown + a PNG equity curve.

Every reported number states whether it is in-sample (IS, the full spec
window) or out-of-sample (OOS, held-out walk-forward test folds) —
project principle #4. Numbers are never presented ambiguously.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alphaloop.backtest.base import BacktestResult
from alphaloop.validate.grades import ValidationReport
from alphaloop.validate.walkforward import regime_table, sharpe


@dataclass
class Scorecard:
    markdown: str
    png_path: Path | None


def render_scorecard(
    result: BacktestResult,
    report: ValidationReport,
    out_dir: str | Path,
    regime: pd.DataFrame | None = None,
) -> Scorecard:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "equity_curve.png"

    _plot_equity_curve(result.equity, png_path)

    lines = [
        f"# Scorecard — {result.spec.name}",
        "",
        f"**Verdict: {report.verdict}** · **Grade: {report.grade}**",
        "",
        f"> {result.spec.hypothesis}",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value | Sample |",
        "|---|---|---|",
        f"| Sharpe (IS, full window) | {sharpe(result.returns):.3f} | IS |",
        f"| Deflated Sharpe (OOS, probability) "
        f"| {report.evidence.oos_dsr.deflated_sharpe_ratio:.3f} | OOS |",
        f"| Deflated Sharpe (OOS, annualized value) "
        f"| {report.evidence.oos_dsr.deflated_sharpe_value:.3f} | OOS |",
        f"| OOS max drawdown | {report.evidence.oos_max_drawdown:.2%} | OOS |",
        f"| Cost-adjusted return | {report.evidence.cost_adjusted_return:.2%} | OOS |",
        f"| Data coverage | {report.evidence.data_coverage:.1%} | — |",
        f"| Trial count (this dataset-hash) | {report.evidence.oos_dsr.n_trials} | — |",
        "",
        "## Required checks",
        "",
        "| Check | Passed | Detail |",
        "|---|---|---|",
    ]
    for check in report.checks:
        mark = "✅" if check.passed else "❌"
        lines.append(f"| {check.name} | {mark} | {check.detail} |")

    lines += ["", "## Equity curve", "", "![equity curve](equity_curve.png)", ""]

    if regime is not None:
        lines += ["## Regime table (OOS)", "", regime.to_markdown(index=False), ""]

    lines += [
        "## Spec",
        "",
        f"- kind: `{result.spec.kind}`",
        f"- venue: `{result.spec.venue}`",
        f"- data window: `{result.spec.data_window.start}` → `{result.spec.data_window.end}` "
        f"@ `{result.spec.data_window.freq}`",
        f"- content hash: `{result.spec.content_hash()}`",
        f"- data hash: `{result.data_hash}`",
        "",
    ]

    markdown = "\n".join(lines)
    (out_dir / "scorecard.md").write_text(markdown)
    return Scorecard(markdown=markdown, png_path=png_path)


def _plot_equity_curve(equity: pd.Series, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")  # headless — this runs from a CLI, never a notebook
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(equity.index, equity.to_numpy(), linewidth=1.5)
    ax.set_title("Equity curve")
    ax.set_ylabel("Equity (start=1.0)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


__all__ = ["Scorecard", "render_scorecard", "regime_table"]
