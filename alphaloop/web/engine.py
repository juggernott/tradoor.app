"""Server-configured engine boundary. Never load modules supplied by API callers.

Alphacore v12 remains private, installed alongside this web service. Its adapter
must implement this protocol after its actual source contracts are inspected.
There is deliberately no fallback to the legacy browser or Alphaloop engines.
"""
from __future__ import annotations

import importlib
import os
from typing import Protocol


class EngineUnavailable(RuntimeError):
    pass


class Engine(Protocol):
    name: str

    def backtest(self, csv: str, config: dict, identifier: str, source: str) -> dict: ...

    def weights(self, frame, config: dict, frequency: str) -> dict[str, float]: ...


def load_engine() -> Engine:
    factory = os.environ.get("TRADOOR_ENGINE_FACTORY", "")
    if not factory:
        raise EngineUnavailable("Alphacore v12 is selected but not connected. Install its private adapter and set TRADOOR_ENGINE_FACTORY.")
    module, separator, attribute = factory.partition(":")
    if not separator or not module or not attribute or attribute.startswith("_"):
        raise EngineUnavailable("Invalid server engine factory configuration")
    try:
        engine = getattr(importlib.import_module(module), attribute)()
        if not callable(engine.backtest) or not callable(engine.weights) or not engine.name:
            raise TypeError("Engine does not implement the Tradoor adapter contract")
        return engine
    except (ImportError, AttributeError, TypeError) as exc:
        raise EngineUnavailable("The configured Alphacore v12 adapter could not be loaded") from exc
