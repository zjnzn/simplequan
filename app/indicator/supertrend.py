"""SuperTrend 超级趋势指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import rma, _ds


class SupertrendCalculator:
    """超级趋势指标计算器。

    params:
        period:     ATR 周期，默认 10
        multiplier: 乘数，默认 3.0
    """

    name = "supertrend"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["supertrend", "supertrend_direction"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 10)
        multiplier = params.get("multiplier", 3.0)
        n = len(bars)
        if n < period + 1:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        # True Range → ATR (RMA)
        tr = [0.0] * n
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        atr = rma(tr, period)

        # Basic bands
        hl2 = [(high[i] + low[i]) / 2 for i in range(n)]
        upper_band = [hl2[i] + multiplier * atr[i] for i in range(n)]
        lower_band = [hl2[i] - multiplier * atr[i] for i in range(n)]

        # Find first valid
        first = 0
        for i in range(n):
            if atr[i] == atr[i]:
                first = i
                break

        final_upper = upper_band[:]
        final_lower = lower_band[:]
        direction = [0.0] * n
        supertrend = [float("nan")] * n

        direction[first] = 1.0
        supertrend[first] = lower_band[first]

        for i in range(first + 1, n):
            if atr[i] != atr[i]:
                direction[i] = direction[i - 1]
                supertrend[i] = supertrend[i - 1]
                continue

            if upper_band[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
                final_upper[i] = upper_band[i]
            else:
                final_upper[i] = final_upper[i - 1]

            if lower_band[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
                final_lower[i] = lower_band[i]
            else:
                final_lower[i] = final_lower[i - 1]

            if direction[i - 1] == -1:
                direction[i] = 1.0 if close[i] > final_upper[i] else -1.0
            else:
                direction[i] = -1.0 if close[i] < final_lower[i] else 1.0

            supertrend[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

        return {
            "supertrend": _ds(supertrend[-1]),
            "supertrend_direction": _ds(direction[-1]),
        }
