# Tradoor Python workspace

The dashboard in dist/ talks to the same-origin FastAPI API and independent worker. Alphacore v12 backtests and continuous simulated trading have been verified locally using the private research library. The private source is configured separately and excluded from this repository.

Install `.[web,v12]`, set `TRADOOR_ALPHACORE_ROOT`, and run `python -m alphaloop.web.api --local` and `python -m alphaloop.web.worker` in two terminals with the same environment and working directory. Open http://127.0.0.1:4173.

See [backend setup and limitations](../docs/tradoor-backend.md). The old browser simulation module remains only for sample generation and legacy tests. Live orders and public deployment remain pending.
