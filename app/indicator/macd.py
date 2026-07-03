"""MACD 指数平滑异同移动平均线。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import ema, _ds


class MacdCalculator:
    """MACD 计算器。

    params:
        fast:   快线周期，默认 12
        slow:   慢线周期，默认 26
        signal: 信号线周期，默认 9
    """

    name = "macd"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["macd", "macd_signal", "macd_histogram"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        fast_p = params.get("fast", 12)
        slow_p = params.get("slow", 26)
        signal_p = params.get("signal", 9)
        closes = [float(b.close) for b in bars]
        if len(closes) < slow_p:
            return {}

        fast_ema = ema(closes, fast_p)
        slow_ema = ema(closes, slow_p)
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
        signal_line = ema(macd_line, signal_p)
        histogram = macd_line[-1] - signal_line[-1]

        return {
            "macd": _ds(macd_line[-1]),
            "macd_signal": _ds(signal_line[-1]),
            "macd_histogram": _ds(histogram),
        }
