"""Public demonstration strategy policy, separate from engine infrastructure.

Customer alpha belongs in a private adapter/workspace, never in this module.
This allocator accepts scores; it does not know how private factors compute them.
"""
import numpy as np


def balanced_rank_weights(scores, selection, warmup):
    """Equal-weight top/bottom baskets for the explicitly selected demo baseline."""
    weights = np.zeros_like(scores, dtype=float)
    for i in range(warmup, len(scores)):
        row = scores[i]
        if not np.isfinite(row).all():
            raise ValueError("Strategy returned a non-finite score")
        if np.allclose(row, 0, atol=1e-14):
            continue
        order = np.argsort(-row, kind="stable")
        weights[i, order[:selection]] = .5 / selection
        weights[i, order[-selection:]] = -.5 / selection
    return weights
