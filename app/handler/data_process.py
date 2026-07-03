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

    性能优化：计算器实例按 name 缓存，避免逐 bar 重复实例化。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: IndicatorRegistry | None = None) -> None:
        self._registry = registry or IndicatorRegistry()
        # 缓存已实例化的计算器，避免逐 bar 重复创建
        self._calc_cache: dict[str, object] = {}

    async def channel_read(self, ctx: Context, event: Event) -> None:
        bar = event.payload
        interval = bar.interval
        market = ctx.channel.market
        bars = market.ensure_bars(interval)
        bars.append(bar)

        result = {}
        for ind_cfg in ctx.channel.config.strategy.indicators:
            cache_key = f"{ind_cfg.name}:{sorted(ind_cfg.params.items())}"
            try:
                calc = self._calc_cache.get(cache_key)
                if calc is None:
                    calc_cls = self._registry.get(ind_cfg.name)
                    calc = calc_cls()
                    self._calc_cache[cache_key] = calc
                result.update(calc.compute(bars, ind_cfg.params))
            except KeyError:
                logger.warning("指标 '%s' 未在 indicators 注册表中声明，跳过", ind_cfg.name)
            except Exception:
                logger.warning("指标计算器 %s 异常，跳过", ind_cfg.name, exc_info=True)

        market.indicators[interval] = result
        logger.debug("指标计算 %s@%s: %s", bar.symbol, interval, result)
        await ctx.fire_channel_read(event)
