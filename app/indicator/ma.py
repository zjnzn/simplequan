from __future__ import annotations

from collections import deque
from decimal import Decimal


class MaCalculator:
    """移动平均线指标计算器（无状态模板）。

    params:
        periods: MA 周期列表，默认 [5, 20]
    """
    name = "ma"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        periods = params.get("periods", [5, 20])
        return [f"ma_{p}" for p in periods]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        periods = params.get("periods", [5, 20])
        result = {}
        closes = [b.close for b in bars]
        for period in periods:
            if len(closes) >= period:
                result[f"ma_{period}"] = sum(closes[-period:], Decimal(0)) / period
        return result
