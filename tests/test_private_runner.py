import json

import pytest

from alphaloop.web.private_runner import run


def test_local_report_omits_alpha_and_does_not_overwrite(tmp_path, monkeypatch):
    prices = tmp_path / "prices.csv"
    prices.write_text("date,symbol,close\n" + "\n".join(
        f"2026-01-{day:02d},{symbol},100" for day in range(1, 11) for symbol in ("BTC", "ETH")))
    config = tmp_path / "config.json"
    config.write_text('{}')
    class PrivateEngine:
        name = "private"
        def backtest(self, csv, config, identifier, source):
            return {"id": identifier, "status": "completed", "engine": self.name,
                "equity": 100, "metrics": {}, "curve": [], "code": "private source",
                "config": {"secret": 42}, "weights": ["signals"], "trades": ["positions"]}
    monkeypatch.setattr("alphaloop.web.private_runner.load_engine", lambda: PrivateEngine())
    for key in ("TRADOOR_ENGINE_FACTORY", "TRADOOR_ALPHACORE_ROOT"):
        monkeypatch.setenv(key, "previous")
    output = tmp_path / "report.json"
    result = run(prices, config, output, factory="customer.adapter:create_engine", source_root=tmp_path)
    assert not {"code", "config", "weights", "trades", "engine"} & result.keys()
    assert json.loads(output.read_text())["privacy"] == "customer-local; no automatic upload"
    with pytest.raises(FileExistsError):
        run(prices, config, output, factory="customer.adapter:create_engine", source_root=tmp_path)
