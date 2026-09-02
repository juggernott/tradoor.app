from typer.testing import CliRunner

from alphaloop.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_adapters_command():
    result = runner.invoke(app, ["adapters"])
    assert result.exit_code == 0
    assert "ccxt" in result.output


def test_doctor_command():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Alphaloop doctor" in result.output


def test_journal_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["journal"])
    assert result.exit_code == 0


def test_run_without_yes_declines_noninteractively(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        "name: t\nhypothesis: h\nkind: timeseries\n"
        "universe:\n  symbols: [BTC/USDT]\n"
        "features: [price.ohlcv:1h]\n"
        "signals:\n  entry: 'close > 0'\n  exit: 'close < 0'\n"
        "sizer:\n  name: vol_target\n"
        "data_window:\n  start: '2024-01-01'\n  end: '2024-01-02'\n"
        "venue: binance\n"
    )
    result = runner.invoke(app, ["run", str(spec_path)])
    assert result.exit_code == 1


def test_flatten_unknown_venue_rejected():
    result = runner.invoke(app, ["flatten", "unknown-venue", "--yes"])
    assert result.exit_code != 0
