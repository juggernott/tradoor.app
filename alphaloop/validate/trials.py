"""Trial registry: one counter per dataset-hash, feeding deflated Sharpe.

Every backtest run against a given ``data_hash`` (see
:func:`alphaloop.backtest.vectorbt_engine._data_hash`) increments that
hash's trial count. The deflated Sharpe calculation
(:mod:`alphaloop.validate.deflated_sharpe`) uses the count to discount for
multiple-testing — running the same idea (or ten variations of it) against
the same data ten times should make its reported significance *harder* to
achieve, not free.

Persisted as a flat JSON file so it survives across CLI invocations without
a database (project principle #7: files over databases).
"""

from __future__ import annotations

import json
from pathlib import Path


class TrialRegistry:
    def __init__(self, path: str | Path = "journal/trials.json") -> None:
        self.path = Path(path)
        self._counts: dict[str, int] = {}
        if self.path.exists():
            self._counts = json.loads(self.path.read_text())

    def record_trial(self, data_hash: str) -> int:
        """Increment and return the new trial count for ``data_hash``."""

        self._counts[data_hash] = self._counts.get(data_hash, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._counts, indent=2, sort_keys=True))
        return self._counts[data_hash]

    def trial_count(self, data_hash: str) -> int:
        """Current count without incrementing — 0 if never recorded."""

        return self._counts.get(data_hash, 0)
