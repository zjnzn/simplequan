from core.domain.signal import Signal


class MaCrossStrategy:
    """均线交叉策略。金叉/死叉：cross 越大信号越强，clip 到 [-1,+1]。"""

    name = "ma_cross_over"
    version = "1.0.0"
    required_indicators = ["ma_5", "ma_20"]

    def __init__(self, params: dict | None = None):
        p = params or {}
        self.fast = p.get("fast", 5)
        self.slow = p.get("slow", 20)

    async def on_bar(self, bar, ctx) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        ma_fast = indicators.get(f"ma_{self.fast}")
        ma_slow = indicators.get(f"ma_{self.slow}")
        if ma_fast is None or ma_slow is None:
            return None
        cross = float(ma_fast - ma_slow)
        # 归一化：cross / (close * 0.002) 映射到 [-1,+1]
        normalized = cross / (float(bar.close) * 0.002)
        if abs(normalized) < 0.5:
            return Signal(0.0, "NO_CROSS")
        return Signal(Signal._clamp(normalized), "MA_CROSS_UP" if normalized > 0 else "MA_CROSS_DOWN")
