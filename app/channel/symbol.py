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
from dataclasses import field
import uuid
from typing import Any, Optional

from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.domain.symbol import Symbol
from core.ports.channel import Channel
from core.ports.eventbus import EventBus
from core.ports.pipline import Pipeline
from utils.config import Config

class SymbolChannel:
    """Netty 风格 Channel。只认 EventBus，不持有任何交易所连接。"""

    # 账户状态
    allocated_balance: float = 0.0
    current_position: Any = None
    daily_pnl: float = 0.0
    position_side: str = ""
    position_qty: float = 0.0
    position_avg_price: float = 0.0
    leverage: int = 1
    margin_mode: str = "cross"
    symbol: Symbol = field(default_factory=Symbol)
    


    def __init__(self, bus: EventBus,config: Config,pipeline:Pipeline):
        self.id = str(uuid.uuid4())
        self.config = config
        self.pipeline = pipeline

        self._bus = bus
        self._activated = False
        self._subscribed = None

    # ---------------- 入站：订阅 EventBus 上的 data topic ----------------
    # ExchangeConnector 已将数据包装为 ChannelEvent，Channel 只转发


    def read(self,pay:str, timeframe: str) -> Channel:
        topic:str = ""
        eventType = ""
        request:str = ""
        if pay is "kline":
            topic = f"{self.market}/kline/{self.symbol}@{timeframe}"
            request = f"request/{self.market}/{self.symbol}/kline-{timeframe}"
            eventType = EventType.KLINE
        elif pay is "orderbook":
            topic = f"{self.market}/orderbook/{self.symbol}"
            request = f"request/{self.market}/{self.symbol}/orderbook"
            eventType = EventType.ORDERBOOK
        elif pay is "trade":
            topic = f"{self.market}/trade/{self.symbol}@{timeframe}"
            request = f"request/{self.market}/{self.symbol}/trade"
            eventType = EventType.TRADE
        elif pay is "order":
            topic = f"{self.market}/order/{self.symbol}/{self.id}/*"
            request = f"request/{self.market}/{self.symbol}/order"
            eventType = EventType.TRADE

        async def listener(_t: str, payload: Any) -> None:
            if isinstance(payload, Event):
                await self.pipeline.fire_channel_read(payload)
            else:
                await self.pipeline.fire_channel_read(
                    Event(eventType, self.symbol, payload)
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
                self._bus.emit(request_topic, {"symbol": self.symbol, "market": self.market})
            )
        except RuntimeError:
            pass

    # ---------------- 出站：写指令，通过 Pipeline 后发布到 EventBus ----------------

    async def write(self, command: Command) -> None:
        await self._publish_command(command)

    async def create_order(
        self, side: str, amount: float, price: Optional[float] = None, type: str = "limit"
    ) -> None:
        await self.write(Command(
            CommandType.CREATE_ORDER, self.symbol,
            {"side": side, "amount": amount, "price": price, "type": type},
        ))

    async def cancel_order(self, order_id: str) -> None:
        await self.write(Command(CommandType.CANCEL_ORDER, self.symbol, {"order_id": order_id}))

    async def _publish_command(self, command: Command) -> None:
        """指令穿过整条 pipeline、到达 head 之后，发布到 EventBus。"""
        topic = f"command/{self.market}/{self.symbol}/{command.type.value}/{self.id}"
        await self._bus.emit(topic, command.payload)

    # ---------------- 生命周期 ----------------

    async def close(self) -> None:
        for pattern in self._subscribed:
            await self._bus.emit(f"unsubscribe/{self.market}/{self.symbol}", {"pattern": pattern})

