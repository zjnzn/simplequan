"""Market —— Channel 运行时市场状态。

每个 SymbolChannel 持有一个 MarketState，缓存 K 线 DataFrame、当前信号。
入站 handler（DataProcess/Signal/PositionCalc）通过 ctx.channel.market 读写。
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass, field

from core.domain.signal import Signal

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


@dataclass
class MarketState:
    """Channel 运行时市场状态。

    bars:       {interval: pd.DataFrame}   K 线序列（按周期分桶），列: timestamp/open/high/low/close/volume + 指标列 + 信号列
    current_signal: 最新信号（SignalHandler 写入）
    """

    bars: dict[str, pd.DataFrame] = field(default_factory=dict)
    current_signal: Signal | None = None

    def get_bars(self, interval: str) -> pd.DataFrame | None:
        return self.bars.get(interval)

    def ensure_bars(self, interval: str) -> pd.DataFrame:
        """获取指定周期的 bar DataFrame，不存在则创建空 DataFrame。"""
        df = self.bars.get(interval)
        if df is None:
            df = pd.DataFrame(columns=OHLCV_COLUMNS)
            self.bars[interval] = df
        return df

    def append_bar(self, interval: str, row: dict) -> pd.DataFrame:
        """追加一行 bar 数据到 DataFrame，返回更新后的 DataFrame。"""
        df = self.ensure_bars(interval)
        new_row = pd.DataFrame([row])
        if len(df) == 0:
            df = new_row
        else:
            df = pd.concat([df, new_row], ignore_index=True)
        if len(df) > 1000:
            df = df.iloc[-1000:]
        self.bars[interval] = df
        return df

    def latest_row(self, interval: str) -> dict | None:
        """获取最新一行数据（含指标/信号列），返回 dict 或 None。"""
        df = self.bars.get(interval)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-1].to_dict()
