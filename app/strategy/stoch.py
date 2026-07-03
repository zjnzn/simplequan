"""随机指标连续置信度策略。

信号 = clamp(-(K - 50) / 50, -1, 1)
K < 50 → 多头（超卖区看涨），K > 50 → 空头（超买区看跌）
"""
from __future__ import annotations

from core.domain.signal import Signal


class StochStrategy:
    """随机指标 KDJ 置信度策略。

    params:
        k_period:  %K 周期，默认 14
        d_period:  %D 周期，默认 3
    """

    name = "stoch"
    version = "2.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        return ["stoch_k", "stoch_d"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        k = indicators.get("stoch_k")
        if k is None:
            return None

        kv = float(k)
        value = Signal._clamp(-(kv - 50.0) / 50.0)
        return Signal(value, f"STOCH_K_{kv:.1f}")
