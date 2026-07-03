"""布林带连续置信度策略。

信号 = clamp(-(close - mid) / (upper - mid), -1, 1)
价格在下轨 → +1（超卖做多），在上轨 → -1（超买做空），中轨 → 0
"""
from __future__ import annotations

from core.domain.signal import Signal


class BollingerStrategy:
    """布林带均值回归置信度策略。

    params:
        period:  布林带周期，默认 20
        std_dev: 标准差倍数，默认 2.0
    """

    name = "bollinger_reversal"
    version = "3.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        period = params.get("period", 20)
        return [f"bb_upper_{period}", f"bb_mid_{period}",
                f"bb_lower_{period}"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        period = params.get("period", 20)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        upper = indicators.get(f"bb_upper_{period}")
        mid = indicators.get(f"bb_mid_{period}")
        lower = indicators.get(f"bb_lower_{period}")
        if upper is None or mid is None or lower is None:
            return None

        u, m, l = float(upper), float(mid), float(lower)
        close = float(bar.close)

        # 价格在轨内：(close-mid)/(upper-mid)∈[-1,1]，取负：下轨→+1，上轨→-1
        band_range = u - m  # upper-mid = mid-lower
        if band_range == 0:
            return Signal(0.0, "BB_FLAT")
        value = Signal._clamp(-(close - m) / band_range)
        return Signal(value, f"BB_{close:.2f}")
