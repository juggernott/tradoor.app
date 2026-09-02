# Alphaloop

*where most alpha goes to die.*

Alphaloop is an open-source (MIT) agentic research loop for crypto quants.
It takes a natural-language trading idea, compiles it into a typed
`StrategySpec`, resolves the features it needs from pluggable data
adapters, backtests it, runs it through a validation gate (walk-forward +
deflated Sharpe + a trial counter that punishes multiple testing), grades
the result honestly, journals it, and — once you've actually earned it —
lets you paper and then live trade it on Binance and Hyperliquid.

Two surfaces: a CLI (`alphaloop`), and an agent plugin
(`alphaloop/agent/SKILL.md` + `tools.json`) so Claude Code, Codex, or any
other agent can drive the same loop directly, under the same
confirmation rules a human gets.

```bash
pip install -e ".[dev,vectorbt]"
alphaloop doctor
alphaloop compile "BTC momentum: price above its 20-period mean predicts \
the next few hours" --out examples/my_idea.yaml
alphaloop run examples/my_idea.yaml --yes
alphaloop journal
```

## Why

Most backtested "alpha" is noise found by trying enough things
(multiple-testing bias), overstates itself on in-sample numbers, and dies
the moment real fees, slippage, and funding show up. Alphaloop's defaults
fight all three: costs are on by default, every backtest increments a
trial counter that discounts its own significance, and the validation
gate reports deflated Sharpe everywhere plain Sharpe would normally go.

## Everything is optional except the free path

The only hard dependency is `ccxt` (free, no key, real OHLCV data) — that's
enough to compile ideas, run cross-sectional backtests, validate them, and
build a journal of what killed what. Nothing else is required to use
Alphaloop purely as an alpha-generation and idea-triage tool:

- **Paid data adapters** (`elfa`, `nansen`, `cryptoquant`, `glassnode`) are
  never imported until you name them in `--adapter` or a spec's
  `features`, and each only raises if it's missing its own API key at
  construction time — not at import time, and not for adapters you never
  use. `alphaloop doctor` shows what's configured without requiring
  anything.
- **The `vectorbt` extra** is only needed for `kind: timeseries` specs
  (`vectorbt.Portfolio.from_signals`). `kind: crosssectional` specs run on
  plain pandas and work with zero extras installed — verified by running
  `pip install -e .` (no extras) and backtesting a crosssectional example
  end to end.
- **The `binance`/`hyperliquid` extras and the trading engine**
  (`alphaloop/execute/`) are only touched by `alphaloop paper` /
  `alphaloop trade` / `alphaloop positions` / `alphaloop flatten` — the
  research commands (`compile`, `run`, `analyze`, `journal`, `export`)
  never import them. You can use Alphaloop exclusively for idea → spec →
  backtest → validated verdict → journal, and never install an exchange
  SDK or touch a trading key.
- **The LLM compiler** is convenience sugar (see "Why" above) — every
  spec is a hand-editable YAML file, so skipping `compile` entirely and
  writing specs by hand works the same way.

## Architecture

Tiny core, everything else is a plugin. Six extension points — data
adapters, event adapters, backtest engines, sizers, executors, and
validators — are all discovered via Python entry points (see
`pyproject.toml`), so a private strategy repo can register its own
adapters and strategies without ever touching this codebase. See
[`docs/private-repo-guide.md`](docs/private-repo-guide.md).

```
alphaloop/
  core/       spec schema, feature resolver, plugin registry, loop orchestrator, confirmation protocol
  adapters/   data adapters (ccxt is real; elfa/nansen/cryptoquant are verified-skeletons — see docs/adapters.md)
  events/     non-point-in-time event streams (news/social) for live/paper hooks
  compile/    natural-language idea -> StrategySpec, via a provider-agnostic LLM compiler
  backtest/   the BacktestEngine protocol + the default vectorbt-backed implementation
  validate/   walk-forward, deflated Sharpe, trial registry, grades, scorecard rendering
  sizing/     six sizers (vol_target, kelly, atr, fixed_fractional, signal_scaled, rank_weights)
  risk/       the always-on risk layer (position/gross/net limits, drawdown kill-switch)
  execute/    paper + live executors (Binance, Hyperliquid) behind one shared runner
  journal/    append-only per-run directories + verified export bundles
  agent/      the agent-facing tool contract, mirroring the CLI exactly
  cli.py      the typer CLI
```

Read [`docs/why-deflated-sharpe.md`](docs/why-deflated-sharpe.md) for the
validation gate's reasoning, [`docs/grades.md`](docs/grades.md) for what a
grade means (and doesn't), and [`docs/adapters.md`](docs/adapters.md)
before writing a new one.

## Safety model

- **Analysis is read-only.** `analyze`, `journal`, `export`, `adapters`,
  `doctor`, `positions` never submit, modify, or trade anything.
- **Mutation needs confirmation.** `run`, `paper`, `trade`, `flatten`,
  `resume` always show the exact effective configuration and require
  explicit confirmation (`--yes` to skip in scripts/CI).
- **Live trading needs two separate acknowledgements**: `--live` AND a
  `live_trading_ack: true` in your config file. Paper is always the
  default.
- **Point-in-time integrity is enforced, not requested.** The backtester
  refuses data from any adapter that isn't marked point-in-time — see
  `alphaloop/core/resolver.py`.

## This repo is public

Nothing proprietary lives here: no strategy parameters, no API keys, no
exchange credentials, no private journal contents. `.gitignore` excludes
`journal/`, `cache/`, `state/`, and `.env*` for exactly this reason. A
private repo installs this package and registers its own adapters and
strategies via the entry-point groups above.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — "write an adapter in 30 lines"
and a list of good first issues.

## License

MIT.
