# Alphaloop agent skill

Use this when the user wants to research, backtest, or trade a crypto
strategy idea with Alphaloop. The tool contract in `tools.json` mirrors
the CLI (`alphaloop/cli.py`) exactly — there is no separate agent code
path, so every rule in this file is just "how the CLI already behaves."

## Read-only vs. mutating

- `analyze`, `journal`, `export`, `adapters`, `doctor`, `positions` never
  submit, modify, or trade anything. Call these freely to gather context.
- `compile` only produces a spec file — it does not run it.
- `run`, `new`, `paper`, `trade`, `flatten`, `resume` are mutating: they
  write to the journal/cache, submit simulated or real orders, or clear a
  kill-switch. Every one of them requires either an interactive
  confirmation or `yes: true` passed explicitly by you AFTER the user has
  told you to proceed with the specific action shown.

## The confirmation protocol

Before calling a mutating tool, show the user the exact effective
configuration you are about to run — the resolved spec fields, venue, and
mode — not a summary like "I'll backtest your idea." Wait for the user to
say yes before setting `yes: true`. This mirrors `alphaloop.core.confirm`:
you are not bypassing a safety check, you're the human-facing half of it.

`trade` additionally needs BOTH `live: true` and `config_ack: true` before
it will place a real order — never set both without the user explicitly,
separately confirming they want real capital at risk, distinct from their
confirmation of the trade's parameters.

## Typical flow

1. `compile` the user's idea -> show them the spec YAML -> let them edit
   it in place if they want changes (it's just a file).
2. `run` the (possibly edited) spec -> read the verdict/grade from the
   result -> if `KILL` or `ITERATE`, you may propose next experiments
   (call the compiler's `propose_next_experiments`, exposed as no direct
   CLI command today — read `journal/<run>/scorecard.md` and reason about
   it directly, or shell out to `python -c` invoking
   `alphaloop.compile.llm.StrategyCompiler.propose_next_experiments`).
3. Only after the user has seen a `PROMOTE` verdict and explicitly asks
   to trade it: `paper` first, always. `trade --venue X` only on the
   user's explicit, separate instruction, and only ever with `testnet:
   true` unless they've said the words "mainnet" or "live money" (or
   equivalent) themselves.

## What NOT to do

- Never chain `compile` directly into `run` with `yes: true` without
  showing the user the compiled spec first — the compiler is a
  convenience, not an autopilot.
- Never set `live: true` because a backtest looked good. A good backtest
  is not user authorization to trade real capital.
- Never edit `journal/` entries in place. If a past run's spec was wrong,
  compile a new one — the journal is append-only by design.
