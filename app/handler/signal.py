import logging

from src.core.context import ChannelHandlerContext
from src.core.event_bus import ChannelEvent, EventType
from src.core.handler import ChannelHandler
from src.handlers.signal_types import Signal
from src.strategies.registry import StrategyRegistry

# 重新导出 Signal
__all__ = ["Signal", "SignalHandler"]

logger = logging.getLogger(__name__)


class SignalHandler(ChannelHandler):
    """入站：策略调度器 —— 遍历 StrategyRegistry 中的策略，首个非零信号即采用。"""

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: StrategyRegistry | None = None):
        self._registry = registry or StrategyRegistry()

    async def channel_read(self, ctx: ChannelHandlerContext, event: ChannelEvent) -> None:
        bar = event.payload
        signal = None

        for strategy in self._registry.all():
            try:
                result = await strategy.on_bar(bar, ctx)
                if result and result.value != 0:
                    signal = result
                    break
            except Exception:
                logger.warning("策略 %s 异常，跳过", strategy.name, exc_info=True)

        if signal is None:
            signal = Signal(0.0, "NO_SIGNAL")

        ctx.market.current_signal = signal
        logger.info("信号: %s %s 强度=%.4f 原因=%s",
                     signal.direction, event.symbol, signal.strength, signal.reason)
        await ctx.fire_channel_read(ChannelEvent(EventType.KLINE, event.symbol, signal))
