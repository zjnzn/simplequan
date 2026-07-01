import logging
from collections import deque

from app.indicator.registry import IndicatorRegistry
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler


logger = logging.getLogger(__name__)


class DataProcessHandler(Handler):
    """入站：Bar → 委托给 IndicatorRegistry 计算指标，存入 ctx.market。只处理 KLINE 事件。"""

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: IndicatorRegistry | None = None):
        self._registry = registry or IndicatorRegistry()

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = event.payload
        interval = bar.interval
        market = ctx.channel.market
        bars = market.ensure_bars(interval)
        bars.append(bar)

        result = {}
        for calc in self._registry.all():
            try:
                result.update(calc.compute(bars))
            except Exception:
                logger.warning("指标计算器 %s 异常，跳过", calc.name, exc_info=True)

        market.indicators[interval] = result
        logger.debug("指标计算 %s[%s]: %s", bar.symbol, interval, result)
        await ctx.fire_channel_read(event)
