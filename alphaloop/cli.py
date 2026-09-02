"""The Alphaloop CLI. Mirrored exactly by the agent tool contract (alphaloop/agent/tools.json)

— there is no separate code path for agent vs. human use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from alphaloop.core.confirm import ConfirmationDeclined, confirm_action, require_live_ack
from alphaloop.core.loop import run_backtest
from alphaloop.core.registry import default_registry
from alphaloop.core.resolver import Resolver
from alphaloop.core.spec import StrategySpec
from alphaloop.execute.base import Executor
from alphaloop.execute.notify import StdoutNotifier
from alphaloop.execute.runner import Runner
from alphaloop.execute.state import RunnerState
from alphaloop.journal.bundle import export_bundle
from alphaloop.journal.render import entries_table
from alphaloop.journal.store import JournalStore

app = typer.Typer(help="Alphaloop — where most alpha goes to die.", no_args_is_help=True)
console = Console()


def _default_resolver(adapter_names: list[str] | None = None) -> Resolver:
    return Resolver(adapter_names=adapter_names or ["ccxt"])


# -- read-only commands ------------------------------------------------


@app.command()
def compile(
    idea: str, out: Annotated[Path | None, typer.Option(help="Where to save the spec YAML")] = None
) -> None:
    """Compile a natural-language idea into a StrategySpec YAML (spec only, never runs it)."""

    from alphaloop.compile.llm import StrategyCompiler

    journal = JournalStore()
    spec = StrategyCompiler().compile(idea, killed_hypotheses=journal.killed_hypotheses())
    console.print(spec.to_yaml())
    if out:
        spec.save(out)
        console.print(f"[green]saved to {out}[/green]")


@app.command()
def analyze(run_id: str, journal_root: Annotated[Path, typer.Option()] = Path("journal")) -> None:
    """Show a journaled run's scorecard. Read-only — never submits or mutates anything."""

    run_dir = journal_root / run_id
    scorecard = run_dir / "scorecard.md"
    if not scorecard.exists():
        raise typer.BadParameter(f"no scorecard at {scorecard}")
    console.print(scorecard.read_text())


@app.command()
def journal(
    verdict: Annotated[str | None, typer.Option(help="Filter by PROMOTE/ITERATE/KILL")] = None,
    journal_root: Annotated[Path, typer.Option()] = Path("journal"),
) -> None:
    """List journal entries. Read-only."""

    store = JournalStore(journal_root)
    entries = store.list_entries(verdict=verdict)
    console.print(entries_table(entries))


@app.command()
def export(run_id: str, journal_root: Annotated[Path, typer.Option()] = Path("journal")) -> None:
    """Export a journal run as a verified, reproducible ZIP bundle."""

    out = export_bundle(journal_root / run_id)
    console.print(f"[green]exported {out}[/green]")


@app.command()
def adapters() -> None:
    """List installed adapters/engines/sizers/executors/validators. Read-only."""

    for group in (
        "alphaloop.adapters",
        "alphaloop.events",
        "alphaloop.engines",
        "alphaloop.sizers",
        "alphaloop.executors",
        "alphaloop.validators",
    ):
        console.print(
            f"[bold]{group}[/bold]: {', '.join(default_registry.names(group)) or '(none)'}"
        )


@app.command()
def doctor() -> None:
    """Check config/key health and venue connectivity before you hit a cryptic failure."""

    import os

    console.print("[bold]Alphaloop doctor[/bold]")
    checks = {
        "ALPHALOOP_ELFA_API_KEY": "elfa adapter",
        "ALPHALOOP_NANSEN_API_KEY": "nansen adapter",
        "ALPHALOOP_CRYPTOQUANT_API_KEY": "cryptoquant adapter",
        "ALPHALOOP_GLASSNODE_API_KEY": "glassnode adapter",
        "ALPHALOOP_XAI_API_KEY": "grok_news events / xai LLM provider",
        "ANTHROPIC_API_KEY": "anthropic LLM provider",
        "OPENAI_API_KEY": "openai LLM provider",
        "ALPHALOOP_BINANCE_API_KEY": "binance executor",
        "ALPHALOOP_HYPERLIQUID_PRIVATE_KEY": "hyperliquid executor",
    }
    for var, purpose in checks.items():
        present = bool(os.environ.get(var))
        mark = "[green]OK[/green]" if present else "[dim]not set[/dim]"
        console.print(f"  {var} ({purpose}): {mark}")

    for group in ("alphaloop.adapters", "alphaloop.engines", "alphaloop.executors"):
        names = default_registry.names(group)
        count_display = f"[green]{len(names)} found[/green]" if names else "[red]none found[/red]"
        console.print(f"  {group}: {count_display}")


@app.command()
def positions(venue: str) -> None:
    """Show current venue-truth positions. Read-only."""

    executor = _build_executor(venue, testnet=True)
    portfolio = executor.fetch_portfolio()
    console.print(f"equity={portfolio.equity:.2f} cash={portfolio.cash:.2f}")
    for symbol, pos in portfolio.positions.items():
        console.print(f"  {symbol}: {pos.qty}")


# -- mutating commands: confirm_action gate ------------------------------


@app.command()
def run(
    spec_path: Path,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation")] = False,
    adapter: Annotated[
        list[str] | None, typer.Option(help="Adapter names, in priority order")
    ] = None,
    n_splits: int = 5,
    embargo: int = 0,
) -> None:
    """Backtest + validate a spec. Mutates only the journal/cache — read-only re: markets."""

    spec = StrategySpec.load(spec_path)
    window = f"{spec.data_window.start}..{spec.data_window.end}@{spec.data_window.freq}"
    try:
        confirm_action(
            f"kind={spec.kind} venue={spec.venue} window={window}\n"
            f"features={spec.features}\nsizer={spec.sizer.name}",
            yes=yes,
            title=f"Backtest: {spec.name}",
        )
    except ConfirmationDeclined as e:
        console.print(f"[yellow]aborted: {e}[/yellow]")
        raise typer.Exit(1) from e

    resolver = _default_resolver(adapter)
    outcome = run_backtest(spec, resolver, n_splits=n_splits, embargo=embargo)

    store = JournalStore()
    import datetime as dt

    entry = store.record(spec, outcome, dt.date.today().isoformat())
    console.print(
        f"[bold]{outcome.report.verdict}[/bold] (grade {outcome.report.grade}) -> {entry.run_dir}"
    )


@app.command()
def new(
    idea: str,
    yes: Annotated[bool, typer.Option("--yes")] = False,
    adapter: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Compile an idea AND run it — the one-shot happy path. Same confirmation gate as `run`."""

    from alphaloop.compile.llm import StrategyCompiler

    journal_store = JournalStore()
    spec = StrategyCompiler().compile(idea, killed_hypotheses=journal_store.killed_hypotheses())
    console.print(spec.to_yaml())
    _invoke_run_with_spec(spec, yes=yes, adapter_names=adapter)


def _invoke_run_with_spec(spec: StrategySpec, yes: bool, adapter_names: list[str] | None) -> None:
    try:
        confirm_action(spec.to_yaml(), yes=yes, title=f"Backtest: {spec.name}")
    except ConfirmationDeclined as e:
        console.print(f"[yellow]aborted: {e}[/yellow]")
        raise typer.Exit(1) from e
    resolver = _default_resolver(adapter_names)
    outcome = run_backtest(spec, resolver)
    store = JournalStore()
    import datetime as dt

    entry = store.record(spec, outcome, dt.date.today().isoformat(), idea_text=spec.hypothesis)
    console.print(
        f"[bold]{outcome.report.verdict}[/bold] (grade {outcome.report.grade}) -> {entry.run_dir}"
    )


@app.command()
def paper(
    spec_path: Path,
    yes: Annotated[bool, typer.Option("--yes")] = False,
    interval: Annotated[int, typer.Option(help="Seconds between reconciliation ticks")] = 60,
    adapter: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Start paper trading a spec against live prices. Simulated fills only. Runs until Ctrl-C."""

    spec = StrategySpec.load(spec_path)
    try:
        confirm_action(f"paper trading {spec.name} on {spec.venue}", yes=yes)
    except ConfirmationDeclined as e:
        console.print(f"[yellow]aborted: {e}[/yellow]")
        raise typer.Exit(1) from e

    from alphaloop.execute.paper import PaperExecutor

    executor = PaperExecutor()
    runner = Runner(
        run_id=f"paper-{spec.content_hash()}",
        venue="paper",
        spec_content_hash=spec.content_hash(),
        executor=executor,
        risk=spec.risk,
    )
    console.print(f"[green]paper runner started: {runner.run_id}[/green] (Ctrl-C to stop)")
    _run_tick_loop(runner, spec, _default_resolver(adapter), interval)


@app.command()
def trade(
    spec_path: Path,
    venue: Annotated[str, typer.Option()],
    testnet: Annotated[bool, typer.Option("--testnet")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    live: Annotated[bool, typer.Option("--live")] = False,
    config_ack: Annotated[
        bool, typer.Option(help="From your config file's live_trading_ack")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes")] = False,
    interval: Annotated[int, typer.Option(help="Seconds between reconciliation ticks")] = 60,
    adapter: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Start live/testnet trading. Live requires --live AND config_ack. Runs until Ctrl-C."""

    require_live_ack(live=live, config_ack=config_ack)
    spec = StrategySpec.load(spec_path)
    mode = "LIVE MAINNET" if (live and not testnet) else ("testnet" if testnet else "dry-run")
    try:
        confirm_action(
            f"{mode} trading {spec.name} on {venue}",
            yes=yes,
            title="LIVE TRADE" if live else "Trade",
        )
    except ConfirmationDeclined as e:
        console.print(f"[yellow]aborted: {e}[/yellow]")
        raise typer.Exit(1) from e

    executor = _build_executor(venue, testnet=testnet and not live)
    runner = Runner(
        run_id=f"{venue}-{spec.content_hash()}",
        venue=venue,
        spec_content_hash=spec.content_hash(),
        executor=executor,
        risk=spec.risk,
        dry_run=dry_run,
    )
    console.print(f"[green]{venue} runner started: {runner.run_id}[/green] (mode={mode})")
    _run_tick_loop(runner, spec, _default_resolver(adapter), interval)


def _run_tick_loop(runner: Runner, spec: StrategySpec, resolver: Resolver, interval: int) -> None:
    """Reconcile toward the spec's live signal every ``interval`` seconds until Ctrl-C.

    Each tick's target weights are computed fresh
    (:func:`alphaloop.core.loop.compute_live_target_weights`) — the runner
    itself is stateless about the *signal*, only about orders/halt status,
    so a restart naturally recomputes the current signal rather than
    trusting anything stale.
    """

    import time

    from alphaloop.core.loop import compute_live_target_weights
    from alphaloop.execute.runner import HaltedError

    try:
        while True:
            try:
                target_weights = compute_live_target_weights(spec, resolver)
                result = runner.tick(target_weights)
                console.print(f"tick: equity={result.equity:.2f} orders={len(result.orders)}")
            except HaltedError as e:
                console.print(f"[red]{e}[/red]")
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]stopped (runner state preserved for resume)[/yellow]")


@app.command()
def flatten(venue: str, yes: Annotated[bool, typer.Option("--yes")] = False) -> None:
    """Close everything at a venue immediately. Manual override, always confirmed."""

    try:
        confirm_action(f"flatten ALL positions at {venue}", yes=yes, title="FLATTEN")
    except ConfirmationDeclined as e:
        console.print(f"[yellow]aborted: {e}[/yellow]")
        raise typer.Exit(1) from e
    executor = _build_executor(venue, testnet=True)
    orders = executor.flatten_all()
    console.print(f"flattened: {len(orders)} orders")


@app.command()
def resume(run_id: str, ack: Annotated[bool, typer.Option("--ack")] = False) -> None:
    """Clear a halted runner's kill-switch. Requires --ack."""

    state_path = Path("state") / f"{run_id}.json"
    if not state_path.exists():
        raise typer.BadParameter(f"no runner state at {state_path}")
    state = RunnerState.load_or_create(state_path, run_id, "", "")
    if not ack:
        console.print(f"[red]runner is halted: {state.halt_reason}. Pass --ack to clear.[/red]")
        raise typer.Exit(1)
    state.halted = False
    state.halt_reason = None
    state.save(state_path)
    console.print(f"[green]{run_id} resumed[/green]")


def _build_executor(venue: str, testnet: bool) -> Executor:
    if venue == "binance":
        from alphaloop.execute.binance_ccxt import BinanceExecutor

        return BinanceExecutor(testnet=testnet, notifier=StdoutNotifier())
    if venue == "hyperliquid":
        from alphaloop.execute.hyperliquid import HyperliquidExecutor

        return HyperliquidExecutor(testnet=testnet, notifier=StdoutNotifier())
    raise typer.BadParameter(f"unknown venue {venue!r}; expected 'binance' or 'hyperliquid'")


if __name__ == "__main__":
    app()
