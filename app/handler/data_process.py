import logging

from app.indicator.registry import IndicatorRegistry
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class DataProcessHandler(Handler):
    """入站：row dict → 追加到 DataFrame → 调用指标计算器 → 合并指标值到 row dict。

    无状态模板模式：注册表缓存指标类对象，handler 从 ctx.channel.config 取
    indicator 配置，调用时注入 params，默认值由指标类内 params.get(k, 默认) 兜底。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: IndicatorRegistry | None = None) -> None:
        self._registry = registry or IndicatorRegistry()
        self._calc_cache: dict[str, object] = {}

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        interval = row.get("interval", "")
        if not interval:
            await ctx.fire_channel_read(event)
            return

        market = ctx.channel.market
        df = market.append_bar(interval, row)

        # 计算指标
        result = {}
        for ind_cfg in ctx.channel.config.strategy.indicators:
            cache_key = f"{ind_cfg.name}:{sorted(ind_cfg.params.items())}"
            try:
                calc = self._calc_cache.get(cache_key)
                if calc is None:
                    calc_cls = self._registry.get(ind_cfg.name)
                    calc = calc_cls()
                    self._calc_cache[cache_key] = calc
                result.update(calc.compute(df, ind_cfg.params))
            except KeyError:
                logger.warning("指标 '%s' 未在 indicators 注册表中声明，跳过", ind_cfg.name)
            except Exception:
                logger.warning("指标计算器 %s 异常，跳过", ind_cfg.name, exc_info=True)

        # 回写到 DataFrame 列（持久化）
        idx = df.index[-1]
        for k, v in result.items():
            if v is not None:
                df.loc[idx, k] = float(v) if hasattr(v, "__float__") else v

        # 合并指标值到 row dict
        enriched = {**row, **result}
        logger.debug("指标计算 %s@%s: %s", row.get("symbol", ""), interval, result)
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, enriched))
