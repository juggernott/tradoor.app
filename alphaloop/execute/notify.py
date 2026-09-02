"""Pluggable alerting on fills, errors, and halts. stdout by default."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from rich.console import Console

console = Console()


@runtime_checkable
class Notifier(Protocol):
    def notify(self, level: str, message: str) -> None: ...


class StdoutNotifier:
    def notify(self, level: str, message: str) -> None:
        style = {
            "info": "cyan",
            "warning": "yellow",
            "error": "bold red",
            "halt": "bold red on white",
        }
        console.print(f"[{style.get(level, 'white')}][{level.upper()}][/] {message}")


class TelegramNotifier:
    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self.bot_token = bot_token or os.environ.get("ALPHALOOP_TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("ALPHALOOP_TELEGRAM_CHAT_ID")
        if not (self.bot_token and self.chat_id):
            raise ValueError(
                "TelegramNotifier requires ALPHALOOP_TELEGRAM_BOT_TOKEN and "
                "ALPHALOOP_TELEGRAM_CHAT_ID (or explicit args)."
            )

    def notify(self, level: str, message: str) -> None:
        import requests

        requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": f"[{level.upper()}] {message}"},
            timeout=10,
        )


class WebhookNotifier:
    def __init__(self, url: str | None = None) -> None:
        resolved = url or os.environ.get("ALPHALOOP_WEBHOOK_URL")
        if not resolved:
            raise ValueError("WebhookNotifier requires ALPHALOOP_WEBHOOK_URL (or an explicit url).")
        self.url: str = resolved

    def notify(self, level: str, message: str) -> None:
        import requests

        requests.post(self.url, json={"level": level, "message": message}, timeout=10)


class CompositeNotifier:
    """Fans out to multiple notifiers; one's failure doesn't block the others."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    def notify(self, level: str, message: str) -> None:
        for n in self.notifiers:
            try:
                n.notify(level, message)
            except Exception as e:  # noqa: BLE001 - alerting must never crash the runner
                StdoutNotifier().notify("error", f"notifier {n!r} failed: {e}")
