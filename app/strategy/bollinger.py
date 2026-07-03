"""布林带均值回归 + 突破策略（对齐 project_refactored BollingerBandStrategy）。

带宽挤压后突破增强信号强度；触轨反弹/回落检测。
无强度过滤，信号过滤交由风控层处理。
"""
from __future__ import annotations

from collections import deque

from core.domain.signal import Signal


class BollingerStrategy:
    """布林带均值回归+突破策略。

    params:
        period:   布林带周期，默认 20
        std_dev:  标准差倍数，默认 2.0
    """

    name = "bollinger_reversal"
    version = "2.0.0"

    def __init__(self) -> None:
        self._prev_close: float | None = None
        self._prev_upper: float | None = None
        self._prev_lower: float | None = None
        self._bw_history: deque[float] = deque(maxlen=10)  # 挤压检测窗口

    def required_indicators(self, params: dict) -> list[str]:
        period = params.get("period", 20)
        return [f"bb_upper_{period}", f"bb_mid_{period}",
                f"bb_lower_{period}", f"bb_bandwidth_{period}"]

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        period = params.get("period", 20)
        indicators = ctx.channel.market.indicators.get(bar.interval, {})
        upper = indicators.get(f"bb_upper_{period}")
        lower = indicators.get(f"bb_lower_{period}")
        bw = indicators.get(f"bb_bandwidth_{period}")
        if upper is None or lower is None or bw is None:
            return None

        close = float(bar.close)
        u, l, b = float(upper), float(lower), float(bw)

        if self._prev_close is None:
            self._prev_close = close
            self._prev_upper = u
            self._prev_lower = l
            self._bw_history.append(b)
            return Signal(0.0, "INIT")

        pc = self._prev_close
        pu = self._prev_upper
        pl = self._prev_lower
        self._prev_close = close
        self._prev_upper = u
        self._prev_lower = l
        self._bw_history.append(b)

        # 带宽挤压检测：当前带宽 < 10根平均 → bonus = 0.3
        squeeze_bonus = 0.0
        if len(self._bw_history) == 10:
            avg_bw = sum(self._bw_history) / 10
            if b < avg_bw:
                squeeze_bonus = 0.3

        # 条件1：从下轨反弹（前一根收盘<=下轨，当前收盘>下轨）
        if pc <= pl and close > l:
            strength = Signal._clamp(0.7 + squeeze_bonus)
            return Signal(strength, "BOLL_BOUNCE_LOWER")

        # 条件2：从上轨回落
        if pc >= pu and close < u:
            strength = Signal._clamp(-(0.7 + squeeze_bonus))
            return Signal(strength, "BOLL_FALL_UPPER")

        # 条件3：价格在下轨下方（未反弹）
        if close < l:
            return Signal(0.5, "BOLL_BELOW_LOWER")

        # 条件4：价格在上轨上方（未回落）
        if close > u:
            return Signal(-0.5, "BOLL_ABOVE_UPPER")

        return Signal(0.0, "NO_SIGNAL")
