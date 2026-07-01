from dataclasses import dataclass
from enum import Enum
from typing import Any

class EventType(str, Enum):
    KLINE = "kline"
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    ORDER_REJECTED = "order_rejected"


@dataclass(frozen=True)
class Event:
    """入站事件：交易所 -> 应用方向流动的数据。不可变。"""
    type: EventType
    symbol: str
    payload: Any
