from src.handlers.signal_types import Signal


class RsiMacdStrategy:
    """RSI+MACD 策略。超买超卖时输出固定 ±0.6 中等偏强信号。"""

    name = "rsi_macd"
    version = "1.0.0"
    required_indicators = ["rsi_14"]

    def __init__(self, params: dict | None = None):
        p = params or {}
        self.rsi_oversold = p.get("rsi_oversold", 30)
        self.rsi_overbought = p.get("rsi_overbought", 70)

    async def on_bar(self, bar, ctx) -> Signal | None:
        indicators = ctx.market.indicators.get(bar.interval, {})
        rsi = indicators.get("rsi_14")
        if rsi is None:
            return None
        if float(rsi) < self.rsi_oversold:
            return Signal(0.6, "RSI_OVERSOLD")
        elif float(rsi) > self.rsi_overbought:
            return Signal(-0.6, "RSI_OVERBOUGHT")
        return Signal(0.0, "NO_SIGNAL")
