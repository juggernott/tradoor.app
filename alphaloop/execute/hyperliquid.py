"""Hyperliquid executor (perps) via the official ``hyperliquid-python-sdk``.

Records the trading address in every journal entry (see the CLI's paper/
trade commands) so fills are onchain-verifiable — Hyperliquid's fills are
public on-chain state, unlike a CEX.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from alphaloop.execute.base import (
    ExecutorError,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
)
from alphaloop.execute.notify import Notifier, StdoutNotifier

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 2.0
_DEFAULT_SLIPPAGE = 0.02
_T = TypeVar("_T")


class HyperliquidExecutor:
    name = "hyperliquid"

    def __init__(
        self,
        private_key: str | None = None,
        testnet: bool = True,
        leverage: int = 1,
        notifier: Notifier | None = None,
        exchange: Exchange | None = None,
        info: Info | None = None,
    ) -> None:
        self.testnet = testnet
        self.notifier = notifier or StdoutNotifier()
        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL

        pk = private_key or os.environ.get("ALPHALOOP_HYPERLIQUID_PRIVATE_KEY")
        if not pk and exchange is None:
            raise ExecutorError(
                "hyperliquid executor requires a private key: set "
                "ALPHALOOP_HYPERLIQUID_PRIVATE_KEY or pass private_key= explicitly."
            )
        wallet = Account.from_key(pk) if pk else None
        self.address = wallet.address if wallet else None

        self._exchange = exchange or Exchange(wallet, base_url=base_url)
        self._info = info or Info(base_url=base_url, skip_ws=True)
        self._leverage = leverage
        self._leverage_set: set[str] = set()

    def _ensure_leverage(self, coin: str) -> None:
        if coin in self._leverage_set:
            return
        self._retry(self._exchange.update_leverage, self._leverage, coin, True)
        self._leverage_set.add(coin)

    def fetch_portfolio(self) -> Portfolio:
        state = self._retry(self._info.user_state, self.address)
        positions: dict[str, Position] = {}
        for entry in state.get("assetPositions", []):
            pos = entry["position"]
            qty = float(pos["szi"])
            if qty == 0:
                continue
            coin = pos["coin"]
            positions[coin] = Position(
                symbol=coin, qty=qty, entry_price=float(pos.get("entryPx") or 0) or None
            )

        margin_summary = state.get("marginSummary", {})
        equity = float(margin_summary.get("accountValue", 0) or 0)
        cash = float(margin_summary.get("totalRawUsd", 0) or 0)
        return Portfolio(positions=positions, equity=equity, cash=cash)

    def reconcile(
        self, target_weights: dict[str, float], portfolio: Portfolio, equity: float
    ) -> list[Order]:
        orders = []
        mids = self._retry(self._info.all_mids)
        for coin, target_w in target_weights.items():
            self._ensure_leverage(coin)
            price = float(mids[coin])
            target_qty = (target_w * equity) / price

            current = portfolio.positions.get(coin)
            current_qty = current.qty if current else 0.0
            delta = target_qty - current_qty
            if abs(delta * price) < 10.0:  # Hyperliquid's practical min order size floor
                continue

            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            order = self._submit_market_order(coin, side, abs(delta), price)
            orders.append(order)
        return orders

    def _submit_market_order(
        self, coin: str, side: OrderSide, qty: float, ref_price: float
    ) -> Order:
        order = Order(symbol=coin, side=side, qty=qty, order_type=OrderType.MARKET)
        is_buy = side == OrderSide.BUY

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._exchange.market_open(coin, is_buy, qty, None, _DEFAULT_SLIPPAGE)
                status = resp.get("status")
                if status != "ok":
                    order.status = OrderStatus.REJECTED
                    order.error = str(resp)
                    self.notifier.notify("error", f"hyperliquid order rejected: {coin} {resp}")
                    return order

                statuses = resp["response"]["data"]["statuses"]
                fill_statuses = [s for s in statuses if "filled" in s]
                if fill_statuses:
                    filled = fill_statuses[0]["filled"]
                    order.status = OrderStatus.FILLED
                    order.filled_qty = float(filled["totalSz"])
                    order.avg_fill_price = float(filled["avgPx"])
                    order.exchange_order_id = str(filled.get("oid"))
                else:
                    order.status = OrderStatus.OPEN
                self.notifier.notify(
                    "info", f"hyperliquid {side.value} {qty} {coin}: {order.status.value}"
                )
                return order
            except (ConnectionError, TimeoutError) as e:
                if attempt == _MAX_RETRIES:
                    order.status = OrderStatus.TIMED_OUT
                    order.error = str(e)
                    self.notifier.notify("error", f"hyperliquid order timed out: {coin} {e}")
                    return order
                time.sleep(_RETRY_BACKOFF_S * attempt)
        raise ExecutorError("unreachable")  # pragma: no cover

    def _retry(self, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except (ConnectionError, TimeoutError) as e:
                last_exc = e
                time.sleep(_RETRY_BACKOFF_S * attempt)
        raise ExecutorError(f"exceeded retries calling {fn}: {last_exc}") from last_exc

    def cancel_all(self) -> None:
        open_orders = self._retry(self._info.open_orders, self.address)
        cancels = [{"coin": o["coin"], "oid": o["oid"]} for o in open_orders]
        if cancels:
            self._retry(self._exchange.bulk_cancel, cancels)

    def flatten_all(self) -> list[Order]:
        self.cancel_all()
        portfolio = self.fetch_portfolio()
        orders = []
        for coin in portfolio.positions:
            resp = self._exchange.market_close(coin)
            order = Order(
                symbol=coin,
                side=OrderSide.SELL if portfolio.positions[coin].qty > 0 else OrderSide.BUY,
                qty=abs(portfolio.positions[coin].qty),
                order_type=OrderType.MARKET,
            )
            order.status = (
                OrderStatus.FILLED if resp.get("status") == "ok" else OrderStatus.REJECTED
            )
            orders.append(order)
            self.notifier.notify("info", f"flattened {coin}")
        return orders
