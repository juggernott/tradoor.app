"""Execution: target-weight reconciliation, order lifecycle, persisted runner state.

Paper (:mod:`alphaloop.execute.paper`) is the default. Binance
(:mod:`alphaloop.execute.binance_ccxt`) and Hyperliquid
(:mod:`alphaloop.execute.hyperliquid`) are both production-usable live
executors sharing one runner (:mod:`alphaloop.execute.runner`) for
reconciliation, order lifecycle, persisted state, and the kill-switch.
"""
