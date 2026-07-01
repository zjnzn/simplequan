import asyncio
import logging

from app.eventbus.eventbus import ChannelEventBus
from app.exchange.connector import ExchangeConnector
from app.exchange.simulated import SimulatedExchange
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
from app.middleware.global_loss import GlobalLossMiddleware
from app.middleware.max_leverage import MaxLeverageMiddleware
from app.middleware.per_order_ratio import PerOrderRatioMiddleware
from app.pipline.risk import RiskPipeline
from app.indicator.registry import IndicatorLoader, IndicatorRegistry
from app.strategy.bollinger import BollingerStrategy
from app.strategy.ma_cross import MaCrossStrategy
from app.strategy.registry import StrategyRegistry
from app.strategy.rsi_macd import RsiMacdStrategy
from bootstrap import Bootstrap, ChannelInitializer
from core.domain.config import load_config
from core.ports.pipline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# 策略名 → 策略类
_STRATEGY_MAP = {
    "ma_cross_over": MaCrossStrategy,
    "rsi_macd": RsiMacdStrategy,
    "bollinger_reversal": BollingerStrategy,
}

def build_default_pre_pipeline() -> RiskPipeline:
    """构建默认 Pre 风控管道（与原 RiskPreCheckHandler 行为一致）。"""
    return RiskPipeline([
        DailyLossMiddleware(),
        DrawdownMiddleware(),
        GlobalLossMiddleware(),
    ])


def build_default_post_pipeline() -> RiskPipeline:
    """构建默认 Post 风控管道（与原 RiskPostCheckHandler 行为一致）。"""
    return RiskPipeline([
        AmountCheckMiddleware(),
        MaxLeverageMiddleware(),
        PerOrderRatioMiddleware(),
    ])

class TradingChannelInitializer(ChannelInitializer):
    """交易 Pipeline 初始化器 —— 组装 Handler 链。"""

    def init_channel(self, pipeline: Pipeline) -> None:
        ch = pipeline.channel
        strat_cfg = ch.config.strategy

        # 从 config 加载策略
        registry = StrategyRegistry()
        strat_cls = _STRATEGY_MAP[strat_cfg.name]
        registry.register(strat_cls(strat_cfg.params))

        # 从 config 加载指标
        ind_registry = IndicatorRegistry()
        ind_loader = IndicatorLoader(ind_registry)
        for ind in strat_cfg.indicators:
            ind_loader.load_module(ind.module, ind.params)

        pipeline.add_last("DataParse", DataParseHandler())
        pipeline.add_last("DataProcess", DataProcessHandler(ind_registry))
        pipeline.add_last("Signal", SignalHandler(registry))
        pipeline.add_last("RiskPre", RiskPreCheckHandler(build_default_pre_pipeline()))
        pipeline.add_last("PositionCalc", PositionCalcHandler())
        pipeline.add_last("RiskPost", RiskPostCheckHandler(build_default_post_pipeline()))
        pipeline.add_last("OrderEncode", OrderEncodeHandler())
        pipeline.add_last("OrderAccepted", OrderAcceptedHandler())
        pipeline.add_last("OrderResult", OrderResultHandler())


async def main() -> None:
    cfg = load_config()
    bus = ChannelEventBus()
    exchange = SimulatedExchange(cfg.exchange, cfg)
    connector = ExchangeConnector(exchange, bus)
    boot = Bootstrap(cfg).childHandler(TradingChannelInitializer()).bus(bus).bind()

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

    # 3. 等待数据流驱动 handler 链
    await asyncio.sleep(1.0)
    print(f"channels: {len(boot._channels)}")
    for cid, ch in boot._channels.items():
        sub = ch.sub_account
        sub_id = sub.account_id if sub else "-"
        lev = sub.leverage_config.leverage if sub else 0
        print(f"  {cid[:8]}  {ch.symbol.symbol}@{ch.config.interval}  sub={sub_id}  lev={lev}x")

    if boot._master:
        m = boot._master
        print(f"master: {m.account_id} balance={m.balance.total} "
              f"positions={len(m.positions)} leverages={len(m.leverages)} "
              f"subs={len(m.sub_accounts)}")

    await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
