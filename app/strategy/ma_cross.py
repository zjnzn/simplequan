"""MA/EMA 连续置信度策略。

信号 = clamp((ma_fast - ma_slow) / (close * sensitivity), -1, 1)
快线在慢线上方 → 多头置信度，下方 → 空头置信度；间距越大越强。
"""
from __future__ import annotations

from core.domain.signal import Signal


class MaCrossStrategy:
    """均线间距置信度策略。

    params:
        fast:       快线周期，默认 5
        slow:       慢线周期，默认 20
        source:     指标源 (ma / ema)，默认 ma
        sensitivity: 归一化系数，默认 0.002（值越小信号越强）
    """

    name = "ma_cross_over"
    version = "4.0.0"

    def required_indicators(self, params: dict) -> list[str]:
        fast = params.get("fast", 5)
        slow = params.get("slow", 20)
        source = params.get("source", "ma")
        return [f"{source}_{fast}", f"{source}_{slow}"]

    async def on_bar(self, row: dict, ctx, params: dict) -> Signal | None:
        fast = params.get("fast", 5)
        slow = params.get("slow", 20)
        source = params.get("source", "ma")
        sensitivity = params.get("sensitivity", 0.002)

        v_fast = row.get(f"{source}_{fast}")
        v_slow = row.get(f"{source}_{slow}")
        if v_fast is None or v_slow is None:
            return None

        f, s = float(v_fast), float(v_slow)
        price = float(row.get("close", 0))
        if price == 0:
            return None

        raw = (f - s) / (price * sensitivity)
        value = Signal._clamp(raw)
        return Signal(value, "MA_SPREAD")
