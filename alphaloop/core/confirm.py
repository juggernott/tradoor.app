"""The confirmation protocol shared by every mutating CLI command.

Project principle #5: analysis is read-only; mutation needs confirmation.
Any command that runs a backtest, starts paper trading, or places live
orders must show the exact effective configuration and require explicit
confirmation (``--yes`` to skip in scripts). Live trading additionally
requires ``--live`` plus a config-file acknowledgement flag — see
:func:`require_live_ack`.

The agent plugin (:mod:`alphaloop.agent`) mirrors this exactly: it is not
a separate code path, so an agent gets the same confirmation prompts a
human does unless it passes the same ``--yes``/``--live`` flags.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


class ConfirmationDeclined(RuntimeError):
    """Raised when the user declines a confirmation prompt."""


def confirm_action(summary: str, *, yes: bool, title: str = "About to run") -> None:
    """Show ``summary`` (the effective config) and require confirmation.

    Args:
        summary: human-readable rendering of exactly what will happen —
            e.g. the resolved spec, venue, and mode. Never abbreviate this
            to "run the strategy"; the whole point is the user sees the
            actual effective configuration before it executes.
        yes: when True, skip the interactive prompt (for scripts/CI/agents
            that have already gotten user sign-off out of band).
    """

    console.print(Panel(summary, title=title, border_style="yellow"))
    if yes:
        return
    if not sys.stdin.isatty():
        raise ConfirmationDeclined(
            "refusing to run a mutating command non-interactively without --yes"
        )
    if not typer.confirm("Proceed?"):
        raise ConfirmationDeclined("user declined confirmation")


def require_live_ack(*, live: bool, config_ack: bool) -> None:
    """Live trading needs --live AND a config-file acknowledgement flag.

    Raises typer.BadParameter (not ConfirmationDeclined) because this is a
    missing-flag error, not a runtime decline — it should look like a CLI
    usage error, not a mid-run abort.
    """

    if not live:
        return
    if not config_ack:
        raise typer.BadParameter(
            "live trading requires both --live and config.live_trading_ack: true "
            "in your alphaloop config file. This is deliberately two separate "
            "acknowledgements — see docs/live-trading.md."
        )
