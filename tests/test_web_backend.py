from __future__ import annotations

import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from alphaloop.web.api import create_app
from alphaloop.web.engine import EngineUnavailable, load_engine
from alphaloop.web.market import Snapshot
from alphaloop.web.store import Store
from alphaloop.web.worker import Worker


class TestEngine:
    """Test-only injected implementation. Never a runtime engine fallback."""
    __test__ = False
    name = "test-engine"

    def backtest(self, csv, config, identifier, source):
        return {"id": identifier, "engine": self.name, "config": config, "source": source,
                "name": config["name"], "status": "completed", "equity": config["capital"],
                "curve": [{"date": "2025-02-01", "equity": config["capital"]}],
                "metrics": {"totalReturn": 0, "maxDrawdown": 0, "sharpe": None}, "weights": [], "trades": []}

    def weights(self, frame, config, frequency):
        return {"BTC/USDT": .5, "ETH/USDT": -.5}


class TestMarket:
    __test__ = False
    def __init__(self):
        self.prices = {"BTC/USDT": 100., "ETH/USDT": 100.}
        self.signal_ts = "2026-10-18T00:00:00+00:00"
        self.age = 0
        self.callback = None

    def snapshot(self, *args):
        if self.callback:
            self.callback()
        return Snapshot(pd.DataFrame(), self.prices, self.signal_ts, time.time()-self.age)


@pytest.fixture
def csv():
    return "date,symbol,close\n" + "\n".join(f"{d.date()},{s},100" for d in pd.date_range("2025-01-01", periods=35) for s in ["BTC/USDT", "ETH/USDT"])


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path/"test.sqlite3", local=True, engine=TestEngine(), allowed_hosts=["testserver"])
    with TestClient(app) as client:
        yield client


def prepared(client, csv):
    dataset = client.post("/api/datasets", json={"csv": csv, "source": "Synthetic test fixture"}).json()
    job = client.post("/api/backtests", json={"dataset_id": dataset["id"], "config": {"lookback": 2}})
    assert job.status_code == 202, job.text
    store = client.app.state.store
    market = TestMarket()
    worker = Worker(store, TestEngine(), market)
    worker.cycle()
    paper = client.post("/api/paper", json={"backtest_id": job.json()["id"], "symbols": ["BTC/USDT", "ETH/USDT"], "acknowledge_simulation": True})
    assert paper.status_code == 201, paper.text
    return store, market, worker, paper.json()["id"]


def test_default_engine_is_unavailable_not_legacy(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADOOR_ENGINE_FACTORY", raising=False)
    monkeypatch.delenv("TRADOOR_ALPHACORE_ROOT", raising=False)
    monkeypatch.setenv("TRADOOR_ENGINE_CONFIG",str(tmp_path/"missing.json"))
    with pytest.raises(EngineUnavailable, match="v12"):
        load_engine()


def test_unavailable_engine_rejects_job_without_queuing(tmp_path, monkeypatch, csv):
    monkeypatch.delenv("TRADOOR_ENGINE_FACTORY", raising=False)
    monkeypatch.delenv("TRADOOR_ALPHACORE_ROOT", raising=False)
    monkeypatch.setenv("TRADOOR_ENGINE_CONFIG",str(tmp_path/"missing.json"))
    with TestClient(create_app(tmp_path/"db", local=True, allowed_hosts=["testserver"])) as c:
        assert c.get("/api/health").json()["engine_ready"] is False
        d = c.post("/api/datasets", json={"csv": csv, "source": "fixture"}).json()
        assert c.post("/api/backtests", json={"dataset_id": d["id"], "config": {}}).status_code == 503
        assert c.get("/api/workspace").json()["jobs"] == []


def test_dataset_validation_and_immutability(client, csv):
    r = client.post("/api/datasets", json={"csv": csv, "source": "fixture"})
    assert r.status_code == 201
    assert "csv" not in r.json()
    saved = client.get("/api/datasets/"+r.json()["id"]).json()
    assert saved["csv"] == csv
    assert len(saved["sha256"]) == 64
    assert client.post("/api/datasets", json={"csv": csv+"\n2025-01-01,BTC/USDT,100", "source": "bad"}).status_code == 422
    assert client.get("/api/datasets/missing").status_code == 404


def test_owner_session_and_cross_origin_protection(tmp_path):
    with TestClient(create_app(tmp_path/"db", token="x"*40, allowed_hosts=["testserver"]), base_url="https://testserver") as c:
        assert c.get("/api/workspace").status_code == 401
        assert c.post("/api/login", json={"token": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"token": "x"*40}).status_code == 200
        assert c.get("/api/workspace").status_code == 200
        assert c.post("/api/logout", json={}, headers={"Origin": "https://attacker.invalid"}).status_code == 403
        assert c.post("/api/logout", json={}).status_code == 200
        assert c.get("/api/workspace").status_code == 401


def test_job_persists_results_and_worker_heartbeat(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    workspace = client.get("/api/workspace").json()
    assert workspace["jobs"][0]["status"] == "completed"
    assert workspace["runs"][0]["engine"] == "test-engine"
    assert workspace["worker"]["online"]
    assert Store(store.path).get("backtest", workspace["runs"][0]["id"])["dataset_id"]


def test_expired_job_lease_is_recoverable_and_old_claim_cannot_overwrite(client, csv):
    d = client.post("/api/datasets", json={"csv": csv, "source": "fixture"}).json()
    j = client.post("/api/backtests", json={"dataset_id": d["id"], "config": {}}).json()
    store = client.app.state.store
    first = store.claim_job()
    expired = dict(first, lease_until=0)
    store.put("job", expired)
    second = store.claim_job()
    assert first["claim"] != second["claim"]
    store.finish_job(first, error="stale worker")
    assert store.get("job", j["id"])["status"] == "running"
    store.finish_job(second, error="current worker")
    assert store.get("job", j["id"])["status"] == "failed"


def test_paper_costs_balance_restart_and_signal_dedup(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    assert worker.tick(identifier)
    p = store.get("paper", identifier)
    assert p["equity"] == pytest.approx(99930)
    assert p["cash"] == pytest.approx(99930)
    assert p["positions"]["BTC/USDT"]["qty"] == 500
    assert p["positions"]["ETH/USDT"]["qty"] == -500
    assert len(store.list("fill:"+identifier)) == 2
    # A fresh process restores both cash and positions. Same candle cannot rebalance twice.
    restarted = Worker(Store(store.path), TestEngine(), market)
    restarted.tick(identifier)
    assert store.get("paper", identifier)["equity"] == pytest.approx(99930)
    assert len(store.list("fill:"+identifier)) == 2
    market.prices = {"BTC/USDT": 110., "ETH/USDT": 90.}
    restarted.tick(identifier)
    assert store.get("paper", identifier)["equity"] == pytest.approx(109930)
    assert len(store.list("fill:"+identifier)) == 2


def test_pause_during_network_cannot_commit_fills(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    market.callback = lambda: client.post("/api/paper/"+identifier+"/pause", json={})
    assert worker.tick(identifier) is False
    assert store.get("paper", identifier)["status"] == "paused"
    assert store.list("fill:"+identifier) == []


def test_stale_mark_cannot_trade(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    market.age = 500
    worker.cycle()
    p = store.get("paper", identifier)
    assert p["data_status"] == "unavailable"
    assert "stale" in p["error"]
    assert not store.list("fill:"+identifier)


def test_risk_halt_flattens_simulated_positions_and_cannot_resume(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    worker.tick(identifier)
    market.prices = {"BTC/USDT": 50., "ETH/USDT": 150.}
    worker.tick(identifier)
    p = store.get("paper", identifier)
    assert p["status"] == "halted"
    assert not p["positions"]
    assert p["equity"] == pytest.approx(49860)
    assert client.post("/api/paper/"+identifier+"/resume", json={}).status_code == 409


def test_stop_is_terminal_and_no_new_ticks(client, csv):
    store, market, worker, identifier = prepared(client, csv)
    assert client.post("/api/paper/"+identifier+"/stop", json={}).status_code == 200
    assert worker.tick(identifier) is False
    assert client.post("/api/paper/"+identifier+"/resume", json={}).status_code == 409
