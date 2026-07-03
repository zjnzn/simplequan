"""Bollinger Bands 布林带。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import sma, stdev, _ds


class BbCalculator:
    """布林带计算器。

    params:
        period:  周期，默认 20
        std_dev: 标准差倍数，默认 2.0
    """

    name = "bb"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        period = params.get("period", 20)
        return [f"bb_upper_{period}", f"bb_mid_{period}", f"bb_lower_{period}", f"bb_bandwidth_{period}"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        std_dev = params.get("std_dev", 2.0)
        closes = [float(b.close) for b in bars]
        if len(closes) < period:
            return {}

        mid = sma(closes, period)
        std = stdev(closes, period)
        upper = mid[-1] + std_dev * std[-1]
        lower = mid[-1] - std_dev * std[-1]
        bandwidth = (upper - lower) / mid[-1] if mid[-1] != 0 else float("nan")

        return {
            f"bb_upper_{period}": _ds(upper),
            f"bb_mid_{period}": _ds(mid[-1]),
            f"bb_lower_{period}": _ds(lower),
            f"bb_bandwidth_{period}": _ds(bandwidth),
        }
