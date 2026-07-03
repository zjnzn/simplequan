"""Williams %R 威廉指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import highest, lowest, _ds


class WilliamsRCalculator:
    """威廉 %R 计算器。

    %R = -100 * (HighestHigh - Close) / (HighestHigh - LowestLow)

    params:
        period: 周期，默认 14
    """

    name = "willr"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["willr"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 14)
        n = len(bars)
        if n < period:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        hh = highest(high, period)
        ll = lowest(low, period)

        denom = hh[-1] - ll[-1]
        if denom == 0 or denom != denom:
            return {"willr": _ds(float("nan"))}

        willr = -100.0 * (hh[-1] - close[-1]) / denom
        return {"willr": _ds(willr)}
