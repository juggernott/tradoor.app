"""SQLite state shared by API and workers. Never persist exchange credentials."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def new_id() -> str:
    return uuid.uuid4().hex


def dump(value) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


class Store:
    def __init__(self, path: str | Path, *, workspace_id=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_id = workspace_id or os.environ.get("TRADOOR_WORKSPACE_ID")
        with self.connect(True) as db:
            # Bind before schema changes; never adopt an existing owner's data.
            db.execute("CREATE TABLE IF NOT EXISTS workspace_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL)")
            owner = db.execute("SELECT owner FROM workspace_identity WHERE singleton=1").fetchone()
            if owner and owner[0] != self.workspace_id:
                raise ValueError("Database belongs to a different workspace")
            if not owner and self.workspace_id:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
                if exists and db.execute("SELECT 1 FROM records LIMIT 1").fetchone():
                    raise ValueError("Existing unbound data requires an explicit owner migration")
                db.execute("INSERT INTO workspace_identity VALUES(1,?)", (self.workspace_id,))
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
                    PRIMARY KEY(kind,id)
                );
                CREATE TABLE IF NOT EXISTS ticks (
                    run_id TEXT NOT NULL, signal_ts TEXT NOT NULL,
                    PRIMARY KEY(run_id,signal_ts)
                );
                CREATE TABLE IF NOT EXISTS heartbeats (id TEXT PRIMARY KEY, updated REAL NOT NULL);
            """)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def read(db, kind, identifier):
        row = db.execute("SELECT body,revision FROM records WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        if row is None:
            raise KeyError(identifier)
        body = json.loads(row["body"])
        body["revision"] = row["revision"]
        return body

    @staticmethod
    def write(db, kind, body):
        db.execute("""INSERT INTO records(kind,id,body,updated) VALUES(?,?,?,?)
            ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,updated=excluded.updated,
            revision=records.revision+1""", (kind, body["id"], dump(body), time.time()))

    def get(self, kind, identifier):
        with self.connect() as db:
            return self.read(db, kind, identifier)

    def put(self, kind, body):
        with self.connect(True) as db:
            self.write(db, kind, body)
        return self.get(kind, body["id"])

    def list(self, kind, limit=100):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT body FROM records WHERE kind=? ORDER BY updated DESC LIMIT ?", (kind, limit))]

    def heartbeat(self, identifier):
        with self.connect(True) as db:
            db.execute("INSERT OR REPLACE INTO heartbeats VALUES(?,?)", (identifier, time.time()))

    def worker_status(self):
        with self.connect() as db:
            row = db.execute("SELECT max(updated) FROM heartbeats").fetchone()
        last = row[0]
        return {"online": last is not None and time.time()-last < 120, "last_seen": last}

    def claim_job(self):
        with self.connect(True) as db:
            for row in db.execute("SELECT body FROM records WHERE kind='job' ORDER BY updated"):
                job = json.loads(row[0])
                if job["status"] == "queued" or (job["status"] == "running" and job.get("lease_until", 0) < time.time()):
                    job.update(status="running", lease_until=time.time()+600, claim=new_id())
                    self.write(db, "job", job)
                    return job
        return None

    def finish_job(self, job, result=None, error=None):
        with self.connect(True) as db:
            current = self.read(db, "job", job["id"])
            if current.get("claim") != job["claim"]:
                return
            if result is not None:
                self.write(db, "backtest", result)
                current.update(status="completed", result_id=result["id"])
            else:
                current.update(status="failed", error=error)
            current["lease_until"] = 0
            self.write(db, "job", current)
