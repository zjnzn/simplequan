"""Market —— Channel 运行时市场状态。

每个 SymbolChannel 持有一个 MarketState，缓存 K 线序列、指标结果、当前信号。
入站 handler（DataProcess/Signal/PositionCalc）通过 ctx.channel.market 读写。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.domain.signal import Signal


@dataclass
class MarketState:
    """Channel 运行时市场状态。

    bars:        {interval: deque[Bar]}    K 线序列（按周期分桶）
    indicators:  {interval: dict[str, Decimal]}  指标计算结果
    current_signal: 最新信号（SignalHandler 写入）
    """
    bars: dict[str, deque] = field(default_factory=dict)
    indicators: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    current_signal: Signal | None = None

    def get_bars(self, interval: str) -> deque | None:
        return self.bars.get(interval)

    def ensure_bars(self, interval: str, maxlen: int = 500) -> deque:
        """获取指定周期的 bar 序列，不存在则创建。"""
        dq = self.bars.get(interval)
        if dq is None:
            dq = deque(maxlen=maxlen)
            self.bars[interval] = dq
        return dq

    def get_indicators(self, interval: str) -> dict[str, Decimal]:
        return self.indicators.get(interval, {})
