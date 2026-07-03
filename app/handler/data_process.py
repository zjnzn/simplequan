import logging

from app.indicator.registry import IndicatorRegistry
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler


logger = logging.getLogger(__name__)


class DataProcessHandler(Handler):
    """入站：Bar → 委托给指标类计算，存入 ctx.market。只处理 KLINE 事件。

    无状态模板模式：注册表缓存指标类对象，handler 从 ctx.channel.config 取
    indicator 配置，调用时注入 params，默认值由指标类内 params.get(k, 默认) 兜底。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: IndicatorRegistry | None = None) -> None:
        self._registry = registry or IndicatorRegistry()

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = event.payload
        interval = bar.interval
        market = ctx.channel.market
        bars = market.ensure_bars(interval)
        bars.append(bar)

        result = {}
        for ind_cfg in ctx.channel.config.strategy.indicators:
            try:
                calc_cls = self._registry.get(ind_cfg.name)
                result.update(calc_cls().compute(bars, ind_cfg.params))
            except KeyError:
                logger.warning("指标 '%s' 未在 indicators 注册表中声明，跳过", ind_cfg.name)
            except Exception:
                logger.warning("指标计算器 %s 异常，跳过", ind_cfg.name, exc_info=True)

        market.indicators[interval] = result
        logger.debug("指标计算 %s@%s: %s", bar.symbol, interval, result)
        await ctx.fire_channel_read(event)
