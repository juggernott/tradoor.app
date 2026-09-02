"""Sizers: turn a raw signal into target portfolio weights.

Every sizer implements :class:`alphaloop.sizing.base.Sizer` and returns
weights in the *same shape* as its input (index=timestamp,
columns=symbol), before the always-on risk layer
(:mod:`alphaloop.risk.limits`) clamps them. A sizer never applies risk
limits itself — that would let a spec silently bypass the risk layer by
swapping sizers.
"""
