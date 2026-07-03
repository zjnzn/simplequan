"""ROC 变动率指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import _ds


class RocCalculator:
    """ROC 变动率计算器。

    params:
        period: 周期，默认 12
    """

    name = "roc"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["roc"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 12)
        n = len(bars)
        if n < period + 1:
            return {}

        closes = [float(b.close) for b in bars]
        roc = (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100.0 if closes[-period - 1] != 0 else float("nan")
        return {"roc": _ds(roc)}
