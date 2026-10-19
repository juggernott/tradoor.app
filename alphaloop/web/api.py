"""Same-origin, single-owner API. Serve only on loopback in --local mode."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from alphaloop.web.engine import EngineUnavailable, load_engine
from alphaloop.web.research import Config, csv_frame
from alphaloop.web.store import Store, new_id
from alphaloop.web.market import PublicMarket
from alphaloop.web.catalog import HistoricalCatalog


class DatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str = Field(max_length=5_000_000)
    source: str = Field(min_length=1, max_length=120)


class BacktestRequest(BaseModel):
    dataset_id: str
    config: Config


class MarketDatasetRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    exchange: Literal["binance","kraken"]="binance"
    symbols: list[str]=Field(min_length=2,max_length=10)
    bars: int=Field(default=600,ge=500,le=800)


class PaperRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    backtest_id: str
    exchange: Literal["binance", "kraken"] = "binance"
    symbols: list[str] = Field(min_length=2, max_length=10)
    frequency: Literal["1m", "5m", "1h", "1d"] = "1d"
    drawdown_limit: float = Field(default=.20, gt=0, le=.5)
    acknowledge_simulation: Literal[True]


def create_app(db_path=None, *, local=False, token=None, engine=None, allowed_hosts=None):
    token = token or os.environ.get("TRADOOR_ADMIN_TOKEN", "")
    if not local and len(token) < 32:
        raise RuntimeError("Set a 32+ character TRADOOR_ADMIN_TOKEN, or use explicit loopback-only --local mode")
    store = Store(db_path or os.environ.get("TRADOOR_DB", "state/tradoor.sqlite3"))
    app = FastAPI(title="Tradoor API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    catalog = HistoricalCatalog(store.workspace_id)
    hosts = allowed_hosts or ["localhost", "127.0.0.1", "::1"]
    if not local and os.environ.get("TRADOOR_HOST"):
        hosts = [os.environ["TRADOOR_HOST"]]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    def selected_engine():
        return engine or load_engine()

    @app.middleware("http")
    async def security(request: Request, call_next):
        if local and request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "Local mode accepts loopback connections only"}, 403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, 403)
        # No CORS or remote API URL overrides: dashboard and API share one origin.
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/login"} and not local:
            session = request.cookies.get("tradoor_session", "")
            try:
                saved = store.get("session", hashlib.sha256(session.encode()).hexdigest())
                valid = saved["expires"] > time.time()
            except KeyError:
                valid = False
            if not valid:
                return JSONResponse({"detail": "Sign in required"}, 401)
        if request.method not in {"GET", "HEAD"}:
            length = request.headers.get("content-length")
            try:
                too_large = length is None or int(length) > 6_000_000
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse({"detail": "Request body must declare Content-Length <= 6 MB"}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def missing(_request, _error):
        return JSONResponse({"detail": "Record not found"}, 404)

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse({"detail": str(error)[:300]}, 422)

    @app.get("/api/health")
    def health():
        try:
            connected = selected_engine()
            name, ready, reason = connected.name, True, None
            minimum_bars = getattr(connected, "minimum_bars", 5)
        except EngineUnavailable as exc:
            name, ready, reason = "Alphacore v12", False, str(exc)
            minimum_bars = None
        return {"api": "ready", "engine": name, "engine_ready": ready, "engine_error": reason,
                "minimum_bars": minimum_bars,
                "mode": "loopback-development" if local else "single-owner", "worker": store.worker_status(), "live_execution": False}

    @app.post("/api/login")
    def login(body: dict, response: Response):
        if local:
            return {"ok": True}
        if not hmac.compare_digest(str(body.get("token", "")).encode(), token.encode()):
            raise HTTPException(401, "Invalid owner token")
        value = secrets.token_urlsafe(32)
        store.put("session", {"id": hashlib.sha256(value.encode()).hexdigest(), "expires": time.time()+43200})
        response.set_cookie("tradoor_session", value, httponly=True, secure=True, samesite="strict", max_age=43200)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        identifier = hashlib.sha256(request.cookies.get("tradoor_session", "").encode()).hexdigest()
        with store.connect(True) as db:
            db.execute("DELETE FROM records WHERE kind='session' AND id=?", (identifier,))
        response.delete_cookie("tradoor_session")
        return {"ok": True}

    @app.get("/api/workspace")
    def workspace():
        datasets = [{k:v for k,v in d.items() if k!="csv"} for d in store.list("dataset")]
        jobs = [{k:v for k,v in d.items() if k not in {"claim", "lease_until"}} for d in store.list("job")]
        runs = [{k:v for k,v in d.items() if k not in {"weights", "trades"}} for d in store.list("backtest", 20)]
        return {"datasets": datasets, "jobs": jobs, "runs": runs, "papers": store.list("paper"), "worker": store.worker_status()}

    @app.post("/api/datasets", status_code=201)
    def dataset(body: DatasetRequest):
        frame = csv_frame(body.csv)
        dates = frame.index.get_level_values("ts").unique().sort_values()
        result = store.put("dataset", {"id": new_id(), "csv": body.csv, "source": body.source,
            "symbols": sorted(frame.index.get_level_values("symbol").unique()), "bars": len(dates),
            "start": dates[0].isoformat(), "end": dates[-1].isoformat(), "sha256": hashlib.sha256(body.csv.encode()).hexdigest()})
        return {k:v for k,v in result.items() if k!="csv"}

    @app.get("/api/catalog")
    def data_catalog():
        return {"datasets": catalog.list()}

    @app.post("/api/catalog/{identifier}/import", status_code=201)
    def import_catalog(identifier: str):
        approved = catalog.read(identifier)
        result = dataset(DatasetRequest(csv=approved["csv"], source=approved["source"]))
        record = store.get("dataset", result["id"])
        record.update(catalog_id=approved["catalog_id"], attribution=approved["attribution"])
        store.put("dataset", record)
        return {k:v for k,v in record.items() if k != "csv"}

    @app.get("/api/datasets/{identifier}")
    def get_dataset(identifier: str):
        return store.get("dataset", identifier)

    @app.post("/api/datasets/market", status_code=201)
    def import_market(body: MarketDatasetRequest):
        import re
        if len(set(body.symbols))!=len(body.symbols) or not all(re.fullmatch(r"[A-Z0-9]{1,15}/(USDT|USD|USDC)",s) for s in body.symbols):
            raise HTTPException(422,"Use distinct explicit exchange symbols such as BTC/USDT")
        if len({s.split("/")[1] for s in body.symbols})!=1:
            raise HTTPException(422,"All symbols must use the same quote currency")
        try:
            csv=PublicMarket().daily_history(body.exchange,body.symbols,body.bars)
        except Exception as exc:
            raise HTTPException(502,"Public exchange history is unavailable: "+type(exc).__name__) from exc
        return dataset(DatasetRequest(csv=csv,source=f"{body.exchange} public daily closes · "+", ".join(body.symbols)))

    @app.post("/api/backtests", status_code=202)
    def submit(body: BacktestRequest):
        try:
            connected = selected_engine()
        except EngineUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        dataset = store.get("dataset", body.dataset_id)
        required = max(getattr(connected,"minimum_bars",5),getattr(connected,"warmup_multiplier",1)*body.config.lookback+3)
        if dataset["bars"]<required or body.config.selection*2>len(dataset["symbols"]):
            raise HTTPException(422, f"Need at least {required} dates and non-overlapping long/short baskets")
        return store.put("job", {"id": new_id(), "status": "queued", "dataset_id": dataset["id"],
            "config": body.config.model_dump(), "engine": connected.name, "created": time.time()})

    @app.get("/api/backtests/{identifier}")
    def backtest(identifier: str):
        return store.get("backtest", identifier)

    @app.post("/api/paper", status_code=201)
    def create_paper(body: PaperRequest):
        try:
            connected = selected_engine()
        except EngineUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        run = store.get("backtest", body.backtest_id)
        if run["engine"] != connected.name:
            raise HTTPException(409, "Backtest engine version differs from the configured forward engine")
        config = Config.model_validate(run["config"])
        if body.frequency != "1d":
            raise HTTPException(422, "This daily backtest must forward-test on daily bars; intraday research support is not connected yet")
        if len(set(body.symbols)) != len(body.symbols) or config.selection*2>len(body.symbols):
            raise HTTPException(422, "Invalid or overlapping universe")
        import re
        if not all(re.fullmatch(r"[A-Z0-9]{1,15}/(USDT|USD|USDC)", s) for s in body.symbols):
            raise HTTPException(422, "Use explicit exchange symbols such as BTC/USDT")
        if len({s.split("/")[1] for s in body.symbols})!=1:
            raise HTTPException(422,"All paper symbols must use the same quote currency")
        dataset = store.get("dataset", run["dataset_id"])
        def normalize(symbol):
            return symbol.split("/")[0]
        if {normalize(s) for s in body.symbols} != {normalize(s) for s in dataset["symbols"]}:
            raise HTTPException(422, "Paper assets must match the backtested dataset")
        capital = config.capital
        return store.put("paper", {"id": new_id(), "name": run["name"], "backtest_id": run["id"],
            "engine": run["engine"], "config": config.model_dump(), "status": "running", "exchange": body.exchange,
            "symbols": body.symbols, "frequency": body.frequency, "drawdown_limit": body.drawdown_limit,
            "quote_currency":body.symbols[0].split("/")[1],
            "capital": capital, "cash": capital, "equity": capital, "peak": capital, "positions": {},
            "marks": {}, "last_signal": None, "observed_at": None, "data_status": "awaiting-first-tick",
            "created": time.time(), "error": None})

    @app.get("/api/paper/{identifier}")
    def paper(identifier: str):
        result = store.get("paper", identifier)
        result["fills"] = store.list("fill:"+identifier, 200)
        result["curve"] = list(reversed(store.list("equity:"+identifier, 1000)))
        return result

    @app.post("/api/paper/{identifier}/{action}")
    def control(identifier: str, action: Literal["pause", "resume", "stop"]):
        with store.connect(True) as db:
            paper = store.read(db, "paper", identifier)
            if paper["status"] in {"stopped", "halted"}:
                raise HTTPException(409, "Terminal run: create a new paper run")
            paper["status"] = {"pause": "paused", "resume": "running", "stop": "stopped"}[action]
            store.write(db, "paper", paper)
        return store.get("paper", identifier)

    root = Path(__file__).resolve().parents[2]/"web"/"dist"
    if root.is_dir():
        app.mount("/", StaticFiles(directory=root, html=True), name="dashboard")
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Loopback-only development workspace, no account login")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--db", default=os.environ.get("TRADOOR_DB", "state/tradoor.sqlite3"))
    parser.add_argument("--workspace", help="Private operator manifest; use separate processes for each workspace")
    args = parser.parse_args()
    if args.workspace:
        if args.local:
            parser.error("Named customer workspaces require owner authentication; omit --local")
        from alphaloop.web.workspace import configure_workspace
        args.db = configure_workspace(args.workspace)
    if args.local and args.host not in {"127.0.0.1", "::1"}:
        parser.error("--local can only bind a loopback address")
    uvicorn.run(create_app(args.db, local=args.local), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
