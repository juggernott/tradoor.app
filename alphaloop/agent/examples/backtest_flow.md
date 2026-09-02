# Example agent transcript: compile -> confirm -> run

**User:** I think BTC momentum over the last day predicts the next few
hours. Can you test that?

**Agent:**
1. Calls `alphaloop_compile` with the idea text.
2. Shows the user the returned spec YAML verbatim (kind, features, signals,
   sizer, risk, costs, data_window) — not a paraphrase.
3. Asks: "Want me to run this backtest as-is, or adjust anything first
   (lookback window, universe, rebalance cadence)?"
4. User says "run it."
5. Calls `alphaloop_run` with `spec_path` pointing at the saved spec and
   `yes: true` — this is safe because the user just approved these exact
   parameters in step 3/4.
6. Reports the verdict, grade, and headline OOS deflated Sharpe from the
   result. Does NOT propose trading it — that requires the user to ask.

**User:** Nice, PROMOTE. Paper trade it.

**Agent:**
1. Shows the effective paper-trading configuration (spec name, venue).
2. Calls `alphaloop_paper` with `yes: true` (user just said "paper trade
   it" — this is the explicit ask this specific action needed).
3. Reports the runner id and that it's simulated fills only.

**User:** ok now put $500 live on hyperliquid mainnet

**Agent:**
1. States clearly that this places real orders with real capital risk.
2. Shows the resolved config: venue=hyperliquid, testnet=false,
   notional≈$500 worth of the spec's target weights.
3. Only after the user reconfirms does it call `alphaloop_trade` with
   `venue: "hyperliquid"`, `testnet: false`, `live: true`,
   `config_ack: true`, `yes: true` — all four together, because the user's
   own words ("live", "mainnet") satisfied the separate live-trading
   acknowledgement this tool requires.
