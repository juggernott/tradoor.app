"""Independent backtest job and continuous simulation process.

Run with python -m alphaloop.web.worker. The browser is not the scheduler.
Only the existing PaperExecutor is exposed; no real execution adapter is loaded.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import logging
import math
import os
import signal
import time

from alphaloop.execute.base import Position
from alphaloop.execute.paper import PaperExecutor
from alphaloop.web.engine import load_engine
from alphaloop.web.market import FrozenMarks, PublicMarket
from alphaloop.web.store import Store, new_id

log = logging.getLogger("tradoor.worker")


class QuietNotifier:
    def notify(self, *args):
        pass


class Worker:
    def __init__(self, store, engine=None, market=None):
        self.store = store
        self.engine = engine
        self.market = market or PublicMarket()
        self.identifier = new_id()

    def selected_engine(self):
        return self.engine or load_engine()

    def cycle(self):
        self.store.heartbeat(self.identifier)
        job = self.store.claim_job()
        if job:
            try:
                dataset = self.store.get("dataset", job["dataset_id"])
                engine = self.selected_engine()
                if job.get("engine") != engine.name:
                    raise ValueError("Queued engine version differs from the configured engine")
                result = engine.backtest(dataset["csv"], job["config"], job["id"], dataset["source"])
                if result.get("id") != job["id"] or result.get("engine") != engine.name or result.get("config") != job["config"] or result.get("status") != "completed":
                    raise ValueError("Engine result identity does not match the requested run")
                curve = result.get("curve", [])
                if not curve or len(curve)>5001 or any(not math.isfinite(float(point["equity"])) for point in curve):
                    raise ValueError("Engine returned an invalid equity curve")
                result["dataset_id"] = dataset["id"]
                result["attribution"] = dataset.get("attribution", "")
                self.store.finish_job(job, result=result)
            except Exception as exc:
                log.exception("Backtest job failed")
                self.store.finish_job(job, error=str(exc)[:300])
        for paper in self.store.list("paper"):
            if paper["status"] != "running" or time.time()-paper.get("attempted_at", 0) < 15:
                continue
            try:
                self.tick(paper["id"])
            except Exception as exc:
                log.warning("Paper %s waiting: %s", paper["id"], type(exc).__name__)
                with self.store.connect(True) as db:
                    current = self.store.read(db, "paper", paper["id"])
                    if current["status"] == "running":
                        current.update(error=str(exc)[:300], attempted_at=time.time(), data_status="unavailable")
                        self.store.write(db, "paper", current)
        self.store.heartbeat(self.identifier)

    def tick(self, identifier):
        paper = self.store.get("paper", identifier)
        if paper["status"] != "running":
            return False
        snapshot = self.market.snapshot(paper["exchange"], paper["symbols"], paper["frequency"], 2*paper["config"]["lookback"]+1)
        if time.time()-snapshot.observed_at > 120 or set(snapshot.prices) != set(paper["symbols"]) or any(not math.isfinite(p) or p<=0 for p in snapshot.prices.values()):
            raise ValueError("Incomplete or stale mark snapshot")
        engine = self.selected_engine()
        if engine.name != paper["engine"]:
            raise ValueError("Paper run engine differs from the configured engine")
        weights = engine.weights(snapshot.frame, paper["config"], paper["frequency"])
        if set(weights) != set(paper["symbols"]) or any(not math.isfinite(w) for w in weights.values()):
            raise ValueError("Invalid engine target weights")
        if sum(abs(w) for w in weights.values()) > 1.000001 or any(abs(w) > .500001 for w in weights.values()) or abs(sum(weights.values())) > .010001:
            raise ValueError("Target weights exceed the preview exposure limits")
        # Network is outside the transaction. Revision and unique signal timestamp
        # prevent a concurrent worker or API pause/stop from committing stale orders.
        with self.store.connect(True) as db:
            current = self.store.read(db, "paper", identifier)
            if current["status"] != "running" or current["revision"] != paper["revision"]:
                return False
            executor = PaperExecutor(starting_cash=paper["cash"], fee_bps=paper["config"]["feeBps"]+paper["config"]["slippageBps"], exchange=FrozenMarks(snapshot.prices), notifier=QuietNotifier())
            executor._positions = {s: Position(**p) for s, p in paper["positions"].items()}
            portfolio = executor.fetch_portfolio()
            peak = max(paper["peak"], portfolio.equity)
            drawdown = 1-portfolio.equity/peak if peak>0 else 1
            orders = []
            halted = portfolio.equity <= 0 or drawdown >= paper["drawdown_limit"]
            if halted:
                orders = executor.flatten_all()
                current.update(status="halted", halt_reason="Drawdown or nonpositive-equity stop")
            elif snapshot.signal_ts != paper.get("last_signal"):
                prior = db.execute("SELECT 1 FROM ticks WHERE run_id=? AND signal_ts=?", (identifier, snapshot.signal_ts)).fetchone()
                if prior is None:
                    orders = executor.reconcile(weights, portfolio, portfolio.equity)
                    db.execute("INSERT INTO ticks VALUES(?,?)", (identifier, snapshot.signal_ts))
                current["last_signal"] = snapshot.signal_ts
            portfolio = executor.fetch_portfolio()
            current.update(cash=portfolio.cash, equity=portfolio.equity, peak=max(peak,portfolio.equity),
                positions={s: asdict(p) for s,p in portfolio.positions.items() if abs(p.qty)>1e-10},
                marks=snapshot.prices, attempted_at=time.time(), observed_at=snapshot.observed_at,
                data_status="fresh", error=None)
            for order in orders:
                fill = {"id": new_id(), "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "symbol": order.symbol, "side": order.side.value, "quantity": order.filled_qty,
                    "price": order.avg_fill_price, "signal_ts": snapshot.signal_ts,
                    "cost": order.filled_qty*order.avg_fill_price*(paper["config"]["feeBps"]+paper["config"]["slippageBps"])/10000}
                self.store.write(db, "fill:"+identifier, fill)
            equity_point = {"id": new_id(), "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "equity": portfolio.equity}
            self.store.write(db, "equity:"+identifier, equity_point)
            self.store.write(db, "paper", current)
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("TRADOOR_DB", "state/tradoor.sqlite3"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--workspace", help="Same private manifest used by this workspace's API")
    args = parser.parse_args()
    if args.workspace:
        from alphaloop.web.workspace import configure_workspace
        args.db = configure_workspace(args.workspace)
    logging.basicConfig(level=logging.INFO)
    worker = Worker(Store(args.db))
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while running:
        try:
            worker.cycle()
        except Exception:
            log.exception("Worker cycle failed; retrying")
        if args.once:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
