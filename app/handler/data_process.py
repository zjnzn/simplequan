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
        # indicators 参数保留向后兼容（旧测试/调用方），但不再使用
        self._registry = registry or IndicatorRegistry()

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = event.payload
        interval = bar.interval
        if interval not in ctx.market.bars or ctx.market.bars[interval] is None:
            ctx.market.bars[interval] = deque(maxlen=500)
        ctx.market.bars[interval].append(bar)

        result = {}
        for calc in self._registry.all():
            try:
                result.update(calc.compute(ctx.market.bars[interval]))
            except Exception:
                logger.warning("指标计算器 %s 异常，跳过", calc.name, exc_info=True)

        ctx.market.indicators[interval] = result
        logger.debug("指标计算 %s[%s]: %s", bar.symbol, interval, ctx.market.indicators[interval])
        await ctx.fire_channel_read(event)
