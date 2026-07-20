"""MarketRegimeHandler — ADX市场状态分类 + DMI方向过滤。

依赖: df 中已存在 adx, dmi_dir 列 (由前置 DataProcess 计算)。
产出: market_state (strong_trend/moderate_trend/weak_trend/range)
      range_allowed (bool, DMI中性时震荡策略可交易)
"""
from __future__ import annotations

import logging

import numpy as np

from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class MarketRegimeHandler(Handler):
    """入站：计算市场状态列 → 追加到 df 和 row dict。

    ADX阈值 (归一化):
      strong_trend:   ADX > 0.5  (>25)
      moderate_trend: ADX 0.4-0.5 (20-25)
      weak_trend:     ADX 0.3-0.4 (15-20)
      range:          ADX ≤ 0.3  (<15)

    DMI方向过滤: |dmi_dir| < threshold → range_allowed=True
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, adx_smooth: int = 8, dmi_threshold: float = 0.15) -> None:
        self._adx_smooth = adx_smooth
        self._dmi_threshold = dmi_threshold

    def _classify(self, df):
        """对整个 df 计算 market_state 和 range_allowed 最新值。

        对齐 cl add_market_state: 当 adx_smooth > 1 时，用平滑后的值覆盖
        df["adx"]（策略 route 依赖 df["adx"] 做入场过滤）。
        """
        adx = df["adx"]
        if self._adx_smooth > 1:
            adx = adx.ewm(span=self._adx_smooth, adjust=False).mean()
            df["adx"] = adx  # 对齐 cl: 覆盖为平滑值

        adx_v = adx.values
        conditions = [
            adx_v > 0.5,
            (adx_v > 0.4) & (adx_v <= 0.5),
            (adx_v > 0.3) & (adx_v <= 0.4),
        ]
        choices = ["strong_trend", "moderate_trend", "weak_trend"]
        market_state = np.select(conditions, choices, default="range")

        range_allowed = np.abs(df["dmi_dir"].values) < self._dmi_threshold

        return market_state[-1], range_allowed[-1]

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        interval = row.get("interval", "")
        df = ctx.channel.market.bars.get(interval)
        if df is None or len(df) < 30:
            await ctx.fire_channel_read(event)
            return

        if "adx" not in df.columns or "dmi_dir" not in df.columns:
            logger.debug("缺少 adx/dmi_dir 列，跳过 market_regime")
            await ctx.fire_channel_read(event)
            return

        state, allowed = self._classify(df)

        # 回写到 df
        idx = df.index[-1]
        df.loc[idx, "market_state"] = state
        df.loc[idx, "range_allowed"] = bool(allowed)

        enriched = {**row, "market_state": state, "range_allowed": bool(allowed)}
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, enriched))
