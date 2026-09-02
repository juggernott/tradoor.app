"""Plugin discovery for the six extension points.

External packages (e.g. a private strategy repo) register adapters, event
sources, backtest engines, sizers, executors, and validators via Python
entry points — no import of, or dependency on, this repo's internal module
layout is required. Group names:

    alphaloop.adapters   alphaloop.events     alphaloop.engines
    alphaloop.sizers     alphaloop.executors  alphaloop.validators

See ``docs/private-repo-guide.md`` for a worked example.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

_GROUPS = (
    "alphaloop.adapters",
    "alphaloop.events",
    "alphaloop.engines",
    "alphaloop.sizers",
    "alphaloop.executors",
    "alphaloop.validators",
)


class RegistryError(LookupError):
    """Raised when a named plugin cannot be found in its group."""


class Registry:
    """A discoverable, overridable map of plugin-name -> class, per group.

    Entry points are loaded lazily and cached. Tests (and interactive use)
    can call :meth:`register` to inject an in-process plugin — e.g. a mock
    ``DataAdapter`` — without touching ``pyproject.toml`` or installing
    anything.
    """

    def __init__(self) -> None:
        self._explicit: dict[str, dict[str, type]] = {g: {} for g in _GROUPS}
        self._discovered: dict[str, dict[str, type]] = {}

    def register(self, group: str, name: str, cls: type) -> None:
        if group not in _GROUPS:
            raise RegistryError(f"unknown plugin group {group!r}; expected one of {_GROUPS}")
        self._explicit[group][name] = cls

    def _discover(self, group: str) -> dict[str, type]:
        if group not in self._discovered:
            found: dict[str, type] = {}
            for ep in entry_points(group=group):
                try:
                    found[ep.name] = ep.load()
                except Exception:  # noqa: BLE001 - a broken plugin must not break discovery
                    continue
            self._discovered[group] = found
        return self._discovered[group]

    def get(self, group: str, name: str) -> type:
        if group not in _GROUPS:
            raise RegistryError(f"unknown plugin group {group!r}; expected one of {_GROUPS}")
        if name in self._explicit[group]:
            return self._explicit[group][name]
        discovered = self._discover(group)
        if name in discovered:
            return discovered[name]
        available = sorted({*self._explicit[group], *discovered})
        raise RegistryError(
            f"no plugin named {name!r} registered in group {group!r}. "
            f"Available: {available or '(none installed)'}. "
            f"Install the package providing it, or check `alphaloop adapters`."
        )

    def names(self, group: str) -> list[str]:
        if group not in _GROUPS:
            raise RegistryError(f"unknown plugin group {group!r}; expected one of {_GROUPS}")
        return sorted({*self._explicit[group], *self._discover(group)})

    def instantiate(self, group: str, name: str, **kwargs: Any) -> Any:
        return self.get(group, name)(**kwargs)


# A process-wide default registry. Most callers use this; tests construct
# their own ``Registry()`` when they need isolation from installed plugins.
default_registry = Registry()
