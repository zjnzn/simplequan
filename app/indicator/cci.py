"""CCI 商品通道指数。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import sma, _ds


class CciCalculator:
    """CCI 商品通道指数计算器。

    params:
        period: 周期，默认 20
    """

    name = "cci"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["cci"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        n = len(bars)
        if n < period:
            return {}

        tp = [float((b.high + b.low + b.close)) / 3 for b in bars]
        sma_tp = sma(tp, period)

        # MAD (Mean Absolute Deviation)
        mad = [float("nan")] * n
        for i in range(period - 1, n):
            window = tp[i - period + 1 : i + 1]
            mean = sum(window) / period
            mad[i] = sum(abs(x - mean) for x in window) / period

        idx = n - 1
        if mad[idx] == 0 or mad[idx] != mad[idx]:
            return {"cci": _ds(float("nan"))}

        cci = (tp[idx] - sma_tp[idx]) / (0.015 * mad[idx])
        return {"cci": _ds(cci)}
