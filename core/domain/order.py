from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Literal


class OrderState(Enum):
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class OrderUpdate:
    timestamp: float
    filled_qty: Decimal
    avg_price: Decimal
    state: OrderState


@dataclass(frozen=True)
class Order:
    order_id: str
    client_order_id: str
    pipeline_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT"]
    qty: Decimal
    price: Decimal | None = None
    filled_qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")
    state: OrderState = OrderState.SUBMITTED
    timestamp: float = 0.0
    updates: tuple[OrderUpdate, ...] = ()

    def with_update(self, **kw) -> "Order":
        update = OrderUpdate(
            timestamp=kw.get("timestamp", 0.0),
            filled_qty=kw.get("filled_qty", self.filled_qty),
            avg_price=kw.get("avg_price", self.avg_price),
            state=kw.get("state", self.state),
        )
        new_kw = {**kw, "updates": self.updates + (update,)}
        return replace(self, **new_kw)


@dataclass(frozen=True)
class OrderTask:
    request_id: str
    pipeline_id: str
    request: object

    async def execute(self) -> Order:
        raise NotImplementedError
