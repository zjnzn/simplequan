import logging
from decimal import Decimal

from app.handler.order_accepted import _STATUS_MAP, _ccxt_to_order
from core.domain.event import Event, EventType
from core.domain.order import OrderState
from core.ports.context import Context
from core.ports.handler import Handler


logger = logging.getLogger(__name__)


class OrderResultHandler(Handler):
    """入站：订单最终状态回报。

    与 OrderAccepted 的乐观更新配合，达到最终一致性：
      - ORDER_FILLED：开仓单用真实成交均价修正 pos.avg_price；平仓单算 PnL；
        部分成交差额回滚。
      - ORDER_CANCELED / ORDER_REJECTED：回滚乐观更新的持仓，撤回未成交部分。
    """

    handles = frozenset({EventType.ORDER_FILLED, EventType.ORDER_CANCELED, EventType.ORDER_REJECTED})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        raw = event.payload
        if isinstance(raw, dict):
            order_id = str(raw.get("id", ""))
            status = raw.get("status", "open")
            filled_qty = Decimal(str(raw.get("filled", 0)))
            avg_price = Decimal(str(raw["average"])) if raw.get("average") else None
            state = _STATUS_MAP.get(status, OrderState.SUBMITTED)
            side = raw.get("side", "").upper()
            raw_fee = raw.get("fee")
        else:
            order_id = getattr(raw, "order_id", None)
            filled_qty = getattr(raw, "filled_qty", None)
            avg_price = getattr(raw, "avg_price", None)
            state = getattr(raw, "state", None)
            side = getattr(raw, "side", "")
            raw_fee = None

        # 更新缓存中的订单
        if order_id:
            key = f"orders/{order_id}"
            cached = await ctx.channel.cache.get(key)
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
            await ctx.channel.cache.set(key, order)

        # 持仓最终修正 / 回滚
        pending_key = f"orders/{order_id}/pending"
        pending = await ctx.channel.cache.get(pending_key)
        if pending is not None:
            if event.type == EventType.ORDER_FILLED:
                fee_usdt = _fee_in_usdt(raw_fee, avg_price or Decimal("0"))
                await self._on_filled(ctx, side, filled_qty, avg_price, pending, fee_usdt)
            else:
                # CANCELED / REJECTED：未成交，全部回滚
                await self._rollback(ctx, pending)
            await ctx.channel.cache.delete(pending_key)

        logger.debug("订单回报: %s %s 订单号=%s 方向=%s 成交=%s",
                    event.symbol, event.type.value, order_id, side, filled_qty)
        await ctx.fire_channel_read(event)

    async def _on_filled(
        self, ctx: Context, side: str, filled_qty: Decimal,
        fill_avg: Decimal | None, pending: dict,
        fee_usdt: Decimal = Decimal("0"),
    ) -> None:
        """FILLED：开仓修正均价，平仓算 PnL，部分成交差额回滚。手续费折算 USDT 后计入成本/PnL。"""
        sub = ctx.channel.sub_account
        if sub is None or fill_avg is None:
            return
        pos = sub.position
        pending_qty = pending["qty"]
        if filled_qty > pending_qty:
            logger.warning("成交超量: filled=%s pending=%s，按 pending 结算",
                           filled_qty, pending_qty)
        settled = min(filled_qty, pending_qty)

        # 部分成交：先回滚未成交差额（回滚后持仓只剩已成交部分）
        unfilled = pending_qty - filled_qty
        if unfilled > 0:
            await self._rollback(ctx, pending, unfilled)

        if pending["kind"] == "open":
            placeholder = pending["placeholder"]
            if pos.qty > 0 and settled > 0:
                other_total = pos.avg_price * pos.qty - placeholder * settled
                pos.avg_price = (other_total + fill_avg * settled) / pos.qty
            # 开仓手续费增加成本基础（抬高持仓均价），分配余额衰减
            if fee_usdt > 0 and pos.qty > 0:
                pos.avg_price = (pos.avg_price * pos.qty + fee_usdt) / pos.qty
                sub.allocated_balance -= fee_usdt
                logger.debug("开仓手续费计入成本: fee=%.4fUSDT 均价=%s", float(fee_usdt), pos.avg_price)
            logger.debug("开仓均价修正: 真均价=%s 成交=%s 持仓=%s 均价=%s",
                         fill_avg, settled, pos.qty, pos.avg_price)
        elif pending["kind"] == "close":
            avg_at_close = pending["avg_at_close"]
            side_at_close = pending["side_at_close"]
            if side_at_close == "BUY":
                pnl = (fill_avg - avg_at_close) * settled
            else:
                pnl = (avg_at_close - fill_avg) * settled
            # 手续费直接扣减净利润
            pnl -= fee_usdt
            sub.daily_pnl += pnl
            sub.allocated_balance += pnl
            if pnl != 0:
                logger.debug("盈亏: %s 方向=%s 盈亏=%.4f(含手续费)=%.4f 日累计=%.4f",
                            ctx.channel.id[:8], side, float(pnl), float(fee_usdt), float(sub.daily_pnl))

    async def _rollback(self, ctx: Context, pending: dict, qty: Decimal | None = None) -> None:
        """回滚乐观更新的持仓。qty=None 全量回滚，否则回滚指定数量（部分成交差额）。"""
        sub = ctx.channel.sub_account
        if sub is None:
            return
        pos = sub.position
        rollback_qty = qty if qty is not None else pending["qty"]

        if pending["kind"] == "open":
            placeholder = pending["placeholder"]
            margin_held = Decimal(str(pending.get("margin", 0)))
            if margin_held > 0 and pending["qty"] > 0:
                release = margin_held * rollback_qty / pending["qty"]
                if sub.margin_used >= release:
                    sub.margin_used -= release
                else:
                    logger.error("保证金释放异常: margin_used=%s < release=%s (order_id=%s)",
                                 sub.margin_used, release, ctx.channel.id[:8])
            if pos.qty > 0:
                other_total = pos.avg_price * pos.qty - placeholder * rollback_qty
                pos.qty -= rollback_qty
                if pos.qty > 0:
                    pos.avg_price = other_total / pos.qty
                else:
                    pos.side = ""
                    pos.avg_price = Decimal("0")
            logger.debug("开仓回滚: 数量=%s 释放保证金=%s 剩余持仓=%s",
                         rollback_qty, margin_held if margin_held > 0 else 0, pos.qty)
        elif pending["kind"] == "close":
            pos.qty += rollback_qty
            if pos.side == "" and pos.qty > 0:
                pos.side = pending["side_at_close"]
                pos.avg_price = pending["avg_at_close"]
            logger.debug("平仓回滚: 数量=%s 剩余持仓=%s 均价=%s",
                         rollback_qty, pos.qty, pos.avg_price)


def _fee_in_usdt(fee: dict | None, fill_avg: Decimal) -> Decimal:
    """将 ccxt 手续费转为 USDT 等值。

    Spot 模式下 Binance 从收到资产中扣除手续费：
      - BUY：收到 BTC，fee 扣 BTC → 按成交均价折 USDT
      - SELL：收到 USDT，fee 扣 USDT → 直接使用
    """
    if not fee:
        return Decimal("0")
    fee_cost = Decimal(str(fee.get("cost", 0) or 0))
    if not fee_cost:
        return Decimal("0")
    if fee.get("currency", "") == "USDT":
        return fee_cost
    # 非 USDT 手续费（BTC/ETH/BNB），按 fill_avg 折算
    if fill_avg and fill_avg > 0:
        return fee_cost * fill_avg
    return Decimal("0")
