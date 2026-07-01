import logging
from decimal import Decimal


from core.domain.event import Event, EventType
from core.domain.order import Order, OrderState
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


# ccxt order status → OrderState 映射
_STATUS_MAP = {
    "open": OrderState.SUBMITTED,
    "closed": OrderState.FILLED,
    "canceled": OrderState.CANCELED,
    "rejected": OrderState.REJECTED,
    "expired": OrderState.EXPIRED,
}


def _ccxt_to_order(raw: dict, pipeline_id: str = "") -> Order:
    """将 ccxt raw dict 转换为不可变 Order dataclass。"""
    status = raw.get("status", "open")
    return Order(
        order_id=str(raw.get("id", "")),
        client_order_id=raw.get("clientOrderId", ""),
        pipeline_id=pipeline_id,
        symbol=raw.get("symbol", ""),
        side=raw.get("side", "").upper(),
        order_type=raw.get("type", "").upper(),
        qty=Decimal(str(raw.get("amount", 0))),
        price=Decimal(str(raw["price"])) if raw.get("price") else None,
        filled_qty=Decimal(str(raw.get("filled", 0))),
        avg_price=Decimal(str(raw["average"])) if raw.get("average") else None,
        state=_STATUS_MAP.get(status, OrderState.SUBMITTED),
    )


class OrderAcceptedHandler(Handler):
    """入站：订单创建成功后缓存。只处理 ORDER_CREATED 事件。"""

    handles = frozenset({EventType.ORDER_CREATED})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        raw = event.payload
        if isinstance(raw, dict):
            order = _ccxt_to_order(raw, pipeline_id=getattr(ctx.pipeline, "id", ""))
        else:
            order = raw
        key = f"orders/{getattr(order, 'order_id', id(order))}"
        await ctx.services.cache.set(key, order)
        logger.info("订单创建: %s %s 订单号=%s", event.symbol, event.type.value, getattr(order, 'order_id', '?'))
        await ctx.fire_channel_read(Event(EventType.ORDER_CREATED, event.symbol, order))
