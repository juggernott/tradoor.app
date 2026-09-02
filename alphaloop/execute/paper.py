"""Paper executor: simulated fills against live ccxt prices, no real orders.

Default executor (project principle #5: paper is the default; live
requires ``--live`` + config ack). Suitable for a long-lived always-on
process — state is persisted the same way live executors are.
"""

from __future__ import annotations

import ccxt

from alphaloop.execute.base import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
)
from alphaloop.execute.notify import Notifier, StdoutNotifier


class PaperExecutor:
    name = "paper"

    def __init__(
        self,
        exchange_id: str = "binance",
        starting_cash: float = 10_000.0,
        fee_bps: float = 7.5,
        exchange: ccxt.Exchange | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._exchange = exchange or getattr(ccxt, exchange_id)({"enableRateLimit": True})
        self.fee_bps = fee_bps
        self.notifier = notifier or StdoutNotifier()
        self._positions: dict[str, Position] = {}
        self._cash = starting_cash

    def _mark_price(self, symbol: str) -> float:
        ticker = self._exchange.fetch_ticker(symbol)
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise RuntimeError(f"could not fetch a mark price for {symbol}")
        return float(price)

    def fetch_portfolio(self) -> Portfolio:
        equity = self._cash
        for symbol, pos in self._positions.items():
            equity += pos.qty * self._mark_price(symbol)
        return Portfolio(positions=dict(self._positions), equity=equity, cash=self._cash)

    def reconcile(
        self, target_weights: dict[str, float], portfolio: Portfolio, equity: float
    ) -> list[Order]:
        orders = []
        for symbol, target_w in target_weights.items():
            price = self._mark_price(symbol)
            target_qty = (target_w * equity) / price
            current_qty = self._positions.get(symbol, Position(symbol, 0.0)).qty
            delta = target_qty - current_qty
            if abs(delta * price) < 1e-8:
                continue

            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            order = Order(symbol=symbol, side=side, qty=abs(delta), order_type=OrderType.MARKET)
            fee = abs(delta) * price * (self.fee_bps / 10_000)
            self._cash -= delta * price + fee
            new_qty = current_qty + delta
            self._positions[symbol] = Position(symbol, new_qty, entry_price=price)
            order.status = OrderStatus.FILLED
            order.filled_qty = order.qty
            order.avg_fill_price = price
            orders.append(order)
            self.notifier.notify(
                "info",
                f"[paper] {side.value} {abs(delta):.6f} {symbol} @ {price:.2f} (fee {fee:.4f})",
            )
        return orders

    def cancel_all(self) -> None:
        pass  # paper orders fill immediately; nothing stays open

    def flatten_all(self) -> list[Order]:
        return self.reconcile(
            {s: 0.0 for s in self._positions}, self.fetch_portfolio(), self.fetch_portfolio().equity
        )
