from statistics import mean, stdev

from core.domain.signal import Signal



class BollingerStrategy:
    """布林带反转策略。触轨反弹/回落：偏离均值越远信号越强，0.5~1.0。"""

    name = "bollinger_reversal"
    version = "1.0.0"
    required_indicators: list[str] = []

    def __init__(self, params: dict | None = None):
        p = params or {}
        self.period = p.get("period", 20)
        self.std_mult = p.get("std_mult", 2.0)

    async def on_bar(self, bar, ctx) -> Signal | None:
        bars = ctx.market.bars.get(bar.interval)
        if bars is None or len(bars) < self.period:
            return None
        closes = [float(b.close) for b in list(bars)[-self.period:]]
        m = mean(closes)
        s = stdev(closes) if len(closes) > 1 else 0
        if s == 0:
            return Signal(0.0, "NO_SIGNAL")
        upper = m + self.std_mult * s
        lower = m - self.std_mult * s
        price = float(bar.close)
        # 偏离度：(price - mean) / (std_mult * std)，clip 到 [-1,+1]
        deviation = (price - m) / (self.std_mult * s)
        if price < lower:
            # 低于下轨 → 做多信号，偏离越远越强
            return Signal(Signal._clamp(0.5 + abs(deviation - 1) * 0.3), "BOLL_LOWER")
        elif price > upper:
            # 高于上轨 → 做空信号，偏离越远越强
            return Signal(Signal._clamp(-0.5 - abs(deviation - 1) * 0.3), "BOLL_UPPER")
        return Signal(0.0, "NO_SIGNAL")
