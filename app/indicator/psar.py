"""Parabolic SAR 抛物线转向指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import _ds


class PsarCalculator:
    """抛物线 SAR 计算器。

    params:
        af_start: 初始加速因子，默认 0.02
        af_step:  加速因子步长，默认 0.02
        af_max:   最大加速因子，默认 0.20
    """

    name = "psar"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["psar", "psar_direction"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        af_start = params.get("af_start", 0.02)
        af_step = params.get("af_step", 0.02)
        af_max = params.get("af_max", 0.20)
        n = len(bars)
        if n < 3:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]

        psar_vals = [float("nan")] * n
        direction = [0.0] * n

        bull = high[1] > high[0]
        af = af_start
        ep = high[1] if bull else low[1]
        psar_vals[1] = low[0] if bull else high[0]
        direction[1] = 1.0 if bull else -1.0

        for i in range(2, n):
            new_psar = psar_vals[i - 1] + af * (ep - psar_vals[i - 1])

            if bull:
                new_psar = min(new_psar, low[i - 1], low[i - 2])
                if low[i] < new_psar:
                    bull = False
                    psar_vals[i] = ep
                    ep = low[i]
                    af = af_start
                    direction[i] = -1.0
                else:
                    psar_vals[i] = new_psar
                    direction[i] = 1.0
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + af_step, af_max)
            else:
                new_psar = max(new_psar, high[i - 1], high[i - 2])
                if high[i] > new_psar:
                    bull = True
                    psar_vals[i] = ep
                    ep = high[i]
                    af = af_start
                    direction[i] = 1.0
                else:
                    psar_vals[i] = new_psar
                    direction[i] = -1.0
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + af_step, af_max)

        return {"psar": _ds(psar_vals[-1]), "psar_direction": _ds(direction[-1])}
