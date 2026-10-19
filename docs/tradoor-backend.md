# Tradoor Python workspace and Alphacore v12 integration

## Current status — 19 October 2026

The dashboard now talks to a same-origin FastAPI server rather than computing results in the browser. A separate Python worker consumes persisted research jobs and processes continuous simulated accounts. The selected production research engine is **Alphacore v12**, as requested. Its source has not yet been inspected: it is on the Mac mini, and the available Windows SSH key is rejected by the Mac account. There is no fallback to Alphaloop, v4, a fake engine, or the old browser simulator.

Consequently, **actual v12 backend backtests and continuous strategy paper runs are not yet enabled or verified**. The API returns 503 and the dashboard disables their creation until a private v12 adapter is installed. Infrastructure tests inject a test-only engine. Test results must not be described as v12 research results.

## Run locally

From the repository root, in two terminals:

```sh
python -m venv .venv
# Activate .venv using your operating system's activation command.
python -m pip install -e '.[web]'
python -m alphaloop.web.api --local
```

```sh
# Activate the same environment in the second terminal.
python -m alphaloop.web.worker
```

Open http://127.0.0.1:4173. Both processes must use the same working directory, or set `TRADOOR_DB` to the same absolute SQLite file. Default: `state/tradoor.sqlite3`, excluded from Git. Local mode binds only to loopback and rejects non-loopback clients and unexpected hosts. Local mode is a single trusted-machine development workspace, not multi-user authentication.

The worker runs independently of the browser, retries failed market requests, writes a heartbeat, and resumes running accounts from persisted cash and positions after restart. It only runs while its process and host are awake. Closing a tool session, rebooting the machine, or terminating the worker stops processing until it is started again. For deployment, manage these processes with a service supervisor and persistent disk; that deployment is still pending.

## Connect the private v12 engine

Keep v12 source, strategies, settings, data and keys outside this public repository. Install its dependencies in the server/worker environment. Implement an adapter **after inspecting v12's actual functions** and configure both processes:

```text
TRADOOR_ENGINE_FACTORY=your_private_v12_adapter:create_engine
```

This value is operator configuration. API callers cannot choose arbitrary Python modules, paths, expressions or code to execute.

The factory returns an object with:

- `name`: a stable engine/version label, for example `alphacore-v12@<source revision>`.
- `backtest(csv, config, identifier, source) -> dict`: translates the bounded request into v12's backtest contract and returns real engine evidence. No subprocess command or shell string should be derived from requests.
- `weights(frame, config, frequency) -> dict[str,float]`: calls v12's forward signal/portfolio logic on validated common closed candles. All requested exchange symbols must be present in the returned target weights. The web worker enforces gross <= 1x, each absolute target <= 50%, and absolute net <= 1%.

Config is currently bounded to name, momentum/reversal mode, capital, lookback, selection, feeBps and slippageBps. Expand the schema to v12's actual strategy model after source review rather than guessing that v12 implements these baseline modes.

Backtest result contract:

```text
id: exact requested identifier
engine: exact adapter name
name: strategy name
status: completed
config: exact immutable request configuration
equity: final equity in USD
curve: nonempty list of {date: ISO timestamp, equity: finite USD number}
metrics: {totalReturn: fraction, maxDrawdown: fraction, sharpe: number or null}
weights: optional retained weight records
trades: optional retained trade records
assumptions: explicit execution, fees, funding and validation methodology
```

The worker adds the immutable dataset ID. Do not create a paper run from a result whose underlying engine/configuration differs from the configured forward engine.

## Implemented infrastructure

- FastAPI health, same-origin dashboard, bounded dataset uploads and validation, immutable IDs and SHA-256 dataset hashes.
- SQLite WAL storage for datasets, jobs, results, sessions, paper accounts, fills, signal deduplication and equity observations.
- Research jobs claimed transactionally with a ten-minute recovery lease. A stale worker cannot overwrite the result after another claim.
- Separate worker process with heartbeat and five-second scheduling loop; each active paper account is checked no more often than every 15 seconds.
- Public CCXT market reads for Binance and Kraken. No exchange account credentials or real-order client is configured. Current UI forward mode is daily to match daily dataset/backtest inputs.
- Closed daily candle signals, complete common universe/history, positive finite mark validation, and stale/future quote rejection.
- Simulated quantity/cash reconciliation through the existing Python `PaperExecutor`, using one frozen price snapshot per tick. This executor is accounting infrastructure, not a substitute for the selected v12 research engine.
- Atomic cash/position/fill/equity commits and one-rebalance-per-signal-candle deduplication. Revision checks prevent an API pause or stop during a market fetch from committing stale fills.
- Pause/resume/terminal stop, and a peak-equity drawdown halt that flattens simulated positions.
- Dashboard shows API/engine/worker state, persistent datasets/jobs/results, paper controls, positions, equity and recent fills.
- Owner-token login for external mode, HttpOnly Secure SameSite cookie sessions, same-origin writes, host checks and logout invalidation. External mode requires HTTPS and a 32+ character `TRADOOR_ADMIN_TOKEN` configured securely; also set `TRADOOR_HOST` to the real hostname. This is single-owner access, not full multi-tenant identity.

## Simulation limits

Paper fills are local synthetic orders at observed public marks. Shorts are simulated; funding, borrow, margin, liquidation, venue precision, order-book fills and market impact are not modeled. This is neither live execution nor a testnet order service. A separate venue-certified lifecycle is required before real trading.

Pause and stop freeze processing without liquidating positions. Terminal stopped/halted runs cannot resume. Drawdown halts flatten at validated marks. The API returns the most recent 200 fills and 1,000 equity points; underlying records persist in SQLite. Full-history export and retention management remain future work.

Heartbeat online status is an operational signal, not proof that a run has fresh prices. A market error leaves the prior positions/equity intact and reports unavailable data and an error. Missing prices never become invented fills. Scheduling uses poll time, so quote/fill timestamps are not deterministic historical replay timestamps.

## Verification completed

```sh
python -m pytest tests/test_web_backend.py tests/test_web_market.py tests/test_execute.py tests/test_risk.py -q
node --check web/dist/backend.js
```

24 tests passed, including auth/session invalidation, dataset validation, engine-unavailable behavior, persisted jobs, expired-claim recovery, restored simulated cash/positions, once-per-candle fills, pause-during-fetch, stale/future prices, closed candles, risk flattening and terminal stop. Infrastructure tests use a test-only injected engine; they do not validate v12.

A real read-only Binance snapshot for BTC/USDT and ETH/USDT succeeded and returned a latest closed daily candle at 2026-10-18T00:00:00Z. No paper or real account was started on the Mac and no exchange orders were placed.

Browser QA verified the API-connected dashboard, server-side synthetic dataset creation, persisted dataset identity/hash, and explicit v12-unavailable status.

## Mac access blocker

The private engine host is reachable, but SSH authentication with the available development-machine key is rejected. The public key was provided separately for one-time authorization; no private key or password was requested. No security setting or authorized key on the engine host was changed by this session. Private network addresses and account access details are intentionally excluded from this public repository.

Once authenticated access is available, locate the v12 repository on its host, read its applicable instructions, identify the actual backtest/data/forward interfaces and dependencies, implement the adapter privately, and run real v12 integration tests before enabling research and continuous strategy paper runs.

## Quandora source availability

The public https://github.com/varsity-tech-product/quandora-plugins repository is Apache-2.0 licensed and contains the agent integration, skills and documentation. Those integrations call authenticated remote services. It does not supply the hosted app/backend source. We have not found public source for its server research/backtest engines, data pipelines, accounts/storage or hosted execution infrastructure. Those parts are not accessible to this session as reusable source; calling the API does not grant the implementation. Official factor results may be accessible without source. User-owned exported factor code is distinct from Quandora's platform code.

This is a statement of verified access and publication evidence, not a claim that every unpublished component has a particular legal license.

