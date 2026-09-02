# Live trading

Live trading is not "done" until each venue passes the acceptance test
below — read this before you flip `--live`.

## The two-acknowledgement gate

`alphaloop trade spec.yaml --venue X --live` refuses to run unless you
*also* pass `--config-ack`, which corresponds to a `live_trading_ack:
true` line you added yourself to your Alphaloop config file. This is
deliberately two separate things: a CLI flag you type in the moment, and
a standing acknowledgement you had to go add to a file beforehand. Neither
alone is enough — see `alphaloop/core/confirm.py::require_live_ack`.

Without `--live`, `alphaloop trade` runs against `--testnet` by default,
or `--dry-run` (logs the order set it would submit, submits nothing).

## Acceptance test (per venue, before it's trusted)

1. **Testnet full cycle**: open a position, scale it up, scale it down,
   flatten it, on testnet.
2. **Mainnet dry-run for 24h**: `--live --dry-run` against real mainnet
   prices, logging every order it *would* place, placing none.
3. **Mainnet with ~$20 notional**: open, scale, reduce, flatten, trip the
   kill-switch on purpose (lower `risk.drawdown_halt_pct` temporarily),
   and crash-and-resume the runner process mid-cycle to confirm
   `alphaloop resume <run-id> --ack` and the persisted `state/<run-id>.json`
   bring it back with no duplicate orders.

Do this for Binance and Hyperliquid independently — passing on one venue
says nothing about the other's precision/limits handling.

## Kill-switch

The risk layer's drawdown halt (`spec.risk.drawdown_halt_pct`) trips
automatically inside `alphaloop.execute.runner.Runner.tick`: it flattens
every position at the venue, cancels open orders, marks the runner state
halted, and refuses further ticks until `alphaloop resume <run-id> --ack`.
`alphaloop flatten --venue X` is the manual, always-available override —
it does not require the runner to be halted first.

## What crash-and-resume actually verifies

`RunnerState` (`alphaloop/execute/state.py`) persists open-order tracking,
last-reconciled weights, and halt status to `state/<run-id>.json`. On
restart, the runner reloads that file but always re-fetches venue-truth
positions from the executor before reconciling again — it never trusts
the file's positions, only its halt/order bookkeeping. That's what makes
`reconcile` idempotent across a crash: the "current state" it diffs
against always comes from the venue, not memory.
