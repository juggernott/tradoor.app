"""Binance executor (spot + USD-M perps) via ccxt.

Live requires ``--live`` at the CLI layer (:mod:`alphaloop.core.confirm`);
this class itself has no such gate — the CLI is what decides whether the
underlying ccxt exchange is constructed against mainnet or testnet.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

import ccxt

from alphaloop.execute.base import (
    ExecutorError,
    InsufficientPrecisionError,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
)
from alphaloop.execute.notify import Notifier, StdoutNotifier

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 2.0
_T = TypeVar("_T")


class BinanceExecutor:
    name = "binance"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = True,
        market_type: str = "swap",  # 'spot' or 'swap' (USD-M perps)
        leverage: int = 1,
        notifier: Notifier | None = None,
        exchange: ccxt.Exchange | None = None,
    ) -> None:
        self.testnet = testnet
        self.notifier = notifier or StdoutNotifier()
        self._exchange = exchange or self._build_exchange(api_key, api_secret, testnet, market_type)
        self._leverage = leverage
        self._leverage_set: set[str] = set()

    def _build_exchange(
        self, api_key: str | None, api_secret: str | None, testnet: bool, market_type: str
    ) -> ccxt.Exchange:
        ex = ccxt.binance(
            {
                "apiKey": api_key or os.environ.get("ALPHALOOP_BINANCE_API_KEY"),
                "secret": api_secret or os.environ.get("ALPHALOOP_BINANCE_API_SECRET"),
                "enableRateLimit": True,
                "options": {"defaultType": market_type},
            }
        )
        if testnet:
            ex.set_sandbox_mode(True)
        return ex

    def _ensure_leverage(self, symbol: str) -> None:
        if symbol in self._leverage_set:
            return
        with contextlib.suppress(ccxt.NotSupported):  # spot market_type has no leverage concept
            self._exchange.set_leverage(self._leverage, symbol)
        self._leverage_set.add(symbol)

    def fetch_portfolio(self) -> Portfolio:
        balance = self._retry(self._exchange.fetch_balance)
        positions_raw = []
        if self._exchange.options.get("defaultType") == "swap":
            positions_raw = self._retry(self._exchange.fetch_positions)

        positions: dict[str, Position] = {}
        for p in positions_raw:
            contracts = float(p.get("contracts") or 0)
            if contracts == 0:
                continue
            side_sign = 1 if p.get("side") == "long" else -1
            positions[p["symbol"]] = Position(
                symbol=p["symbol"], qty=side_sign * contracts, entry_price=p.get("entryPrice")
            )

        equity = float(balance.get("total", {}).get("USDT", 0) or 0)
        cash = float(balance.get("free", {}).get("USDT", 0) or 0)
        return Portfolio(positions=positions, equity=equity, cash=cash)

    def reconcile(
        self, target_weights: dict[str, float], portfolio: Portfolio, equity: float
    ) -> list[Order]:
        orders = []
        for symbol, target_w in target_weights.items():
            self._ensure_leverage(symbol)
            ticker = self._retry(self._exchange.fetch_ticker, symbol)
            price = float(ticker["last"])
            target_qty = (target_w * equity) / price

            current = portfolio.positions.get(symbol)
            current_qty = current.qty if current else 0.0
            delta = target_qty - current_qty
            if abs(delta * price) < self._min_notional(symbol):
                continue

            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            reduce_only = self._is_reducing(current_qty, delta)
            order = self._submit_market_order(symbol, side, abs(delta), reduce_only=reduce_only)
            orders.append(order)
        return orders

    def _is_reducing(self, current_qty: float, delta: float) -> bool:
        if current_qty == 0:
            return False
        return (current_qty > 0 and delta < 0 and abs(delta) <= current_qty) or (
            current_qty < 0 and delta > 0 and abs(delta) <= abs(current_qty)
        )

    def _min_notional(self, symbol: str) -> float:
        try:
            market = self._exchange.market(symbol)
            return float(market.get("limits", {}).get("cost", {}).get("min") or 5.0)
        except Exception:  # noqa: BLE001
            return 5.0

    def _round_amount(self, symbol: str, qty: float) -> float:
        try:
            return float(self._exchange.amount_to_precision(symbol, qty))
        except Exception as e:  # noqa: BLE001
            raise InsufficientPrecisionError(f"could not round {qty} for {symbol}: {e}") from e

    def _submit_market_order(
        self, symbol: str, side: OrderSide, qty: float, reduce_only: bool
    ) -> Order:
        rounded = self._round_amount(symbol, qty)
        order = Order(
            symbol=symbol,
            side=side,
            qty=rounded,
            order_type=OrderType.MARKET,
            reduce_only=reduce_only,
        )
        params = {"reduceOnly": reduce_only} if reduce_only else {}

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                raw = self._exchange.create_order(
                    symbol, "market", side.value, rounded, None, params
                )
                order.exchange_order_id = str(raw.get("id"))
                order.status = OrderStatus.FILLED
                order.filled_qty = float(raw.get("filled") or rounded)
                order.avg_fill_price = float(raw.get("average") or 0) or None
                self.notifier.notify("info", f"filled {side.value} {rounded} {symbol}")
                return order
            except ccxt.InsufficientFunds as e:
                order.status = OrderStatus.REJECTED
                order.error = str(e)
                self.notifier.notify("error", f"order rejected (insufficient funds): {symbol} {e}")
                return order
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                if attempt == _MAX_RETRIES:
                    order.status = OrderStatus.TIMED_OUT
                    order.error = str(e)
                    self.notifier.notify(
                        "error", f"order timed out after {_MAX_RETRIES} attempts: {symbol} {e}"
                    )
                    return order
                time.sleep(_RETRY_BACKOFF_S * attempt)
        raise ExecutorError("unreachable")  # pragma: no cover

    def _retry(self, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                last_exc = e
                time.sleep(_RETRY_BACKOFF_S * attempt)
        raise ExecutorError(f"exceeded retries calling {fn}: {last_exc}") from last_exc

    def cancel_all(self) -> None:
        for symbol in {o["symbol"] for o in self._retry(self._exchange.fetch_open_orders)}:
            self._retry(self._exchange.cancel_all_orders, symbol)

    def flatten_all(self) -> list[Order]:
        self.cancel_all()
        portfolio = self.fetch_portfolio()
        return self.reconcile({s: 0.0 for s in portfolio.positions}, portfolio, portfolio.equity)
