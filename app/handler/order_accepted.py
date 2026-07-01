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
    """入站：订单创建成功后缓存 + 乐观更新持仓。

    收到 ORDER_CREATED 即认为下单成功（交易所已接受），立即乐观更新 Position：
      - 同向开仓/加仓：pos.qty += amount，avg_price 用占位价临时加权
      - 反向平仓：pos.qty -= amount
    pending 写入 cache，OrderResult 成交/失败时读取做最终修正或回滚。
    """

    handles = frozenset({EventType.ORDER_CREATED})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        raw = event.payload
        if isinstance(raw, dict):
            order = _ccxt_to_order(raw, pipeline_id=ctx.channel.id)
        else:
            order = raw
        key = f"orders/{order.order_id}"
        await ctx.channel.cache.set(key, order)

        # 乐观更新持仓（模拟器立即 closed 时，FILLED 回报会随后修正均价/算PnL）
        sub = ctx.channel.sub_account
        if sub is not None and order.qty and order.qty > 0:
            placeholder = Decimal(str(raw.get("close_price", 0))) or None
            await self._optimistic_apply(ctx, order, placeholder)

        logger.info("订单创建: %s %s 订单号=%s", event.symbol, event.type.value, order.order_id)
        await ctx.fire_channel_read(Event(EventType.ORDER_CREATED, event.symbol, order))

    async def _optimistic_apply(
        self, ctx: Context, order: Order, placeholder: Decimal | None
    ) -> None:
        """下单即乐观更新持仓，pending 写入 cache 供 OrderResult 修正/回滚。"""
        pos = ctx.channel.sub_account.position
        side = order.side
        qty = order.qty
        oid = order.order_id
        pending_key = f"orders/{oid}/pending"

        if placeholder is None or placeholder <= 0:
            logger.warning("订单 %s 无占位价，乐观更新跳过均价计算", oid)
            return

        if side == pos.side or pos.side == "":
            # 同向开仓 / 加仓（含空仓建仓）
            await self._apply_open(ctx, pos, side, qty, placeholder, pending_key, oid)
        else:
            # 反向 → 平仓
            await self._apply_close(ctx, pos, side, qty, pending_key, oid)

    async def _apply_open(
        self, ctx: Context, pos, side: str, qty: Decimal,
        placeholder: Decimal, pending_key: str, oid: str,
    ) -> None:
        """开仓/加仓：qty 即时增，avg_price 占位加权。"""
        total = pos.avg_price * pos.qty + placeholder * qty
        pos.qty += qty
        pos.avg_price = total / pos.qty if pos.qty else Decimal("0")
        pos.side = side
        # pending: 开仓待确认（FILLED 时用真实均价替换占位部分）
        await ctx.channel.cache.set(pending_key, {
            "kind": "open",
            "qty": qty,
            "placeholder": placeholder,
        })
        logger.debug("乐观开仓 %s %s 数量=%s 占价=%s 持仓=%s 均价=%s",
                     oid, side, qty, placeholder, pos.qty, pos.avg_price)

    async def _apply_close(
        self, ctx: Context, pos, side: str, qty: Decimal,
        pending_key: str, oid: str,
    ) -> None:
        """平仓：qty 即时减，记录平仓前的均价/方向供 FILLED 算 PnL。"""
        close_qty = min(qty, pos.qty)
        if close_qty <= 0:
            logger.warning("订单 %s 平仓但无持仓可平，跳过", oid)
            return
        avg_at_close = pos.avg_price
        side_at_close = pos.side  # 平仓前的持仓方向（BUY/SELL）
        pos.qty -= close_qty
        if pos.qty <= 0:
            pos.side = ""
            pos.avg_price = Decimal("0")
        # pending: 平仓待结算（FILLED 时算 PnL = (fill - avg_at_close) × close_qty × 方向符号）
        await ctx.channel.cache.set(pending_key, {
            "kind": "close",
            "qty": close_qty,
            "avg_at_close": avg_at_close,
            "side_at_close": side_at_close,
        })
        logger.debug("乐观平仓 %s %s 数量=%s 剩余持仓=%s",
                     oid, side, close_qty, pos.qty)
