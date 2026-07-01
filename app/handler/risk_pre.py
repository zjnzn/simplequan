import logging

from app.pipline.risk import RiskPipeline
from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class RiskPreCheckHandler(Handler):
    """入站：交易信号风控检查。通过 RiskPipeline 委托中间件链。"""

    handles = frozenset({EventType.KLINE})

    def __init__(self, pipeline: RiskPipeline | None = None) -> None:
        self._pipeline = pipeline or RiskPipeline([])

    async def channel_read(self, ctx: Context, event: Event) -> None:
        signal = event.payload
        if not hasattr(signal, "direction"):
            await ctx.fire_channel_read(event)
            return

        if signal.direction == "HOLD":
            await ctx.fire_channel_read(event)
            return

        result = await self._pipeline.check(signal, ctx)
        if result.passed:
            logger.debug("Pre风控通过: %s", signal.direction)
            await ctx.fire_channel_read(event)
        else:
            logger.warning("Pre风控拒绝: %s", result.reason)
