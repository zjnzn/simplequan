"""ADX 趋势强度过滤策略（对齐 project_refactored ADXTrendStrategy）。

ADX >= 阈值时 +DI > -DI 做多，反之做空；ADX < 阈值无信号。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class AdxTrendStrategy:
    """ADX 趋势强度过滤策略。

    params:
        period:    ADX 周期，默认 14
        threshold: 趋势阈值，默认 25
    """

    name = "adx_trend"
    version = "1.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        return ["adx", "plus_di", "minus_di"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        threshold = params.get("threshold", 25)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        adx = indicators.get("adx")
        plus_di = indicators.get("plus_di")
        minus_di = indicators.get("minus_di")
        if adx is None or plus_di is None or minus_di is None:
            return None

        a, pdi, mdi = float(adx), float(plus_di), float(minus_di)

        # ADX 不足 → 无趋势
        if a < threshold:
            return Signal(0.0, "NO_TREND")

        # 信号强度：(ADX - threshold) / 25
        strength = Signal._clamp((a - threshold) / 25.0)

        if pdi > mdi:
            return Signal(strength, "ADX_TREND_UP")
        elif mdi > pdi:
            return Signal(-strength, "ADX_TREND_DOWN")
        return Signal(0.0, "NO_SIGNAL")
