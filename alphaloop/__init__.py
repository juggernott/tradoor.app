"""Alphaloop: an agentic research loop for crypto quants.

Public API surface re-exported here is intentionally small — most code
should import from the specific submodule (``alphaloop.core.spec``,
``alphaloop.backtest.base``, ...) so plugin authors can see exactly which
protocol they are implementing.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("alphaloop")
except PackageNotFoundError:  # pragma: no cover - editable/unbuilt checkout
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
