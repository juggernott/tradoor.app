"""Natural-language idea -> StrategySpec. A convenience, never a dependency.

:mod:`alphaloop.compile.llm` is provider-agnostic (env-selected) and always
returns a spec for the user to review/edit before it runs — nothing in
this package executes anything itself.
"""
