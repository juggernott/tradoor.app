"""Data adapters: pluggable sources of point-in-time (or not) features.

Every adapter implements the :class:`alphaloop.adapters.base.DataAdapter`
protocol and registers itself under the ``alphaloop.adapters`` entry-point
group (see ``pyproject.toml``). This package ships:

- :mod:`alphaloop.adapters.ccxt_data` — OHLCV + funding, free, point-in-time.
- :mod:`alphaloop.adapters.elfa` — social mentions/sentiment (historical
  endpoints are point-in-time; live/trending are not).
- :mod:`alphaloop.adapters.nansen`, :mod:`alphaloop.adapters.cryptoquant`,
  :mod:`alphaloop.adapters.glassnode` — on-chain features. Endpoints not
  independently verifiable against public docs are marked
  ``TODO(verify)`` in their docstrings and raise ``NotImplementedError``
  rather than guess a response shape.
"""
