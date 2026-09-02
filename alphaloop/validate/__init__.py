"""Validation gate: walk-forward, deflated Sharpe, regime table, grades, verdicts.

Nothing here promotes a strategy — it produces evidence
(:class:`alphaloop.validate.scorecard.Scorecard`) that the CLI/journal
attach a verdict to. Unknown, missing, or non-finite evidence never
passes a required check (project principle #4).
"""
