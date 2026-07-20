import logging

from app.pipline.risk import RiskPipeline
from core.domain.event import Event, EventType
from core.domain.signal import Signal
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class RiskPreCheckHandler(Handler):
    """入站：交易信号风控检查。通过 RiskPipeline 委托中间件链。

    离场信号 (signal_type=="exit") 放行，不经过入场风控。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, pipeline: RiskPipeline | None = None) -> None:
        self._pipeline = pipeline or RiskPipeline([])

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        signal_value = row.get("signal_value", 0.0)
        signal_reason = row.get("signal_reason", "NO_SIGNAL")
        signal_type = row.get("signal_type", "entry")
        signal = Signal(signal_value, signal_reason, signal_type)

        if signal.direction == "HOLD":
            await ctx.fire_channel_read(event)
            return

        # 离场信号放行（平仓不应被风控拦截）
        if signal.signal_type == "exit":
            logger.debug("离场信号放行: reason=%s", signal_reason)
            await ctx.fire_channel_read(event)
            return

        result = await self._pipeline.check(signal, ctx)
        if result.passed:
            logger.debug("Pre风控通过: %s", signal.direction)
            await ctx.fire_channel_read(event)
        else:
            logger.warning("Pre风控拒绝: %s", result.reason)
