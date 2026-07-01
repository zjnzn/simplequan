import logging

from src.core.context import ChannelHandlerContext
from src.core.event_bus import ChannelEvent, EventType
from src.core.handler import ChannelHandler
from src.risk.pipeline import RiskPipeline

logger = logging.getLogger(__name__)


class RiskPreCheckHandler(ChannelHandler):
    """入站：交易信号风控检查。通过 RiskPipeline 委托中间件链。"""

    handles = frozenset({EventType.KLINE})

    def __init__(self, pipeline: RiskPipeline | None = None) -> None:
        self._pipeline = pipeline or RiskPipeline([])

    async def channel_read(self, ctx: ChannelHandlerContext, event: ChannelEvent) -> None:
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
