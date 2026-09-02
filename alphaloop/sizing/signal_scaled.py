"""Weight proportional to signal magnitude, squashed through tanh.

For crosssectional scores: ``weight = max_weight * tanh(score / scale)``.
For boolean timeseries signals this degenerates to fixed_fractional
(there is no magnitude to scale by), so it falls back to that behavior.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from alphaloop.sizing.base import is_bool_frame


class SignalScaledSizer:
    name = "signal_scaled"

    def size(
        self, signal: pd.DataFrame, returns: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame:
        max_weight = float(params.get("max_weight", 0.20))
        scale = float(params.get("scale", 1.0))

        if is_bool_frame(signal):
            return signal.astype(float) * max_weight
        normalized: pd.DataFrame = signal.apply(
            lambda col: (col - col.mean()) / (col.std() or 1.0), axis=1, result_type="broadcast"
        )
        return cast(pd.DataFrame, np.tanh(normalized.fillna(0.0) / scale) * max_weight)
