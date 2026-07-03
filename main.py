import asyncio
import logging

from app.eventbus.eventbus import ChannelEventBus
from app.exchange.connector import ExchangeConnector
from app.exchange.simulated import SimulatedExchange
from app.exchange.hybrid import HybridExchange
from app.handler.data_parse import DataParseHandler
from app.handler.data_process import DataProcessHandler
from app.handler.order_accepted import OrderAcceptedHandler
from app.handler.order_encode import OrderEncodeHandler
from app.handler.order_result import OrderResultHandler
from app.handler.position_calc import PositionCalcHandler
from app.handler.risk_post import RiskPostCheckHandler
from app.handler.risk_pre import RiskPreCheckHandler
from app.handler.signal import SignalHandler
from app.middleware.amount_check import AmountCheckMiddleware
from app.middleware.daily_loss import DailyLossMiddleware
from app.middleware.drawdown import DrawdownMiddleware
from app.middleware.max_leverage import MaxLeverageMiddleware
from app.middleware.min_notional import MinNotionalMiddleware
from app.middleware.per_order_ratio import PerOrderRatioMiddleware
from app.middleware.position_tolerance import PositionToleranceMiddleware
from app.middleware.signal_strength import SignalStrengthMiddleware
from app.pipline.risk import RiskPipeline
from app.indicator.registry import IndicatorLoader, IndicatorRegistry
from app.strategy.registry import StrategyLoader, StrategyRegistry
from app.bootstrap import Bootstrap, ChannelInitializer
from app.monitor import Monitor
from core.domain.config import load_config
from core.ports.pipline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_default_pre_pipeline() -> RiskPipeline:
    """构建默认 Pre 风控管道。"""
    return RiskPipeline([
        SignalStrengthMiddleware(min_strength=0.03),
        DailyLossMiddleware(),
        DrawdownMiddleware(),
    ])


def build_default_post_pipeline() -> RiskPipeline:
    """构建默认 Post 风控管道（与原 RiskPostCheckHandler 行为一致）。"""
    return RiskPipeline([
        MinNotionalMiddleware(),
        PositionToleranceMiddleware(tolerance=0.15),
        AmountCheckMiddleware(),
        MaxLeverageMiddleware(),
        PerOrderRatioMiddleware(),
    ])

class TradingChannelInitializer(ChannelInitializer):
    """交易 Pipeline 初始化器 —— 组装 Handler 链。

    无状态模板模式：strategies/indicators 注册表在 main() 中一次性加载所有类对象
    （全局共享），handler 从 ctx.channel.config 取配置，调用时注入 params，
    默认值由策略/指标类内 params.get(k, 默认) 兜底。
    """

    def __init__(self, strategy_registry: StrategyRegistry,
                 indicator_registry: IndicatorRegistry) -> None:
        self._strategy_registry = strategy_registry
        self._indicator_registry = indicator_registry

    def init_channel(self, pipeline: Pipeline) -> None:
        pipeline.add_last("DataParse", DataParseHandler())
        pipeline.add_last("DataProcess", DataProcessHandler(self._indicator_registry))
        pipeline.add_last("Signal", SignalHandler(self._strategy_registry))
        pipeline.add_last("RiskPre", RiskPreCheckHandler(build_default_pre_pipeline()))
        pipeline.add_last("PositionCalc", PositionCalcHandler())
        pipeline.add_last("RiskPost", RiskPostCheckHandler(build_default_post_pipeline()))
        pipeline.add_last("OrderEncode", OrderEncodeHandler())
        pipeline.add_last("OrderAccepted", OrderAcceptedHandler())
        pipeline.add_last("OrderResult", OrderResultHandler())


async def main() -> None:
    cfg = load_config()
    bus = ChannelEventBus()
    if cfg.exchange.mode == "hybrid":
        exchange = HybridExchange(cfg.exchange, cfg)
        print(f"交易所模式: hybrid（真实行情+虚拟撮合）交易所={cfg.exchange.name}")
    else:
        exchange = SimulatedExchange(cfg.exchange, cfg)
        print("交易所模式: simulated（纯内存模拟）")
    connector = ExchangeConnector(exchange, bus)

    # 一次性加载所有策略/指标类到全局注册表（无状态模板，全局共享）
    strategy_registry = StrategyRegistry()
    for strat_def in cfg.strategies.values():
        StrategyLoader(strategy_registry).load_module(strat_def.module)
    indicator_registry = IndicatorRegistry()
    for ind_def in cfg.indicators.values():
        IndicatorLoader(indicator_registry).load_module(ind_def.module)

    boot = Bootstrap(cfg).childHandler(
        TradingChannelInitializer(strategy_registry, indicator_registry)
    ).bus(bus).bind()

    # 1. 拉主账号（异步回报），等待就绪后再拉 symbol，避免 _master 为 None
    symbols = list({c.symbol for c in cfg.channels})
    await bus.emit("command/fetch_account",
                   {"symbols": symbols, "account_id": "master"})
    await boot.wait_master_ready()

    # 2. 每个 symbol@timeframe 各发一次 fetch_symbol，回报后 bootstrap 自动建 channel
    for c in cfg.channels:
        await bus.emit("command/fetch_symbol", {
            "symbol": c.symbol, "market": c.market, "interval": c.interval,
        })

    # 3. 启动监控器（HTTP 服务 + bus 订阅采集）
    monitor = Monitor(boot, bus)
    monitor.start()

    # 4. 等待数据流驱动 handler 链，监控器持续对外服务
    print(f"channels: {len(boot._channels)}  监控器: http://localhost:8080")
    print("  GET /ui         前端监控面板（推荐）")
    print("  GET /            总览 JSON")
    print("  GET /channels    channel 列表")
    print("  GET /channels/{cid}  单 channel 详情")
    print("  GET /channels/{cid}/signals?limit=5  历史信号")
    print("  GET /master      主账号")
    print("按 Ctrl+C 退出")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await exchange.close()
        await connector.close()


if __name__ == "__main__":
    asyncio.run(main())
