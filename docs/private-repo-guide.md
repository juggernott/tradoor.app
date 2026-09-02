# Using Alphaloop from a private repo

This repo (`alphaloop`) is public and MIT-licensed. It never contains
strategy parameters, API keys, exchange credentials, or private journal
contents. If you have proprietary strategies, tuned parameters, or data
subscriptions to keep private, put them in your own repo (conventionally
named `alphaloop-private`) that depends on this one.

## Setup

```bash
# alphaloop-private/pyproject.toml
[project]
dependencies = ["alphaloop @ git+https://github.com/you/alphaloop"]
```

## Registering your own plugins

Every extension point is a Python entry-point group. Your private repo's
`pyproject.toml` registers plugins the exact same way this repo does —
nothing in `alphaloop`'s source needs to change or know your package
exists:

```toml
[project.entry-points."alphaloop.adapters"]
my_proprietary_feed = "alphaloop_private.adapters:MyProprietaryFeed"

[project.entry-points."alphaloop.sizers"]
my_custom_sizer = "alphaloop_private.sizing:MyCustomSizer"

[project.entry-points."alphaloop.executors"]
my_broker = "alphaloop_private.execute:MyBrokerExecutor"
```

Install your private package (`pip install -e .` inside
`alphaloop-private`) and `alphaloop adapters` / `alphaloop doctor` will
list your plugins alongside the built-in ones — the CLI, the resolver,
the registry, none of them distinguish "built into alphaloop" from
"registered by a private package." That's the whole point.

## Where things go

| Goes in `alphaloop` (public) | Goes in your private repo |
|---|---|
| Spec schema, resolver, registry, CLI, agent contract | Actual `.yaml` strategy specs with real parameters |
| Adapter *protocol* + a few reference implementations | Adapters for data you pay for and don't want to expose the shape of |
| Sizer/executor/validator *protocols* + reference implementations | Custom sizers/executors tuned to your risk tolerance |
| `journal/` and `cache/` are `.gitignore`d here | Your own journal, containing your actual run history |
| Docs, examples with synthetic/free data | Your `.env` with real API keys (never committed anywhere) |

## Journal privacy

`alphaloop`'s `.gitignore` excludes `journal/`, `cache/`, `state/`, and
`.env*` specifically so a contributor working in this repo never
accidentally commits a real run's results. Your private repo should keep
its own `.gitignore` doing the same, or — if the private repo itself is
meant to store journal history under version control — remove those lines
deliberately, knowing what you're committing.

## Contributing back

If you build an adapter, sizer, or validator that isn't proprietary (e.g.
it wraps a public API's *shape*, not your API key or a tuned parameter),
consider upstreaming it here instead of keeping it private — see
`CONTRIBUTING.md`.
