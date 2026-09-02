# Grades

A grade is relayed evidence, not a promotion decision. It **never**
overrides a failed required check — see `alphaloop/validate/grades.py`,
specifically `RequiredChecksValidator.validate`: the verdict is `KILL`
whenever any required check fails, full stop, regardless of what grade
the same run would otherwise earn.

## Bands

Grades are bands on `deflated_sharpe_value` — the observed OOS annualized
Sharpe minus the chance-benchmark Sharpe implied by your trial count (see
`docs/why-deflated-sharpe.md` for what that means and why it's not just
"Sharpe ratio").

| Grade | Deflated Sharpe value |
|---|---|
| F | < 0.8 |
| D | 0.8 – 1.2 |
| C | 1.2 – 1.4 |
| B | 1.4 – 1.6 |
| A | 1.6 – 1.8 |
| S | 1.8 – 2.0 |
| SS | 2.0 – 2.2 |
| SSS | ≥ 2.2 |

Missing or non-finite input is always graded `F` — never treated as "no
data, so let's not penalize it."

## Required checks (gate the verdict, independent of grade)

1. `oos_deflated_sharpe_probability > 0.95` (the *other* deflated Sharpe
   number — the probability, not the value used for grading)
2. `abs(oos_max_drawdown) < 0.35`
3. `cost_adjusted_return > 0`
4. `data_coverage >= 0.98`

Thresholds live in `alphaloop.validate.grades.RequiredCheckThresholds` and
are constructor arguments to `RequiredChecksValidator` — override them per
run if your risk tolerance differs, but the defaults are what
`alphaloop run` uses out of the box.

## Verdict

- Any required check fails → **KILL**, regardless of grade.
- All required checks pass, grade is F or D → **ITERATE** (evidence says
  "not there yet, but not obviously wrong either").
- All required checks pass, grade C or better → **PROMOTE**.

`PROMOTE` means "the evidence clears the bar to paper trade it." It does
not mean "trade it live" — see the confirmation protocol in
`alphaloop/core/confirm.py` and `alphaloop/agent/SKILL.md` for what
happens (and doesn't happen automatically) after a PROMOTE.
