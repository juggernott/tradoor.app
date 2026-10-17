# Tradoor web foundation

An independent, inspectable first increment toward the requested Quandora-style platform. This is **not a complete clone or a production trading platform**.

## Run and test

Requires Node 20+ for tests and Python 3 for the local static server. No npm packages are required.

```sh
npm test
npm start
```

Open http://127.0.0.1:4173. All workspace data persists only in the current browser's local storage. Export your workspace before changing browser or origin. The hosted preview has its own separate storage.

## Implemented

- Responsive dashboard, baseline factor research, backtest history, data library and readiness screens.
- Deterministic synthetic sample labelled as synthetic throughout.
- Validated consecutive daily crypto CSV import: date,symbol,close; balanced universe, duplicate detection, positive finite prices, calendar validation.
- Momentum and reversal cross-sectional daily portfolios, 50% long and 50% short before costs.
- Quantity-based mark-to-market PnL with initial and rebalance turnover fees and slippage.
- Net equity curve, total return, peak-to-trough drawdown and daily Sharpe (365 days, zero risk-free rate).
- Historical paper replay, positions, fill ledger, terminal stop, data and result exports.
- Nine deterministic tests covering future-data independence, portfolio weights, entry costs, replay equivalence, invalid inputs and drawdown.

## Simulation assumptions

Signals use the current daily close and assume execution at that same close; returns accrue on the next close. This is optimistic and not a realistic venue fill model. There is no funding, borrow, margin, liquidation, market-impact, survivorship correction, walk-forward or multiple-testing adjustment. Initial and daily rebalance costs are charged; terminal holdings are marked, not liquidated. Paper is manual historical replay, not real-time paper trading. It stops at the dataset boundary and does not run after closing the browser.

## Existing repository integration

The existing public repository https://github.com/juggernott/tradoor.app contains Alphaloop, a Python research/execution engine with validation and exchange adapters. This web foundation should live under `web/` alongside it. It does not replace or invoke that Python engine yet. Existing exchange adapters are unverified in this session and are not reachable from the preview.

## Access findings (17 October 2026)

- Signed-in Quandora screens inspected: factor library and system folders; strategy library; strategy analytics with NAV, drawdown, exposure, style diagnostics, trades and positions; paper trading list.
- Quandora public plugin is an authenticated remote integration, not the private platform backend. Its source https://github.com/varsity-tech-product/quandora-plugins describes Factor Mining -> Factor Analysis -> Strategy Building -> Strategy Analysis -> simulated Paper Trading.
- No private factor code, account balances or research records are copied into this deliverable. No Quandora mutations or order actions were performed.
- tradoor.app NS resolves to dns1.registrar-servers.com and dns2.registrar-servers.com; apex A resolved to 15.235.180.2. Registrar access and current hosting ownership remain unverified.
- Vercel connector discovery returned reauthentication required. No matching hosting project could be verified.

## Remaining production work and access needed

1. Confirm registrar/current host for tradoor.app; reconnect Vercel if it is the intended host. Preserve the existing site until deployment ownership is verified.
2. Choose deployment architecture: authenticated web/API, managed Postgres, object storage, job queue, always-on execution workers, central logs and alerts. The Python worker must remain separate from this static preview.
3. Connect the Alphaloop engine through bounded authenticated API jobs, with ownership enforcement and immutable dataset/config/run identities. Add server-persisted histories, worker retry/idempotency, result pagination, export integrity and per-user isolation.
4. Build the observed factor lifecycle: folders, favorites, compare, grades, mine/import, validation, versioning, research memory. Source-free official factors cannot be reconstructed from summary evidence alone.
5. Add multi-factor composition, run history, cost/funding attribution, out-of-sample validation and six diagnostic charts from real engine evidence.
6. Select licensed point-in-time market data, venue/universe, bar frequency, history range and funding/borrow inputs. Do not use the synthetic sample to make financial claims.
7. Continuous paper: server-side live feed, persisted cash/positions/fills/funding, freshness checks, worker restart recovery and reconciled accounting. Historical replay is not a substitute.
8. Select first venue (existing candidates Binance or Hyperliquid), testnet account and scoped credentials entered through a secure secret store. No withdrawal permissions. Specify maximum capital, gross/net exposure, per-asset/order limits, daily loss and drawdown stops.
9. Audit existing execution adapters and runner; verify open/scale/reduce/flatten, partial fills, venue precision/minimums, retry deduplication, stale market data, crash recovery, cancellation and emergency stop before live activation.
10. Authentication, tenant tests, encrypted keys with rotation, user consent, monitoring, backups and operator recovery need implementation before public production use.

No credentials should be pasted into chat or committed. Deployment of this preview does not enable any real-money trading.
