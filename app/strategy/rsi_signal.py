from core.domain.signal import Signal


class RsiSignalStrategy:
    """RSI 超买超卖策略。信号 [-1,+1]：越极端越强，边界0.5，极限1.0。"""

    name = "rsi_signal"
    version = "1.0.0"
    required_indicators = ["rsi_14"]

    def __init__(self, params: dict | None = None):
        p = params or {}
        self.period = p.get("period", 14)
        self.overbought = p.get("overbought", 70)
        self.oversold = p.get("oversold", 30)

    async def on_bar(self, bar, ctx) -> Signal | None:
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        rsi = indicators.get(f"rsi_{self.period}")
        if rsi is None:
            return None
        rsi_val = float(rsi)
        if rsi_val >= self.overbought:
            # 超买：越接近100越强，边界70→0.5，100→1.0
            strength = (rsi_val - self.overbought) / (100 - self.overbought)
            return Signal(Signal._clamp(-0.5 - strength * 0.5), f"RSI_OVERBOUGHT_{rsi_val:.1f}")
        elif rsi_val <= self.oversold:
            # 超卖：越接近0越强，边界30→0.5，0→1.0
            strength = (self.oversold - rsi_val) / self.oversold
            return Signal(Signal._clamp(0.5 + strength * 0.5), f"RSI_OVERSOLD_{rsi_val:.1f}")
        return Signal(0.0, f"RSI_NEUTRAL_{rsi_val:.1f}")
