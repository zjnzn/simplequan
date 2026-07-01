from __future__ import annotations

from collections import deque
from decimal import Decimal

from core.ports.indicator import Indicator


class MaCalculator(Indicator):
    """移动平均线指标计算器。

    params:
        periods: MA 周期列表，默认 [5, 20]
    """
    name = "ma"
    version = "1.0.0"

    def __init__(self, periods: list[int] | None = None) -> None:
        self._periods = periods or [5, 20]
        self.output_keys = [f"ma_{p}" for p in self._periods]

    def compute(self, bars: deque) -> dict[str, Decimal]:
        result = {}
        closes = [b.close for b in bars]
        for period in self._periods:
            if len(closes) >= period:
                result[f"ma_{period}"] = sum(closes[-period:], Decimal(0)) / period
        return result
