"""ADX 平均趋向指数。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import rma, _ds


class AdxCalculator:
    """ADX 平均趋向指数计算器。

    params:
        period: 周期，默认 14
    """

    name = "adx"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["adx", "plus_di", "minus_di"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 14)
        n = len(bars)
        if n < period + 1:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        # True Range
        tr = [0.0] * n
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        tr[0] = high[0] - low[0]

        # Directional Movement
        plus_dm = [0.0] * n
        minus_dm = [0.0] * n
        for i in range(1, n):
            up = high[i] - high[i - 1]
            down = low[i - 1] - low[i]
            if up > down and up > 0:
                plus_dm[i] = up
            if down > up and down > 0:
                minus_dm[i] = down

        # Wilder-smoothed
        atr_rma = rma(tr, period)
        plus_di_rma = rma(plus_dm, period)
        minus_di_rma = rma(minus_dm, period)

        # DI
        plus_di = [0.0] * n
        minus_di = [0.0] * n
        for i in range(n):
            if atr_rma[i] == atr_rma[i] and atr_rma[i] != 0:
                plus_di[i] = 100.0 * plus_di_rma[i] / atr_rma[i]
                minus_di[i] = 100.0 * minus_di_rma[i] / atr_rma[i]
            else:
                plus_di[i] = float("nan")
                minus_di[i] = float("nan")

        # DX
        dx = [float("nan")] * n
        for i in range(n):
            denom = plus_di[i] + minus_di[i]
            if denom != denom or denom == 0:
                continue
            dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / denom

        # ADX = RMA of DX
        adx = rma(dx, period)

        return {
            "adx": _ds(adx[-1]),
            "plus_di": _ds(plus_di[-1]),
            "minus_di": _ds(minus_di[-1]),
        }
