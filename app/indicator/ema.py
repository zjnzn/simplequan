"""EMA 指数移动平均线。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import ema, _ds


class EmaCalculator:
    """EMA 指数移动平均计算器。

    params:
        period: 周期，默认 20
    """

    name = "ema"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        period = params.get("period", 20)
        return [f"ema_{period}"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        closes = [float(b.close) for b in bars]
        if len(closes) < period:
            return {}
        result = ema(closes, period)
        return {f"ema_{period}": _ds(result[-1])}
