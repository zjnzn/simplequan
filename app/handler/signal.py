import logging

from app.strategy.registry import StrategyRegistry
from core.domain.event import Event, EventType
from core.domain.signal import Signal
from core.ports.context import Context
from core.ports.handler import Handler

# 重新导出 Signal
__all__ = ["Signal", "SignalHandler"]

logger = logging.getLogger(__name__)


class SignalHandler(Handler):
    """入站：策略调度器 —— 从 ctx.channel.config 取策略配置，注入 params 后调用 on_bar。

    无状态模板模式：注册表缓存策略类对象，handler 调用时注入 channel 的 params，
    默认值由策略类内 params.get(k, 默认) 兜底。

    实例缓存：策略实例按 channel_id 缓存，保证 _prev_* 状态跨 bar 持续。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or StrategyRegistry()
        self._strat_cache: dict[str, object] = {}

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = event.payload
        strat_cfg = ctx.channel.config.strategy
        signal = None

        try:
            cache_key = ctx.channel.config.channel_id
            strat = self._strat_cache.get(cache_key)
            if strat is None:
                strat_cls = self._registry.get(strat_cfg.name)
                strat = strat_cls()
                self._strat_cache[cache_key] = strat
            result = await strat.on_bar(bar, ctx, strat_cfg.params)
            if result and result.value != 0:
                signal = result
        except KeyError:
            logger.warning("策略 '%s' 未在 strategies 注册表中声明", strat_cfg.name)
        except Exception:
            logger.warning("策略 %s 异常，跳过", strat_cfg.name, exc_info=True)

        if signal is None:
            signal = Signal(0.0, "NO_SIGNAL")

        ctx.channel.market.current_signal = signal
        logger.debug("信号: %s %s 强度=%.4f 原因=%s",
                     signal.direction, event.symbol, signal.strength, signal.reason)
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, signal))
