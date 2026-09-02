# Research task cards

Copy-pasteable ideas for `alphaloop compile "<idea>"` or `alphaloop new
"<idea>"` — a starting point, not a claim any of these will PROMOTE.

1. **Funding-rate mean reversion.** "When BTC perp funding rate is above
   its 7-day average, price tends to mean-revert over the next 24h —
   crowded longs paying up for leverage is a contrarian signal."
   (timeseries, needs `price.funding`)

2. **Cross-sectional volume breakout.** "Coins whose volume just broke
   out above their 30-day average outperform the rest of the universe
   over the following day." (crosssectional, `price.ohlcv`)

3. **On-chain exchange outflow momentum.** "Assets seeing sustained net
   outflows from exchanges (accumulation) outperform assets seeing net
   inflows, ranked weekly." (crosssectional, needs an on-chain adapter —
   see `docs/adapters.md` before trusting the point-in-time flag)

4. **Social sentiment spike fade.** "A sudden spike in social mention
   volume for a single asset, without a matching price move yet, tends
   to fade rather than lead — the crowd is late." (timeseries, needs
   `social.mentions`)

5. **MVRV regime filter.** "Only take the momentum signal from card #2
   when BTC's MVRV is below 2 (not obviously overheated) — combine an
   on-chain regime filter with a price-only signal." (crosssectional +
   a feature-gated variant of the entry expression)

Each card intentionally states a falsifiable causal claim in the
hypothesis, not just "this feature correlates with returns" — a good
`spec.hypothesis` should let you say, after seeing the scorecard, whether
the *claim* was right, not just whether the number was positive.
