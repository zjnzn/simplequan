"""MarketRegimeHandler — ADX市场状态分类 + DMI方向过滤.

依赖: df 中已存在 adx, dmi_dir 列 (由前置 DataProcess 计算).
产出: market_state (strong_trend/moderate_trend/weak_trend/range)
      range_allowed (bool, DMI中性时震荡策略可交易)

使用 expanding 百分位排名进行动态分类, 避免固定阈值在加密市场 ADX 偏高时丢失区分度.
"""
from __future__ import annotations

import logging

from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class MarketRegimeHandler(Handler):
    """入站: 计算 market_state / range_allowed → 追加到 df 和 row dict."""

    handles = frozenset({EventType.KLINE})

    def __init__(self, adx_smooth: int = 8, dmi_threshold: float = 0.15) -> None:
        self._adx_smooth = adx_smooth
        self._dmi_threshold = dmi_threshold

    def _classify(self, df):
        """expanding 百分位排名动态分类.

        strong_trend:   rank > 0.70  (top 30%)
        moderate_trend: rank 0.40-0.70
        weak_trend:     rank 0.20-0.40
        range:          rank ≤ 0.20  (bottom 20%)
        """
        import numpy as np

        adx = df["adx"]
        if self._adx_smooth > 1:
            adx = adx.ewm(span=self._adx_smooth, adjust=False).mean()
            df["adx"] = adx

        rank = adx.expanding(min_periods=100).rank(pct=True)
        rv = rank.values
        conditions = [
            rv > 0.70,
            (rv > 0.40) & (rv <= 0.70),
            (rv > 0.20) & (rv <= 0.40),
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

        idx = df.index[-1]
        df.loc[idx, "market_state"] = state
        df.loc[idx, "range_allowed"] = bool(allowed)

        enriched = {**row, "market_state": state, "range_allowed": bool(allowed)}
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, enriched))
