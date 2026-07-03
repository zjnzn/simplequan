"""RSI 超买超卖反转策略（对齐 project_refactored RSIStrategy）。

越极端信号越强；从极端区回归给出退出信号。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class RsiMacdStrategy:
    """RSI 超买超卖反转策略。

    params:
        period:       RSI 周期，默认 14
        oversold:     超卖阈值，默认 30
        overbought:   超买阈值，默认 70
    """

    name = "rsi_macd"
    version = "2.0.0"

    def __init__(self) -> None:
        self._prev_rsi: float | None = None

    def required_indicators(self, params: dict) -> list[str]:
        period = params.get("period", 14)
        return [f"rsi_{period}"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        period = params.get("period", 14)
        os = params.get("oversold", 30)
        ob = params.get("overbought", 70)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        rsi = indicators.get(f"rsi_{period}")
        if rsi is None:
            return None

        r = float(rsi)

        if self._prev_rsi is None:
            self._prev_rsi = r
            return Signal(0.0, "INIT")

        pr = self._prev_rsi
        self._prev_rsi = r

        # 条件1：超卖区 (RSI < oversold) — 越深信号越强
        if r < os:
            strength = Signal._clamp((os - r) / os * 3 + 0.5)
            return Signal(strength, "RSI_OVERSOLD")

        # 条件2：超买区 (RSI > overbought) — 越高信号越强
        if r > ob:
            strength = Signal._clamp(-((r - ob) / (100 - ob) * 3 + 0.5))
            return Signal(strength, "RSI_OVERBOUGHT")

        # 条件3：从超卖区回归（前一根在超卖，当前回到正常区）
        if pr < os and r >= os:
            return Signal(0.6, "RSI_EXIT_OVERSOLD")

        # 条件4：从超买区回归
        if pr > ob and r <= ob:
            return Signal(-0.6, "RSI_EXIT_OVERBOUGHT")

        return Signal(0.0, "NO_SIGNAL")
