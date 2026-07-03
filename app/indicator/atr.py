"""ATR 平均真实波幅。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import rma, _ds


class AtrCalculator:
    """ATR 平均真实波幅计算器。

    params:
        period: 周期，默认 14
    """

    name = "atr"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["atr", "tr"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 14)
        n = len(bars)
        if n < 2:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        tr = [0.0] * n
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        atr = rma(tr, period)
        return {"atr": _ds(atr[-1]), "tr": _ds(tr[-1])}
