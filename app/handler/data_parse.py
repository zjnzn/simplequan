import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


@dataclass
class Bar:
    symbol: str
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: int


class DataParseHandler(Handler):
    """入站：ccxt OHLCV → Bar dataclass。只处理 KLINE 事件。

    批量预热：首次拉取返回大量历史K线（limit=500），前 N-1 根直接注入
    market.bars 绕过 handler 链，仅最后一根触发完整 pipeline。
    后续增量轮询返回 1~2 根，按 timestamp 去重后正常处理。
    """

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bars = self._parse_all(event.payload, event.symbol)
        if not bars:
            return

        market = ctx.channel.market
        interval = bars[0].interval
        market_bars = market.ensure_bars(interval)

        # 找出 deque 中尚未存在的新 bar（按 timestamp 去重）
        last_ts = market_bars[-1].timestamp if market_bars else 0
        new_bars = [b for b in bars if b.timestamp > last_ts]

        if not new_bars:
            return

        # 除最后一根外，全部直接注入 deque（绕过 pipeline）
        for bar in new_bars[:-1]:
            market_bars.append(bar)
            last_ts = bar.timestamp

        # 最后一根走完整 pipeline
        last = new_bars[-1]
        logger.debug("K线入站 %s@%s: %d 根中 %d 根新 bar",
                     event.symbol, interval, len(bars), len(new_bars))
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, last))

    def _parse_all(self, raw: Any, symbol: str) -> list[Bar]:
        """解析 ccxt OHLCV 列表 → Bar 列表。

        dict 格式: {"timeframe": "1m", "ohlcv": [[ts,o,h,l,c,v], ...]}
        也兼容裸 list: [[ts,o,h,l,c,v], ...]
        """
        timeframe = ""
        ohlcv = raw

        if isinstance(raw, dict) and "ohlcv" in raw:
            timeframe = raw.get("timeframe", "")
            ohlcv = raw["ohlcv"]

        if not isinstance(ohlcv, list) or len(ohlcv) == 0:
            return []

        # [[ts,o,h,l,c,v], ...] 或 [ts,o,h,l,c,v]
        rows = ohlcv if isinstance(ohlcv[0], list) else [ohlcv]
        bars: list[Bar] = []
        for row in rows:
            if len(row) < 6:
                continue
            bars.append(Bar(
                symbol=symbol,
                interval=timeframe,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
                timestamp=int(row[0]),
            ))
        return bars
