"""Keltner Channel 肯特纳通道。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import ema, rma, _ds


class KcCalculator:
    """肯特纳通道计算器。

    params:
        period:     EMA 周期，默认 20
        multiplier: ATR 乘数，默认 1.5
        atr_period: ATR 周期，默认 10
    """

    name = "kc"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["kc_upper", "kc_mid", "kc_lower", "kc_bandwidth"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        multiplier = params.get("multiplier", 1.5)
        atr_period = params.get("atr_period", 10)
        n = len(bars)
        if n < max(period, atr_period):
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        # Mid = EMA
        mid = ema(close, period)

        # ATR via RMA
        tr = [0.0] * n
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        atr = rma(tr, atr_period)

        upper = mid[-1] + multiplier * atr[-1]
        lower = mid[-1] - multiplier * atr[-1]
        bandwidth = (upper - lower) / mid[-1] if mid[-1] != 0 else float("nan")

        return {
            "kc_upper": _ds(upper),
            "kc_mid": _ds(mid[-1]),
            "kc_lower": _ds(lower),
            "kc_bandwidth": _ds(bandwidth),
        }
