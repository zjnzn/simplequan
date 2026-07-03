"""随机指标 KDJ 超买超卖策略（对齐 project_refactored StochasticStrategy）。

K 上穿 D 且在超卖区→做多；K 下穿 D 且在超买区→做空。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class StochStrategy:
    """随机指标 KDJ 策略。

    params:
        k_period:    %K 周期，默认 14
        d_period:    %D 周期，默认 3
        overbought:  超买阈值，默认 80
        oversold:    超卖阈值，默认 20
    """

    name = "stoch"
    version = "1.0.0"

    def __init__(self) -> None:
        self._prev_k: float | None = None
        self._prev_d: float | None = None

    def required_indicators(self, params: dict) -> list[str]:
        return ["stoch_k", "stoch_d"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        ob = params.get("overbought", 80)
        os = params.get("oversold", 20)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        k = indicators.get("stoch_k")
        d = indicators.get("stoch_d")
        if k is None or d is None:
            return None

        kv, dv = float(k), float(d)

        if self._prev_k is None:
            self._prev_k, self._prev_d = kv, dv
            return Signal(0.0, "INIT")

        pk, pd = self._prev_k, self._prev_d
        self._prev_k, self._prev_d = kv, dv

        # K 上穿 D
        if pk <= pd and kv > dv:
            if kv < os:
                return Signal(0.8, "STOCH_CROSS_UP_OVERSOLD")
            return Signal(0.5, "STOCH_CROSS_UP")

        # K 下穿 D
        if pk >= pd and kv < dv:
            if kv > ob:
                return Signal(-0.8, "STOCH_CROSS_DOWN_OVERBOUGHT")
            return Signal(-0.5, "STOCH_CROSS_DOWN")

        return Signal(0.0, "NO_SIGNAL")
