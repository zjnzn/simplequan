"""Bootstrap —— Netty 风格客户端启动器。

三阶段：声明依赖 -> bind 订阅 -> on_accept 构建 Channel。

bind() 订阅 connector 的回报 topic：
  - account/master  → 缓存 MasterAccount
  - market/symbol/* → 缓存 Symbol 并触发对应 channel 构建
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from app.cache.memory import MemoryCache
from app.channel.channel import SymbolChannel
from app.eventbus.eventbus import ChannelEventBus
from app.pipline.pipline import ChannelPipeline
from core.domain.account import MasterAccount, Position, SubAccount
from core.domain.config import AppConfig, ChannelConfig
from core.domain.symbol import Symbol
from core.ports.pipline import Pipeline

logger = logging.getLogger(__name__)


class ChannelInitializer(ABC):
    """Handler 初始化器 —— 每个 Channel 创建时回调。

    子类实现 init_channel() 往 Pipeline 添加 Handler。
    """

    @abstractmethod
    def init_channel(self, pipeline: Pipeline) -> None:
        ...


class Bootstrap:
    """Netty 风格客户端 Bootstrap。

    三阶段：声明 -> 组装 -> 启动。
    """

    def __init__(self, app_config: AppConfig):
        self._app_config = app_config
        self._initializer: Optional[ChannelInitializer] = None
        self._channels: dict[str, SymbolChannel] = {}
        self._bus = ChannelEventBus()
        self._cache = MemoryCache()
        self._master: MasterAccount | None = None
        self._master_ready: asyncio.Future[MasterAccount] | None = None

    def bus(self, bus: ChannelEventBus) -> Bootstrap:
        """注入外部 EventBus（与 connector 共用同一个 bus）。"""
        self._bus = bus
        return self

    # ============================================================
    # Phase 1: 声明依赖（链式配置）
    # ============================================================

    def group(self, account_mgr) -> Bootstrap:
        """设置账户管理器（类似 Netty 的 EventLoopGroup）。"""
        return self

    def childHandler(self, initializer: ChannelInitializer) -> Bootstrap:
        """设置 Channel 初始化器（类似 Netty 的 ChannelInitializer）。"""
        self._initializer = initializer
        return self

    async def wait_master_ready(self) -> MasterAccount:
        """等待 MasterAccount 回报就绪。"""
        if self._master is not None:
            return self._master
        if self._master_ready is None:
            self._master_ready = asyncio.get_running_loop().create_future()
        return await self._master_ready

    def bind(self) -> Bootstrap:
        """订阅 connector 回报 topic。"""
        self._bus.on("account/master", self._on_master)
        self._bus.on("market/symbol/*", self._on_symbol)
        return self

    # ============================================================
    # Phase 2: 回报处理 + Channel 构建
    # ============================================================

    async def _on_master(self, topic: str, master: MasterAccount) -> None:
        """缓存 MasterAccount，并唤醒等待者。"""
        self._master = master
        await self._cache.set("account/master", master)
        if self._master_ready is not None and not self._master_ready.done():
            self._master_ready.set_result(master)
        logger.info(
            "收到 MasterAccount: %s 余额=%s 持仓=%d 杠杆=%d",
            master.account_id, master.balance.total,
            len(master.positions), len(master.leverages),
        )

    async def _on_symbol(self, topic: str, sym: Symbol) -> None:
        """收到 Symbol 后缓存，并为对应的 symbol@timeframe 构建一个 channel。

        topic 格式: market/symbol/{symbol}@{interval}
        一次 fetch_symbol 只创建一个 channel（对应一个 ChannelConfig）。
        """
        if sym is None:
            return
        # 从 topic 解析 channel_id（symbol@interval）
        channel_id = topic.split("market/symbol/", 1)[1]
        cfg = self._app_config.by_channel_id().get(channel_id)
        if cfg is None:
            logger.warning("未找到 ChannelConfig: %s", channel_id)
            return
        await self._cache.set(f"symbol/{sym.symbol}", sym)
        logger.info("收到 Symbol: %s market=%s → %s", sym.symbol, sym.market, channel_id)
        await self.on_accept(sym, cfg)

    async def on_accept(self, symbol: Symbol, cfg: ChannelConfig) -> SymbolChannel:
        """构建 Channel（两步构造解决 pipeline 循环依赖）。

        从 MasterAccount 取该 symbol 的持仓/杠杆，创建 Channel 维度的 SubAccount
       （account_id = channel_id，即 symbol@timeframe）。
        """
        # 1. 创建 Channel 维度 SubAccount
        sub = None
        if self._master:
            allocated = self._master.balance.total * Decimal(str(cfg.allocation))
            master_pos = self._master.get_position(symbol.symbol)
            # 深拷贝 Position：master 可能已持仓，共享引用会导致多 channel 持仓串台
            sub = SubAccount(
                account_id=cfg.channel_id,
                master_id=self._master.account_id,
                symbol=symbol.symbol,
                allocated_balance=allocated,
                position=Position(
                    side=master_pos.side,
                    qty=master_pos.qty,
                    avg_price=master_pos.avg_price,
                    unrealized_pnl=master_pos.unrealized_pnl,
                ),
                leverage_config=self._master.get_leverage(symbol.symbol),
            )
            self._master = self._master.add_sub_account(sub)
        # 2. 先建 channel（pipeline=None 占位）
        ch = SymbolChannel(
            self._bus, cfg, symbol, cfg.market,
            pipeline=None, sub_account=sub,
        )
        # 3. 建 pipeline 绑定 channel，再回填
        pipeline = ChannelPipeline(ch)
        ch.pipeline = pipeline
        # 4. initializer 往 pipeline 塞 handler
        if self._initializer:
            self._initializer.init_channel(pipeline)
        # 5. 订阅数据流（kline 触发 connector 的 _kline_loop；order 订阅订单回报）
        ch.read("kline", cfg.interval)
        ch.read("order")
        # 6. 注册
        self._channels[ch.id] = ch
        logger.info("构建 Channel: %s [%s@%s]", ch.id, symbol.symbol, cfg.interval)
        return ch
