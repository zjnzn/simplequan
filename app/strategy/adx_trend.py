"""ADX 连续置信度策略。

信号 = sign(+DI - -DI) * clamp(ADX/50, 0, 1) * clamp(|+DI--DI|/50, 0, 1)
趋势强度 × 方向偏差 → 连续置信度，ADX 低时信号自然趋近 0。
"""
from __future__ import annotations

from core.domain.signal import Signal


class AdxTrendStrategy:
    """ADX 趋势置信度策略。

    params:
        period: ADX 周期，默认 14
    """

    name = "adx_trend"
    version = "2.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        return ["adx", "plus_di", "minus_di"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        adx = indicators.get("adx")
        plus_di = indicators.get("plus_di")
        minus_di = indicators.get("minus_di")
        if adx is None or plus_di is None or minus_di is None:
            return None

        a, pdi, mdi = float(adx), float(plus_di), float(minus_di)

        # 趋势强度：ADX/50 裁剪到 [0, 1]
        trend = min(1.0, a / 50.0)
        # 方向分歧度：|+DI - -DI|/50 裁剪到 [0, 1]，DI 差值越大方向越确定
        diff = min(1.0, abs(pdi - mdi) / 50.0)
        # 方向符号
        sign = 1.0 if pdi > mdi else -1.0

        value = sign * trend * diff
        value = Signal._clamp(value)
        return Signal(value, f"ADX_{a:.1f}_{'LONG' if sign>0 else 'SHORT'}")
