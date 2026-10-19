# Tradoor Python workspace and Alphacore v12 integration

## Status — 19 October 2026

The same-origin dashboard uses FastAPI, SQLite and an independent Python worker. The private Alphacore v12 research library is connected and verified locally. Private source was accessed through an authenticated file share, reviewed, and copied to a private runtime snapshot outside this public repository. Neither private source nor credentials are distributed here.

The tested identity is `alphacore-v12@839604801b26`. The adapter hashes eight library files and records their identities in results. A queued job and a paper account pin their engine version; changing it requires a new compatible run.

## Run locally

```sh
python -m venv .venv
# Activate the virtual environment.
python -m pip install -e '.[web,v12]'
# Set TRADOOR_ALPHACORE_ROOT to your private v12 source root.
python -m alphaloop.web.api --local
```

In a second terminal with the same environment and working directory:

```sh
python -m alphaloop.web.worker
```

Open http://127.0.0.1:4173. Both processes must share `TRADOOR_DB` (default `state/tradoor.sqlite3`). An ignored `state/engine.json` containing `{"source_root":"/private/path/to/alphacore-v12"}` is an alternative to the source-root environment variable. The default factory is `alphaloop.web.alphacore_v12:create_engine`; `TRADOOR_ENGINE_FACTORY` optionally selects an operator-installed adapter. API callers cannot choose imports or executable code.

The source root must contain `research/lib/{__init__,backtest,validation,datasource,eda,factor,normalisers,signals}.py`. The reviewed dependency versions and source identity must be checked when upgrading. Missing source/dependencies disables research with an explicit error, without a legacy fallback.

Local mode is a single trusted-machine workspace, bound to loopback. External mode requires HTTPS, `TRADOOR_HOST`, and a securely configured 32+ character `TRADOOR_ADMIN_TOKEN`. It uses hashed owner sessions and Secure HttpOnly SameSite cookies; it is not multi-tenant identity. Public deployment and the tradoor.app domain cutover remain pending.

## Actual v12 scope

The adapter calls the private library's `factor.rate_of_change` and `validation.backtest_v2`. Tradoor ranks the scaled signals, chooses equal long/short sleeves, and sums their daily return contributions. Momentum and sign-reversed reversal are baseline controls, not the private production strategy roster, HMM or HRP allocator. Custom factor authoring remains future work.

Backtests require at least 500 consecutive daily dates and two assets, with balanced panels, finite positive prices and no duplicate rows. Configured fees and slippage apply to turnover. A one-bar signal shift precedes close-to-close returns. Annualization is 365 days; the 70/30 chronological split is descriptive rather than a promotion verdict. Funding, borrow, margin, liquidation, next-open fills and selection-adjusted grades are absent. Capital is in the dataset's quote units; no USD conversion is performed.

Forward targets use the same v12 factor and ranking logic on common closed daily candles. The worker polls public Binance/Kraken prices at least 15 seconds apart and rebalances once per closed signal candle. It enforces gross exposure <=1, each position <=50%, and absolute net <=1%. Shorts are synthetic. The existing Python PaperExecutor provides simulated cash/quantity accounting only; it is not the research engine.

## Persistence and controls

SQLite WAL stores immutable dataset hashes, leased research jobs, results, sessions, paper cash/positions, fills, signal deduplication and equity observations. A stale job claim cannot overwrite a newer lease. Paper commits check account revision so a pause during a market fetch cannot commit stale fills. One frozen, validated mark snapshot is used per accounting tick. Missing, stale or future marks produce an unavailable-data state without invented fills.

Pause and stop freeze processing without liquidation. Terminal stopped/halted runs cannot resume. Peak-equity drawdown halts flatten simulated positions at validated marks. The API returns the latest 200 fills and 1,000 equity points; full-history export and retention controls remain future work.

The worker resumes persisted cash and positions on restart and runs independently of the browser. It only processes while its process and host remain awake. A supervised service with persistent disk is needed for deployment; the current verified run is on the development laptop, not on the Mac mini or tradoor.app. Real exchange orders and credentials are not exposed by this backend.

## Verification

```sh
python -m pytest tests/test_web_backend.py tests/test_web_market.py tests/test_web_v12.py tests/test_execute.py tests/test_risk.py -q
node --check web/dist/backend.js
```

28 targeted tests passed, including four tests against the actual configured private v12 library. They check v12 kernel invocation, shifted returns and costs, independence from future prices, matching historical/forward targets, and minimum history. The private-library tests skip on installations without a configured private source; test doubles separately cover worker persistence, deduplication, drawdown flattening, stale prices, pause races, job lease recovery, authentication and dataset validation.

Browser verification imported 600 closed daily BTC/USDT and ETH/USDT bars from Binance, queued and completed a v12 backend backtest, then started one continuous paper account. The worker recorded two simulated fills, 70 USDT in initial fees/slippage, persisted positions, and fresh equity observations. This verifies operation, not strategy profitability. The tested baseline lost approximately 21.27% in the historical sample.

## Quandora source availability

The public https://github.com/varsity-tech-product/quandora-plugins repository is Apache-2.0 licensed and contains the agent integration, skills and documentation. Those integrations call authenticated remote services. It does not supply the hosted app/backend source. We have not found public source for its server research/backtest engines, data pipelines, accounts/storage or hosted execution infrastructure. Those parts are not accessible to this session as reusable source; calling the API does not grant the implementation. Official factor results may be accessible without source. User-owned exported factor code is distinct from Quandora's platform code.

This is a statement of verified access and publication evidence, not a claim that every unpublished component has a particular legal license.

