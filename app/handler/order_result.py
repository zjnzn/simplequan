import logging
from decimal import Decimal

from src.core.context import ChannelHandlerContext
from src.core.event_bus import ChannelEvent, EventType
from src.core.handler import ChannelHandler
from src.core.order import OrderState

from src.handlers.order_accepted import _ccxt_to_order, _STATUS_MAP

logger = logging.getLogger(__name__)


class OrderResultHandler(ChannelHandler):
    """入站：订单状态更新。只处理 ORDER_FILLED/CANCELED/REJECTED 事件。

    成交时更新仓位追踪和 daily_pnl。
    """

    handles = frozenset({EventType.ORDER_FILLED, EventType.ORDER_CANCELED, EventType.ORDER_REJECTED})

    async def channel_read(self, ctx: ChannelHandlerContext, event: ChannelEvent) -> None:
        raw = event.payload
        if isinstance(raw, dict):
            order_id = str(raw.get("id", ""))
            status = raw.get("status", "open")
            filled_qty = Decimal(str(raw.get("filled", 0)))
            avg_price = Decimal(str(raw["average"])) if raw.get("average") else None
            state = _STATUS_MAP.get(status, OrderState.SUBMITTED)
            side = raw.get("side", "").upper()
        else:
            order_id = getattr(raw, "order_id", None)
            filled_qty = getattr(raw, "filled_qty", None)
            avg_price = getattr(raw, "avg_price", None)
            state = getattr(raw, "state", None)
            side = getattr(raw, "side", "")

        # 更新缓存中的订单
        if order_id:
            key = f"orders/{order_id}"
            cached = await ctx.services.cache.get(key)
            if cached is not None and hasattr(cached, "with_update"):
                try:
                    order = cached.with_update(
                        filled_qty=filled_qty,
                        avg_price=avg_price,
                        state=state,
                    )
                except Exception:
                    order = raw
            else:
                order = _ccxt_to_order(raw) if isinstance(raw, dict) else raw
            await ctx.services.cache.set(key, order)

        # 成交时更新仓位和 PnL
        if event.type == EventType.ORDER_FILLED and avg_price and filled_qty:
            self._update_position_and_pnl(ctx, side, float(filled_qty), float(avg_price))

        ctx.account.current_position = raw
        logger.info("订单回报: %s %s 订单号=%s 方向=%s 成交=%s", event.symbol, event.type.value, order_id, side, filled_qty)
        await ctx.fire_channel_read(event)

    @staticmethod
    def _update_position_and_pnl(
        ctx: ChannelHandlerContext, side: str, qty: float, price: float
    ) -> None:
        """更新仓位追踪和 daily_pnl，并同步到 MasterAccountManager。"""
        acc = ctx.account
        pnl = 0.0
        if side == "BUY":
            if acc.position_side == "SELL":
                # 平空仓 → 计算 PnL
                pnl = (acc.position_avg_price - price) * min(qty, acc.position_qty)
                acc.daily_pnl += pnl
                remaining = acc.position_qty - qty
                if remaining <= 0:
                    acc.position_side = ""
                    acc.position_qty = 0.0
                    acc.position_avg_price = 0.0
                else:
                    acc.position_qty = remaining
            else:
                # 开多仓或加仓
                total_cost = acc.position_avg_price * acc.position_qty + price * qty
                acc.position_qty += qty
                acc.position_avg_price = total_cost / acc.position_qty if acc.position_qty else 0
                acc.position_side = "BUY"
        elif side == "SELL":
            if acc.position_side == "BUY":
                # 平多仓 → 计算 PnL
                pnl = (price - acc.position_avg_price) * min(qty, acc.position_qty)
                acc.daily_pnl += pnl
                remaining = acc.position_qty - qty
                if remaining <= 0:
                    acc.position_side = ""
                    acc.position_qty = 0.0
                    acc.position_avg_price = 0.0
                else:
                    acc.position_qty = remaining
            else:
                # 开空仓或加仓
                total_cost = acc.position_avg_price * acc.position_qty + price * qty
                acc.position_qty += qty
                acc.position_avg_price = total_cost / acc.position_qty if acc.position_qty else 0
                acc.position_side = "SELL"

        # 同步 PnL 变动到 MasterAccountManager 全局汇总
        if pnl != 0.0:
            pipeline_id = getattr(ctx.ctx, "pipeline_id", "")
            logger.info("盈亏: %s 方向=%s 盈亏=%.4f 日累计=%.4f", pipeline_id or "?", side, pnl, acc.daily_pnl)
            mgr = ctx.services.account_mgr
            if mgr and pipeline_id and pipeline_id in mgr._daily_pnls:
                mgr._daily_pnls[pipeline_id] += pnl
