"""The shared execution runner: one reconciliation loop for every executor.

Ties together target-weight computation (from a spec's current signal),
the venue-truth :class:`~alphaloop.execute.base.Executor`, persisted
:class:`~alphaloop.execute.state.RunnerState`, the risk layer's kill-switch
(:func:`alphaloop.risk.limits.drawdown_breach`), and alerting
(:mod:`alphaloop.execute.notify`). Both paper and live executors run
through this same loop — there is no separate "live runner".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alphaloop.core.spec import RiskLimits
from alphaloop.execute.base import Executor, Order
from alphaloop.execute.notify import Notifier, StdoutNotifier
from alphaloop.execute.state import RunnerState


class HaltedError(RuntimeError):
    """Raised when a tick is attempted on a halted runner without --ack."""


@dataclass
class TickResult:
    orders: list[Order]
    equity: float
    halted: bool


class Runner:
    """One instance per (spec, venue) live/paper run.

    Args:
        run_id: stable id for this run — used for the state file name and
            surfaced in every notification/journal entry.
        state_path: defaults to ``state/<run_id>.json``.
        dry_run: when True, computes and logs the order set a tick would
            submit, but never calls ``executor.reconcile`` — a rehearsal
            before flipping to ``--live``.
    """

    def __init__(
        self,
        run_id: str,
        venue: str,
        spec_content_hash: str,
        executor: Executor,
        risk: RiskLimits,
        state_path: str | Path | None = None,
        notifier: Notifier | None = None,
        dry_run: bool = False,
    ) -> None:
        self.run_id = run_id
        self.executor = executor
        self.risk = risk
        self.notifier = notifier or StdoutNotifier()
        self.dry_run = dry_run
        self.state_path = Path(state_path) if state_path else Path("state") / f"{run_id}.json"
        self.state = RunnerState.load_or_create(self.state_path, run_id, venue, spec_content_hash)

    def tick(self, target_weights: dict[str, float]) -> TickResult:
        if self.state.halted:
            raise HaltedError(
                f"runner {self.run_id!r} is halted ({self.state.halt_reason}). "
                f"Run `alphaloop resume {self.run_id} --ack` to clear it."
            )

        portfolio = self.executor.fetch_portfolio()
        equity = portfolio.equity
        self.state.peak_equity = max(self.state.peak_equity, equity)

        drawdown = (
            0.0
            if self.state.peak_equity <= 0
            else (equity - self.state.peak_equity) / self.state.peak_equity
        )
        if drawdown <= -self.risk.drawdown_halt_pct:
            self._trip_kill_switch(
                f"drawdown {drawdown:.2%} breached limit {self.risk.drawdown_halt_pct:.2%}"
            )
            return TickResult(orders=[], equity=equity, halted=True)

        if self.dry_run:
            self.notifier.notify(
                "info",
                f"[dry-run] would reconcile to {target_weights} (current equity {equity:.2f})",
            )
            return TickResult(orders=[], equity=equity, halted=False)

        orders = self.executor.reconcile(target_weights, portfolio, equity)
        self.state.last_reconciled_weights = target_weights
        self.state.save(self.state_path)
        return TickResult(orders=orders, equity=equity, halted=False)

    def _trip_kill_switch(self, reason: str) -> None:
        self.notifier.notify("halt", f"KILL-SWITCH TRIPPED: {reason}. Flattening and halting.")
        self.executor.flatten_all()
        self.state.halted = True
        self.state.halt_reason = reason
        self.state.save(self.state_path)

    def resume(self, ack: bool) -> None:
        if not ack:
            raise HaltedError("resume requires ack=True (alphaloop resume <run-id> --ack)")
        self.state.halted = False
        self.state.halt_reason = None
        self.state.save(self.state_path)
        self.notifier.notify("info", f"runner {self.run_id!r} resumed")

    def flatten(self) -> list[Order]:
        orders = self.executor.flatten_all()
        self.notifier.notify("warning", f"manual flatten: {len(orders)} orders")
        return orders
