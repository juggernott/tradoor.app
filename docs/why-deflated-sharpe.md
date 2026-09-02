# Why deflated Sharpe

Plain Sharpe ratio answers "was this profitable, adjusted for volatility?"
It does not answer "how surprised should I be that this looked good?" —
and that second question is the one that actually matters when you (or an
LLM compiler, tirelessly generating variations) can try a hundred feature
combinations before lunch.

## The problem it fixes

If you backtest 100 random, edgeless strategies, the *best* one will
almost certainly show a Sharpe ratio that looks respectable — sometimes
very good — purely from noise. Reporting only that one number, without
saying how many others you tried and threw away, is how "alpha" that was
never real gets promoted, traded, and lost.

## What Alphaloop does about it

1. **Trial counter** (`alphaloop/validate/trials.py`). Every backtest run
   against a given dataset-hash increments a persistent counter. Run the
   same idea (or ten tweaks of it) against the same data ten times, and
   the eleventh run's significance bar is higher — not free.

2. **Deflated Sharpe Ratio** (`alphaloop/validate/deflated_sharpe.py`),
   from Bailey & López de Prado (2014). Two numbers come out of it:
   - `deflated_sharpe_ratio` — a probability in [0, 1]: how confident you
     can be the strategy's true Sharpe exceeds zero, *after* discounting
     for the trial count and the return distribution's skew/kurtosis (fat
     tails and negative skew both raise the bar). This is the number the
     required-checks validator gates on (default threshold: 0.95).
   - `deflated_sharpe_value` — the observed annualized Sharpe minus the
     Sharpe you'd expect to see from chance alone given the trial count.
     This is what the letter grade bands in `docs/grades.md` are measured
     against.

3. **Walk-forward, not one static split** (`alphaloop/validate/walkforward.py`).
   The evidence fed into deflated Sharpe is the concatenation of every
   walk-forward test fold's out-of-sample returns, with an embargo gap
   purged between train and test to stop a rolling-lookback feature from
   leaking across the boundary.

4. **Missing evidence never passes.** If a required metric is NaN,
   infinite, or couldn't be computed, the check fails — silence is never
   mistaken for a pass (see `alphaloop/validate/grades.py`).

## What it doesn't fix

Deflated Sharpe corrects for the number of trials *you told it about*
(the trial registry). It cannot see trials run outside Alphaloop, hand-picked
universes chosen after looking at the data, or hypotheses whose features
were selected because they happened to work in a prior, unlogged pass.
Those are still on you — the trial counter is a tool for honesty, not a
substitute for it.
