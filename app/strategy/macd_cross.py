"""MACD 金叉死叉策略（对齐 project_refactored MACDCrossStrategy）。

零轴位置加权；柱状图加速辅助持仓信号。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class MacdCrossStrategy:
    """MACD 金叉死叉策略。

    params:
        fast:   快线周期，默认 12
        slow:   慢线周期，默认 26
        signal: 信号线周期，默认 9
    """

    name = "macd_cross"
    version = "1.0.0"

    def __init__(self) -> None:
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None
        self._prev_hist: float | None = None

    def required_indicators(self, params: dict) -> list[str]:
        return ["macd", "macd_signal", "macd_histogram"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        macd = indicators.get("macd")
        sig = indicators.get("macd_signal")
        hist = indicators.get("macd_histogram")
        if macd is None or sig is None or hist is None:
            return None

        m, s, h = float(macd), float(sig), float(hist)

        if self._prev_macd is None:
            self._prev_macd = m
            self._prev_signal = s
            self._prev_hist = h
            return Signal(0.0, "INIT")

        pm, ps, ph = self._prev_macd, self._prev_signal, self._prev_hist
        self._prev_macd = m
        self._prev_signal = s
        self._prev_hist = h

        # 零轴权重
        long_weight = 0.3 if m > 0 else -0.1
        short_weight = 0.3 if m < 0 else -0.1

        # 条件1：金叉
        if pm <= ps and m > s:
            strength = Signal._clamp(0.7 + long_weight)
            return Signal(strength, "MACD_GOLDEN_CROSS")

        # 条件2：死叉
        if pm >= ps and m < s:
            strength = Signal._clamp(-(0.7 + short_weight))
            return Signal(strength, "MACD_DEATH_CROSS")

        # 条件3：柱状图多头扩张
        if h > 0 and h > ph:
            return Signal(0.4, "MACD_HIST_LONG")

        # 条件4：柱状图空头扩张
        if h < 0 and h < ph:
            return Signal(-0.4, "MACD_HIST_SHORT")

        return Signal(0.0, "NO_SIGNAL")
