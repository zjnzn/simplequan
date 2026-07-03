"""Monitor 存储 —— 每个 channel 一条记录，有界 deque 存历史。"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelRecord:
    """单 channel 的历史数据记录，各序列有界 500。"""

    channel_id: str
    symbol: str
    interval: str

    klines: deque = field(default_factory=lambda: deque(maxlen=500))
    indicators: deque = field(default_factory=lambda: deque(maxlen=500))
    signals: deque = field(default_factory=lambda: deque(maxlen=500))
    orders: deque = field(default_factory=lambda: deque(maxlen=500))

    def snapshot(self) -> dict[str, Any]:
        """当前快照（不含历史，用于总览）。"""
        return {
            "channel_id": self.channel_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "klines_count": len(self.klines),
            "indicators_count": len(self.indicators),
            "signals_count": len(self.signals),
            "orders_count": len(self.orders),
        }
