from __future__ import annotations

from collections import deque
from decimal import Decimal


class RsiCalculator:
    """RSI 相对强弱指标计算器（Wilder's RMA 平滑，对齐 project_refactored）。

    params:
        period: RSI 周期，默认 14
    """
    name = "rsi"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        period = params.get("period", 14)
        return [f"rsi_{period}"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 14)
        closes = [float(b.close) for b in bars]
        n = len(closes)
        if n < period + 1:
            return {}

        # 1. 价格变动
        gain_full = [float("nan")]
        loss_full = [float("nan")]
        for i in range(1, n):
            delta = closes[i] - closes[i - 1]
            gain_full.append(delta if delta > 0 else 0.0)
            loss_full.append(-delta if delta < 0 else 0.0)

        # 2. Wilder's RMA 平滑
        from ._helpers import rma
        avg_gain = rma(gain_full, period)
        avg_loss = rma(loss_full, period)

        key = f"rsi_{period}"
        if avg_loss[-1] == 0:
            return {key: Decimal(str(100))}

        rs = avg_gain[-1] / avg_loss[-1]
        rsi = 100.0 - 100.0 / (1.0 + rs)
        return {key: Decimal(str(rsi))}
