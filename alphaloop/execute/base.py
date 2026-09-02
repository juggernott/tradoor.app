"""The Executor protocol and its shared order/portfolio types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    reduce_only: bool = False
    client_order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    exchange_order_id: str | None = None
    error: str | None = None


@dataclass
class Position:
    symbol: str
    qty: float  # signed: positive long, negative short
    entry_price: float | None = None


@dataclass
class Portfolio:
    """Venue-truth positions and balances — always re-fetched, never assumed."""

    positions: dict[str, Position] = field(default_factory=dict)
    equity: float = 0.0
    cash: float = 0.0


class ExecutorError(RuntimeError):
    pass


class InsufficientPrecisionError(ExecutorError):
    """Raised when an order can't be rounded to the venue's tick/lot size."""


@runtime_checkable
class Executor(Protocol):
    """Places/manages orders at one venue. Implementations must be idempotent:

    calling ``reconcile`` twice in a row with the same ``target_weights``
    and no market movement should not double-submit orders.
    """

    name: str

    def fetch_portfolio(self) -> Portfolio:
        """Venue-truth positions/balances. Never trust local state alone."""
        ...

    def reconcile(
        self, target_weights: dict[str, float], portfolio: Portfolio, equity: float
    ) -> list[Order]:
        """Compute (and submit) the minimal order set to reach target_weights."""
        ...

    def cancel_all(self) -> None: ...

    def flatten_all(self) -> list[Order]:
        """Close every open position immediately, cancel all open orders."""
        ...
