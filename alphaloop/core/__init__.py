"""Core package: spec schema, feature resolver, plugin registry, loop orchestrator.

Everything in ``alphaloop.core`` is engine-, adapter-, and venue-agnostic.
It never imports from ``alphaloop.adapters``, ``alphaloop.backtest``,
``alphaloop.execute``, etc. — those are plugins discovered at runtime via
``alphaloop.core.registry``.
"""
