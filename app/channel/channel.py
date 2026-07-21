"""Channel —— 只认 EventBus，从不持有交易所对象。

每个 symbol 一个实例。通过 EventBus 订阅数据、发布指令。

Channel 不解析 topic、不映射 EventType —— 这些职责在 ExchangeConnector。
Channel listener 接收 ChannelEvent 对象，直接转发到 Pipeline。

Topic 协议：
  数据入站:  {market}/{feed}/{symbol}[@{param}]        spot/kline/BTC/USDT@1m
  订单回报:  {market}/order/{symbol}/{channel_id}/{event}  spot/order/BTC/USDT/{uuid}/filled
  错误通知:  {market}/error/{sym_compact}/{source}     spot/error/BTCUSDT/kline
  订阅请求:  request/{market}/{symbol}/{feed}         request/spot/BTC/USDT/kline-1m
  下单指令:  command/{market}/{symbol}/{cmd}/{channel_id}  command/spot/BTC/USDT/create_order/{uuid}
  取消订阅:  unsubscribe/{market}/{symbol}            unsubscribe/spot/BTC/USDT

  channel_id 确保订单回报只被创建它的 Channel 消费。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from core.domain.account import SubAccount
from core.domain.command import Command, CommandType
from core.domain.config import ChannelConfig
from core.domain.event import Event, EventType
from core.domain.market import MarketState
from core.domain.symbol import Symbol
from app.cache.memory import MemoryCache
from core.ports.channel import Channel
from core.ports.eventbus import BusHandler, EventBus
from core.ports.pipline import Pipeline


class SymbolChannel:
    """Netty 风格 Channel。只认 EventBus，不持有任何交易所连接。

    持有运行时状态：market（MarketState，K线/指标/信号）、sub_account（Channel 维度子账号）、
    cache（订单缓存）、bootstrap（跨Channel查询门）。handler 通过 ctx.channel.* 访问。
    """

    def __init__(
        self,
        bus: EventBus,
        config: ChannelConfig,
        symbol: Symbol,
        market_type: str,
        pipeline: Pipeline | None = None,
        sub_account: SubAccount | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.config = config
        self._pipeline: Pipeline | None = pipeline
        self.symbol = symbol
        self._bus = bus
        self.market_type = market_type       # "futures" / "spot"
        self.market = MarketState()          # 运行时市场状态
        self.sub_account = sub_account
        self.cache = MemoryCache()           # Channel 维度缓存（订单等）
        self.bootstrap = None                # Bootstrap 注入，跨TF门控查询

        self._activated = False
        self._subscribed: set[str] = set()

    @property
    def pipeline(self) -> Pipeline:
        """pipeline 后置注入：未注入时访问报错。"""
        if self._pipeline is None:
            raise RuntimeError(f"channel {self.id} pipeline 未注入")
        return self._pipeline

    @pipeline.setter
    def pipeline(self, p: Pipeline) -> None:
        self._pipeline = p

    # ---------------- 入站：订阅 EventBus 上的 data topic ----------------
    # ExchangeConnector 已将数据包装为 ChannelEvent，Channel 只转发

    def read(self, feed: str, timeframe: str = "") -> Channel:
        """订阅数据流。feed: kline / orderbook / trade / order"""
        sym = self.symbol.symbol
        topic = ""
        event_type = EventType.KLINE
        request = ""

        if feed == "kline":
            topic = f"{self.market_type}/kline/{sym}@{timeframe}"
            request = f"request/{self.market_type}/{sym}/kline-{timeframe}"
            event_type = EventType.KLINE
        elif feed == "orderbook":
            topic = f"{self.market_type}/orderbook/{sym}"
            request = f"request/{self.market_type}/{sym}/orderbook"
            event_type = EventType.ORDERBOOK
        elif feed == "trade":
            topic = f"{self.market_type}/trade/{sym}"
            request = f"request/{self.market_type}/{sym}/trade"
            event_type = EventType.TRADE
        elif feed == "order":
            topic = f"{self.market_type}/order/{sym}/{self.id}/*"
            request = f"request/{self.market_type}/{sym}/order"
            event_type = EventType.ORDER_CREATED

        async def listener(_t: str, payload: Any) -> None:
            if isinstance(payload, Event):
                await self.pipeline.fire_channel_read(payload)
            else:
                await self.pipeline.fire_channel_read(
                    Event(event_type, sym, payload)
                )

        self._subscribe(topic, listener, request)
        return self

    def _subscribe(self, topic_pattern: str, listener: BusHandler, request_topic: str) -> None:
        if not self._activated:
            self._activated = True
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self.pipeline.fire_channel_active())
            except RuntimeError:
                pass
        if topic_pattern in self._subscribed:
            return
        self._subscribed.add(topic_pattern)
        self._bus.on(topic_pattern, listener)
        # 通知 ExchangeConnector：有人要这路数据了
        try:
            asyncio.get_running_loop()
            asyncio.create_task(
                self._bus.emit(request_topic, {"symbol": self.symbol.symbol, "market": self.market_type})
            )
        except RuntimeError:
            pass

    # ---------------- 出站：写指令，通过 Pipeline 后发布到 EventBus ----------------

    async def write(self, command: Command) -> None:
        await self._publish_command(command)

    async def _publish_command(self, command: Command) -> None:
        """指令穿过整条 pipeline、到达 head 之后，发布到 EventBus。"""
        topic = f"command/{self.market_type}/{self.symbol.symbol}/{command.type.value}/{self.id}"
        logger.debug("发布命令到总线: topic=%s", topic)
        await self._bus.emit(topic, command.payload)

    # ---------------- 生命周期 ----------------

    async def close(self) -> None:
        for pattern in self._subscribed:
            await self._bus.emit(f"unsubscribe/{self.market_type}/{self.symbol.symbol}", {"pattern": pattern})
        self._subscribed.clear()

