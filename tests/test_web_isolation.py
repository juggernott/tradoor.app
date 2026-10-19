import json

import pytest
from fastapi.testclient import TestClient

from alphaloop.web.api import create_app
from alphaloop.web.store import Store
from alphaloop.web.worker import Worker
from alphaloop.web.workspace import configure_workspace


class Engine:
    name = "customer-owned-test-engine"

    def backtest(self, csv, config, identifier, source):
        return {"id": identifier, "engine": self.name, "config": config,
                "status": "completed", "curve": [{"equity": 100, "date": "2026-01-01"}]}


def test_separate_authenticated_workspaces_deny_guessed_ids_and_jobs(tmp_path, monkeypatch):
    clients = []
    for owner in ("alice", "bob"):
        monkeypatch.setenv("TRADOOR_WORKSPACE_ID", owner)
        app = create_app(tmp_path / (owner + ".sqlite3"), token=owner * 32,
                         engine=Engine(), allowed_hosts=["testserver"])
        client = TestClient(app, base_url="https://testserver")
        assert client.get("/api/workspace").status_code == 401
        assert client.post("/api/login", json={"token": owner * 32}).status_code == 200
        clients.append(client)
    alice, bob = clients
    store = alice.app.state.store
    store.put("dataset", {"id": "private-dataset", "csv": "private alpha input", "source": "private"})
    store.put("job", {"id": "private-job", "dataset_id": "private-dataset", "status": "queued",
                      "engine": Engine.name, "config": {}})
    store.put("backtest", {"id": "private-result", "config": {"secret": "alpha"}})
    store.put("paper", {"id": "private-paper", "status": "paused"})
    for route in ("datasets/private-dataset", "backtests/private-result", "paper/private-paper"):
        assert bob.get("/api/" + route).status_code == 404
    assert bob.post("/api/paper/private-paper/resume", json={}).status_code == 404
    assert bob.post("/api/backtests", json={"dataset_id": "private-dataset", "config": {}}).status_code == 404
    assert bob.get("/api/workspace").json()["datasets"] == []
    # A Bob worker cannot claim Alice's pending research or publish its result.
    Worker(bob.app.state.store, Engine()).cycle()
    assert store.get("job", "private-job")["status"] == "queued"
    assert bob.app.state.store.list("backtest") == []
    # Alice's cookie cannot authenticate with Bob's separate session store.
    bob.cookies.clear()
    bob.cookies.set("tradoor_session", alice.cookies.get("tradoor_session"))
    assert bob.get("/api/workspace").status_code == 401
    for client in clients:
        client.close()


def test_database_binding_rejects_other_owner_and_unscoped_worker(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADOOR_WORKSPACE_ID", raising=False)
    path = tmp_path / "owned.sqlite3"
    Store(path, workspace_id="alice").put("dataset", {"id": "secret"})
    with pytest.raises(ValueError, match="different workspace"):
        Store(path, workspace_id="bob")
    with pytest.raises(ValueError, match="different workspace"):
        Store(path)
    assert Store(path, workspace_id="alice").get("dataset", "secret")
    legacy = tmp_path / "legacy.sqlite3"
    Store(legacy).put("dataset", {"id": "original-owner"})
    with pytest.raises(ValueError, match="migration"):
        Store(legacy, workspace_id="new-owner")


def test_manifest_replaces_inherited_private_engine_and_resolves_local_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("ALICE_TOKEN", "a" * 40)
    for key in ("TRADOOR_WORKSPACE_ID", "TRADOOR_DB", "TRADOOR_ENGINE_FACTORY",
                "TRADOOR_ALPHACORE_ROOT", "TRADOOR_ADMIN_TOKEN", "TRADOOR_HOST"):
        monkeypatch.setenv(key, "inherited-value")
    manifest = tmp_path / "workspace.json"
    manifest.write_text(json.dumps({"id": "alice", "database": "state/private.sqlite3",
        "engine_factory": "alice_private.adapter:create_engine", "source_root": "private-source",
        "token_env": "ALICE_TOKEN", "host": "alice.example.com"}))
    assert configure_workspace(manifest) == str((tmp_path / "state/private.sqlite3").resolve())
    import os
    assert os.environ["TRADOOR_ENGINE_FACTORY"] == "alice_private.adapter:create_engine"
    assert os.environ["TRADOOR_ALPHACORE_ROOT"] == str((tmp_path / "private-source").resolve())
