"""MACD 连续置信度策略。

信号 = clamp(macd_histogram / (close * sensitivity), -1, 1)
柱状图为正 → 多头动量，为负 → 空头动量；柱状图越大信号越强。
"""
from __future__ import annotations

from core.domain.signal import Signal


class MacdCrossStrategy:
    """MACD 动量置信度策略。

    params:
        fast:       快线周期，默认 12
        slow:       慢线周期，默认 26
        signal:     信号线周期，默认 9
        sensitivity: 归一化系数，默认 0.001
    """

    name = "macd_cross"
    version = "2.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        return ["macd", "macd_signal", "macd_histogram"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        sensitivity = params.get("sensitivity", 0.001)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        hist = indicators.get("macd_histogram")
        if hist is None:
            return None

        h = float(hist)
        price = float(bar.close)
        raw = h / (price * sensitivity)
        value = Signal._clamp(raw)
        return Signal(value, f"MACD_HIST_{h:.2f}")
