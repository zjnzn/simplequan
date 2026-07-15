import logging
from typing import Any

import pandas as pd

from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class DataParseHandler(Handler):
    """入站：ccxt OHLCV → DataFrame → emit 最新行 dict。

    批量预热：首次拉取返回大量历史K线，前 N-1 根直接注入
    market.bars 绕过 handler 链，仅最后一根触发完整 pipeline。
    后续增量轮询返回 1~2 根，按 timestamp 去重后正常处理。
    """

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        df = self._parse_all(event.payload, event.symbol)
        if df is None or len(df) == 0:
            return

        market = ctx.channel.market
        interval = df["interval"].iloc[0] if "interval" in df.columns else ""
        if not interval:
            return

        market_df = market.ensure_bars(interval)

        # 按 timestamp 去重
        last_ts = int(market_df["timestamp"].iloc[-1]) if len(market_df) > 0 else 0
        new_df = df[df["timestamp"] > last_ts]
        if len(new_df) == 0:
            return

        # 除最后一根外，全部直接注入 DataFrame（绕过 pipeline）
        if len(new_df) > 1:
            for _, row in new_df.iloc[:-1].iterrows():
                market_df = market.append_bar(interval, row.to_dict())

        # 最后一根走完整 pipeline
        last_row = new_df.iloc[-1].to_dict()
        logger.debug("K线入站 %s@%s: %d 根中 %d 根新 bar",
                     event.symbol, interval, len(df), len(new_df))
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, last_row))

    def _parse_all(self, raw: Any, symbol: str) -> pd.DataFrame | None:
        """解析 ccxt OHLCV 列表 → DataFrame。

        dict 格式: {"timeframe": "1m", "ohlcv": [[ts,o,h,l,c,v], ...]}
        也兼容裸 list: [[ts,o,h,l,c,v], ...]
        """
        timeframe = ""
        ohlcv = raw

        if isinstance(raw, dict) and "ohlcv" in raw:
            timeframe = raw.get("timeframe", "")
            ohlcv = raw["ohlcv"]

        if not isinstance(ohlcv, list) or len(ohlcv) == 0:
            return None

        rows = ohlcv if isinstance(ohlcv[0], list) else [ohlcv]
        data = []
        for row in rows:
            if len(row) < 6:
                continue
            data.append({
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })

        if not data:
            return None

        df = pd.DataFrame(data)
        if timeframe:
            df["interval"] = timeframe
        return df
