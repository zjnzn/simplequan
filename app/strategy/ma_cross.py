"""EMA/SMA 交叉策略（对齐 project_refactored EMACrossStrategy）。

金叉→+1.0，死叉→-1.0，趋势延续→±0.5。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from core.domain.signal import Signal


class MaCrossStrategy:
    """均线金叉死叉策略。

    params:
        fast: 快线周期，默认 5
        slow: 慢线周期，默认 20
        source: 指标源 (ma / ema)，默认 ma
    """

    name = "ma_cross_over"
    version = "2.0.0"

    def __init__(self) -> None:
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def required_indicators(self, params: dict) -> list[str]:
        fast = params.get("fast", 5)
        slow = params.get("slow", 20)
        source = params.get("source", "ma")
        return [f"{source}_{fast}", f"{source}_{slow}"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        fast = params.get("fast", 5)
        slow = params.get("slow", 20)
        source = params.get("source", "ma")
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        v_fast = indicators.get(f"{source}_{fast}")
        v_slow = indicators.get(f"{source}_{slow}")
        if v_fast is None or v_slow is None:
            return None

        f, s = float(v_fast), float(v_slow)

        if self._prev_fast is None or self._prev_slow is None:
            self._prev_fast, self._prev_slow = f, s
            return Signal(0.0, "INIT")

        pf, ps = self._prev_fast, self._prev_slow
        self._prev_fast, self._prev_slow = f, s

        # 金叉：前一根快线<=慢线，当前快线>慢线
        if pf <= ps and f > s:
            return Signal(1.0, "GOLDEN_CROSS")
        # 死叉：前一根快线>=慢线，当前快线<慢线
        if pf >= ps and f < s:
            return Signal(-1.0, "DEATH_CROSS")
        # 趋势延续
        if f > s:
            return Signal(0.5, "UPTREND")
        return Signal(-0.5, "DOWNTREND")
