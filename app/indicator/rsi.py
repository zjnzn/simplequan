from __future__ import annotations

from collections import deque
from decimal import Decimal

from core.ports.indicator import Indicator


class RsiCalculator(Indicator):
    """RSI 相对强弱指标计算器。

    params:
        period: RSI 周期，默认 14
    """
    name = "rsi"
    version = "1.0.0"

    def __init__(self, period: int = 14) -> None:
        self._period = period
        self.output_keys = [f"rsi_{period}"]

    def compute(self, bars: deque) -> dict[str, Decimal]:
        closes = [b.close for b in bars]
        if len(closes) < self._period + 1:
            return {}

        gains = Decimal(0)
        losses = Decimal(0)
        recent = closes[-(self._period + 1):]
        for i in range(1, len(recent)):
            delta = recent[i] - recent[i - 1]
            if delta > 0:
                gains += delta
            else:
                losses += abs(delta)

        if losses == 0:
            return {self.output_keys[0]: Decimal(100)}

        rs = (gains / self._period) / (losses / self._period)
        rsi = Decimal(100) - (Decimal(100) / (1 + rs))
        return {self.output_keys[0]: rsi}
