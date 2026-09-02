import pytest

from alphaloop.core.spec import RiskLimits
from alphaloop.execute.base import OrderSide, OrderStatus
from alphaloop.execute.notify import StdoutNotifier
from alphaloop.execute.paper import PaperExecutor
from alphaloop.execute.runner import HaltedError, Runner


class FakeExchange:
    """Minimal ccxt-shaped stub: fixed prices, no network."""

    def __init__(self, prices: dict[str, float]):
        self._prices = prices

    def fetch_ticker(self, symbol: str) -> dict:
        return {"last": self._prices[symbol]}


@pytest.fixture
def paper_executor():
    return PaperExecutor(
        starting_cash=10_000.0, exchange=FakeExchange({"BTC/USDT": 50_000.0, "ETH/USDT": 3_000.0})
    )


def test_paper_reconcile_opens_position(paper_executor):
    portfolio = paper_executor.fetch_portfolio()
    orders = paper_executor.reconcile({"BTC/USDT": 0.5}, portfolio, portfolio.equity)
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BUY
    assert orders[0].status == OrderStatus.FILLED

    portfolio2 = paper_executor.fetch_portfolio()
    assert portfolio2.positions["BTC/USDT"].qty > 0


def test_paper_reconcile_is_idempotent(paper_executor):
    portfolio = paper_executor.fetch_portfolio()
    paper_executor.reconcile({"BTC/USDT": 0.5}, portfolio, portfolio.equity)
    portfolio2 = paper_executor.fetch_portfolio()
    orders2 = paper_executor.reconcile({"BTC/USDT": 0.5}, portfolio2, portfolio2.equity)
    # equity shifts slightly between calls because the first reconcile paid
    # a fee, so a small rebalancing order is expected, not zero orders —
    # idempotency means "no runaway order size", not "no order":
    if orders2:
        assert orders2[0].qty * orders2[0].avg_fill_price < 10.0


def test_paper_flatten_closes_all(paper_executor):
    portfolio = paper_executor.fetch_portfolio()
    paper_executor.reconcile({"BTC/USDT": 0.3, "ETH/USDT": -0.2}, portfolio, portfolio.equity)
    paper_executor.flatten_all()
    portfolio2 = paper_executor.fetch_portfolio()
    assert all(abs(p.qty) < 1e-6 for p in portfolio2.positions.values())


def test_runner_dry_run_never_submits(tmp_path, paper_executor):
    runner = Runner(
        run_id="test-run",
        venue="paper",
        spec_content_hash="abc",
        executor=paper_executor,
        risk=RiskLimits(),
        state_path=tmp_path / "state.json",
        dry_run=True,
        notifier=StdoutNotifier(),
    )
    result = runner.tick({"BTC/USDT": 0.5})
    assert result.orders == []
    portfolio = paper_executor.fetch_portfolio()
    assert "BTC/USDT" not in portfolio.positions


def test_runner_kill_switch_trips_on_drawdown(tmp_path, paper_executor):
    runner = Runner(
        run_id="test-run-2",
        venue="paper",
        spec_content_hash="abc",
        executor=paper_executor,
        risk=RiskLimits(drawdown_halt_pct=0.01),
        state_path=tmp_path / "state2.json",
        notifier=StdoutNotifier(),
    )
    runner.tick({})  # establish peak equity
    paper_executor._cash -= 500  # simulate a large loss, well past 1% of ~10k equity
    result = runner.tick({})
    assert result.halted
    assert runner.state.halted

    with pytest.raises(HaltedError):
        runner.tick({})


def test_runner_resume_clears_halt(tmp_path, paper_executor):
    runner = Runner(
        run_id="test-run-3",
        venue="paper",
        spec_content_hash="abc",
        executor=paper_executor,
        risk=RiskLimits(drawdown_halt_pct=0.01),
        state_path=tmp_path / "state3.json",
        notifier=StdoutNotifier(),
    )
    runner.tick({})
    paper_executor._cash -= 500
    runner.tick({})
    assert runner.state.halted

    with pytest.raises(HaltedError):
        runner.resume(ack=False)

    runner.resume(ack=True)
    assert not runner.state.halted
