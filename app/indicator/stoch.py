"""Stochastic 随机指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import highest, lowest, sma, _ds


class StochCalculator:
    """随机指标计算器。

    params:
        k_period: %K 周期，默认 14
        d_period: %D 周期，默认 3
    """

    name = "stoch"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["stoch_k", "stoch_d"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        k_period = params.get("k_period", 14)
        d_period = params.get("d_period", 3)
        n = len(bars)
        if n < k_period:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]

        hh = highest(high, k_period)
        ll = lowest(low, k_period)

        k = [float("nan")] * n
        for i in range(n):
            denom = hh[i] - ll[i]
            if denom != denom or denom == 0:
                continue
            k[i] = 100.0 * (close[i] - ll[i]) / denom

        k_valid = [v for v in k if v == v]
        if len(k_valid) < d_period:
            return {"stoch_k": _ds(k[-1] if k[-1] == k[-1] else float("nan")),
                    "stoch_d": _ds(float("nan"))}

        d = sma(k, d_period)
        return {"stoch_k": _ds(k[-1]), "stoch_d": _ds(d[-1])}
