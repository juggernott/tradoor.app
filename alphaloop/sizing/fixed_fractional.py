"""Constant fraction of equity per open position, sign-following the signal."""

from __future__ import annotations

from typing import Any

import pandas as pd

from alphaloop.sizing.base import is_bool_frame


class FixedFractionalSizer:
    name = "fixed_fractional"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        fraction = float(params.get("fraction", 0.1))
        if is_bool_frame(signal):
            return signal.astype(float) * fraction
        # crosssectional score input: sign of score, same fixed fraction
        result: pd.DataFrame = signal.apply(
            lambda col: col.apply(lambda v: fraction if v > 0 else (-fraction if v < 0 else 0.0))
        )
        return result
