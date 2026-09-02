# Contributing to Alphaloop

## Setup

```bash
git clone <this repo>
cd alphaloop
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,vectorbt]"
pre-commit install
pytest
```

## Write an adapter in 30 lines

See [`docs/adapters.md`](docs/adapters.md) — the whole contract is a
`name`, a `provides` set, a `point_in_time` bool, and one `fetch` method.
Register it via an `alphaloop.adapters` entry point in your package (or,
for a contribution to this repo, in `pyproject.toml` here). Never guess an
endpoint's response shape — if you can't verify it from public docs,
implement the skeleton + interface test and mark it `TODO(verify)`
(see `alphaloop/adapters/elfa.py` for the pattern).

## Code style

- `ruff check .` and `ruff format .` before committing (or let
  pre-commit do it).
- `mypy alphaloop` — core is `strict = true`; keep type hints real, not
  `Any`-shaped escape hatches.
- `pytest` — mock adapters (see `tests/conftest.py::MockAdapter`), never
  live API keys, in tests.
- No proprietary content: no real strategy parameters, no API keys, no
  exchange credentials, no private journal contents. This repo is public
  — see `docs/private-repo-guide.md` for where that content belongs
  instead.
- Every module implementing a plugin protocol should state which
  protocol it implements in its module docstring.

## Good first issues

- Verify one of the `TODO(verify)` adapters (`elfa`, `nansen`,
  `cryptoquant`) against a real captured response and implement `fetch`
  for real.
- Add a `nautilus_trader`-backed `BacktestEngine` implementation
  alongside the default vectorbt one (the protocol in
  `alphaloop/backtest/base.py` is engine-agnostic by design).
- Add a screen-based universe resolver (`ScreenUniverse` in
  `alphaloop/core/spec.py` is defined but `alphaloop.core.loop` doesn't
  resolve it yet — see the `NotImplementedError` there).
- Add a Kraken or Bybit executor alongside Binance/Hyperliquid, following
  the shared `Executor` protocol in `alphaloop/execute/base.py`.
- Improve the signal mini-language (`alphaloop/backtest/signals.py`) —
  e.g. add a whitelisted `crossover`/`crossunder` helper so strategies
  don't have to hand-roll it from `shift`/comparisons.

## Pull requests

- One logical change per PR. If you're touching both an adapter and the
  resolver, explain why in the PR description.
- Add tests for new behavior — a plugin without a test showing it
  actually satisfies its protocol isn't done.
- Run `pytest` and `mypy alphaloop` locally before opening the PR; CI
  runs both plus `ruff check`.
