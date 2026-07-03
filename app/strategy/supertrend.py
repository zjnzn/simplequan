"""SuperTrend 连续置信度策略。

信号 = direction * clamp(|close - supertrend| / (close * sensitivity), 0, 1)
价格距超趋势线越远，趋势置信度越高；接近趋势线时置信度趋近 0。
"""
from __future__ import annotations

from core.domain.signal import Signal


class SupertrendStrategy:
    """SuperTrend 置信度策略。

    params:
        period:      ATR 周期，默认 10
        multiplier:  乘数，默认 3.0
        sensitivity: 归一化系数，默认 0.01
    """

    name = "supertrend"
    version = "2.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        return ["supertrend", "supertrend_direction"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        sensitivity = params.get("sensitivity", 0.01)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        st = indicators.get("supertrend")
        direction = indicators.get("supertrend_direction")
        if st is None or direction is None:
            return None

        d = float(direction)
        if d == 0:
            return Signal(0.0, "ST_DIR_0")

        price = float(bar.close)
        # 价格距超趋势线的偏离程度
        deviation = abs(price - float(st)) / (price * sensitivity)
        strength = min(1.0, deviation)
        value = d * strength
        return Signal(value, f"ST_DIST_{strength:.2f}")
