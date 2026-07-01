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
    """入站：ccxt OHLCV → Bar dataclass。只处理 KLINE 事件。"""

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = self._parse_ohlcv(event.payload, event.symbol)
        if bar is None:
            logger.debug("解析失败: symbol=%s payload类型=%s", event.symbol, type(event.payload).__name__)
            return
        logger.debug("解析K线: %s %s 收盘=%s 成交量=%s", bar.symbol, bar.interval, bar.close, bar.volume)
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, bar))

    def _parse_ohlcv(self, raw: Any, symbol: str) -> Bar | None:
        """解析 ccxt watch_ohlcv 返回的 OHLCV 格式。

        ExchangeConnector 传入: {"timeframe": "1m", "ohlcv": [[ts, o, h, l, c, v], ...]}
        也兼容裸 list 格式: [[ts, o, h, l, c, v], ...] 或 [ts, o, h, l, c, v]
        """
        timeframe = ""
        ohlcv = raw

        # dict 格式: {"timeframe": "1m", "ohlcv": [...]}
        if isinstance(raw, dict) and "ohlcv" in raw:
            timeframe = raw.get("timeframe", "")
            ohlcv = raw["ohlcv"]

        if not isinstance(ohlcv, list) or len(ohlcv) == 0:
            return None

        # [[ts, o, h, l, c, v], ...] → 取最后一根
        row = ohlcv[-1] if isinstance(ohlcv[-1], list) else ohlcv
        if len(row) < 6:
            return None

        return Bar(
            symbol=symbol,
            interval=timeframe,
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            timestamp=int(row[0]),
        )
