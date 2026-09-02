"""Persisted runner state: ``state/<run-id>.json``.

A crash + restart must resume cleanly with no duplicate orders — the
runner reloads this file, re-fetches venue-truth positions (never trusts
the file's positions alone), and only trusts the file for open-order
tracking and kill-switch/halt status.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RunnerState:
    run_id: str
    venue: str
    spec_content_hash: str
    open_order_ids: list[str] = field(default_factory=list)
    last_reconciled_weights: dict[str, float] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str | None = None
    peak_equity: float = 0.0

    @classmethod
    def load_or_create(
        cls, path: str | Path, run_id: str, venue: str, spec_content_hash: str
    ) -> RunnerState:
        path = Path(path)
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return cls(run_id=run_id, venue=venue, spec_content_hash=spec_content_hash)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True))
