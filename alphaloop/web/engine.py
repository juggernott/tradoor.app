"""Server-configured engine boundary. Never load modules supplied by API callers.

Alphacore v12 remains private, installed alongside this web service. The bundled glue loads its
reviewed research-library contracts from an operator-configured private source root.
There is deliberately no fallback to the legacy browser or Alphaloop engines.
"""
from __future__ import annotations

import importlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol


class EngineUnavailable(RuntimeError):
    pass


class Engine(Protocol):
    name: str

    def backtest(self, csv: str, config: dict, identifier: str, source: str) -> dict: ...

    def weights(self, frame, config: dict, frequency: str) -> dict[str, float]: ...


def source_root() -> str:
    explicit = os.environ.get("TRADOOR_ALPHACORE_ROOT", "")
    if explicit:
        return explicit
    path = Path(os.environ.get("TRADOOR_ENGINE_CONFIG", "state/engine.json"))
    if path.is_file():
        return str(json.loads(path.read_text()).get("source_root", ""))
    return ""


def load_engine() -> Engine:
    factory = os.environ.get("TRADOOR_ENGINE_FACTORY", "") or "alphaloop.web.alphacore_v12:create_engine"
    return _construct(factory, source_root())


@lru_cache(maxsize=4)
def _construct(factory: str, root: str) -> Engine:
    module, separator, attribute = factory.partition(":")
    if not separator or not module or not attribute or attribute.startswith("_"):
        raise EngineUnavailable("Invalid server engine factory configuration")
    try:
        engine = getattr(importlib.import_module(module), attribute)()
        if not callable(engine.backtest) or not callable(engine.weights) or not engine.name:
            raise TypeError("Engine does not implement the Tradoor adapter contract")
        return engine
    except (ImportError, AttributeError, TypeError, OSError) as exc:
        raise EngineUnavailable("The configured Alphacore v12 adapter could not be loaded") from exc
