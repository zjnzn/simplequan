"""SuperTrend 趋势跟随策略（对齐 project_refactored SuperTrendStrategy）。

方向翻转给出最强信号 ±1.0；方向延续给出 ±0.6。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class SupertrendStrategy:
    """SuperTrend 趋势跟随策略。

    params:
        period:     ATR 周期，默认 10
        multiplier: 乘数，默认 3.0
    """

    name = "supertrend"
    version = "1.0.0"

    def __init__(self) -> None:
        self._prev_direction: float | None = None

    def required_indicators(self, params: dict) -> list[str]:
        return ["supertrend", "supertrend_direction"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        direction = indicators.get("supertrend_direction")
        if direction is None:
            return None

        d = float(direction)
        if d == 0:
            return Signal(0.0, "NO_SIGNAL")

        if self._prev_direction is None:
            self._prev_direction = d
            return Signal(0.0, "INIT")

        pd = self._prev_direction
        self._prev_direction = d

        # 方向翻转检测
        flip = d != pd and pd != 0

        if d == 1:
            return Signal(1.0 if flip else 0.6, "SUPERTREND_LONG")
        return Signal(-1.0 if flip else -0.6, "SUPERTREND_SHORT")
