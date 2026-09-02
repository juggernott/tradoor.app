"""Backtest engines behind the :class:`alphaloop.backtest.base.BacktestEngine` protocol.

Ships :mod:`alphaloop.backtest.vectorbt_engine` as the default, open-source
implementation, covering both ``timeseries`` and ``crosssectional`` specs.
The protocol is engine-agnostic — see ``docs/adapters.md`` for the
documented seam to plug in e.g. ``nautilus_trader``.
"""
