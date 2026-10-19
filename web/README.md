# Tradoor Python workspace

The dashboard in dist/ talks to the same-origin Python API. It no longer submits browser-computed research results. The old browser simulation module remains only as a labelled sample-data generator and legacy unit-test target.

Alphacore v12 is the selected research engine. Its source on the Mac mini has not been accessible through SSH yet. Backend research jobs and continuous strategy paper-run creation remain unavailable until a private v12 adapter is installed. There is no silent fallback.

From the repository root, activate your virtual environment and run:

    python -m pip install -e '.[web]'
    python -m alphaloop.web.api --local

In another terminal using the same directory and environment:

    python -m alphaloop.web.worker

Open http://127.0.0.1:4173. This is a single-workspace loopback development server. For external deployment use HTTPS, owner authentication, persistent disk and a process supervisor.

See ../docs/tradoor-backend.md for the adapter contract, complete implementation status, test results, simulation assumptions and remaining Mac access blocker. No private Alphacore code or credentials have been copied into this public repository.