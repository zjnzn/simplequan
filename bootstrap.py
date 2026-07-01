
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.cache.memory import Cache, MemoryCache
from app.channel.channel import SymbolChannel
from app.eventbus.eventbus import ChannelEventBus
from core.ports.channel import Channel
from core.ports.database import Database
from core.ports.eventbus import EventBus
from utils.config import Config



class ChannelInitializer(ABC):
    """Handler 初始化器 -- 每个 Channel 创建时回调。

    子类实现 init_channel() 往 Pipeline 添加 Handler。
    """

    @abstractmethod
    def init_channel(self, pipeline: ChannelPipeline) -> None:
        ...


class Bootstrap:
    """Netty 风格客户端 Bootstrap。

    三阶段：声明 -> 组装 -> 启动。
    """

    def __init__(self):
        self._initializer: Optional[ChannelInitializer] = None
        self._channels: Dict[str, Channel] = {}
        self._bus = ChannelEventBus()
        self._cache = MemoryCache()

    # ============================================================
    # Phase 1: 声明依赖（链式配置）
    # ============================================================

    def group(self, account_mgr) -> Bootstrap:
        """设置账户管理器（类似 Netty 的 EventLoopGroup）。"""
        self._account_mgr = account_mgr
        return self

    def childHandler(self, initializer: ChannelInitializer) -> Bootstrap:
        """设置 Channel 初始化器（类似 Netty 的 ChannelInitializer）。"""
        self._initializer = initializer
        return self
    
    def bind(self) -> Bootstrap:
        self._bus.on()
        return self

    # ============================================================
    # Phase 2: 组装 Channel + Pipeline
    # ============================================================

    def on_accept(self, symbol: str, cfg: Config) -> List[Channel]:

        market = cfg.market


        ch = SymbolChannel(self._bus,cfg, symbol, market,pipeline,symbol,market)
        pipeline = ch.pipeline

