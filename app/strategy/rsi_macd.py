"""RSI 连续置信度策略。

信号 = clamp(-(RSI - 50) / 50, -1, 1)
RSI < 50 → 多头（超卖区看涨），低至 0 时信号=+1
RSI > 50 → 空头（超买区看跌），高至 100 时信号=-1
"""
from __future__ import annotations

from core.domain.signal import Signal


class RsiMacdStrategy:
    """RSI 置信度策略。

    params:
        period: RSI 周期，默认 14
    """

    name = "rsi_macd"
    version = "3.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        period = params.get("period", 14)
        return [f"rsi_{period}"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        period = params.get("period", 14)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        rsi = indicators.get(f"rsi_{period}")
        if rsi is None:
            return None

        r = float(rsi)
        # RSI 在 30-70 中性区也输出非零值，信号强度与偏离中位线成正比
        value = Signal._clamp(-(r - 50.0) / 50.0)
        return Signal(value, f"RSI_{r:.1f}")
