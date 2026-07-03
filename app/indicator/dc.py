"""Donchian Channel 唐奇安通道。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import highest, lowest, _ds


class DcCalculator:
    """唐奇安通道计算器。

    params:
        period: 周期，默认 20
    """

    name = "dc"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["dc_upper", "dc_mid", "dc_lower"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        n = len(bars)
        if n < period:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]

        upper = highest(high, period)
        lower = lowest(low, period)
        mid = (upper[-1] + lower[-1]) / 2

        return {
            "dc_upper": _ds(upper[-1]),
            "dc_mid": _ds(mid),
            "dc_lower": _ds(lower[-1]),
        }
