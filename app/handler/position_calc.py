import logging
from decimal import Decimal

from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class PositionCalcHandler(Handler):
    """入站：row dict (signal_value/close等) → 目标仓位差值 → 下单。

    单一职责：仅做仓位计算，不做信号过滤（过滤交由 Risk 层）。
    信号强度驱动仓位大小：
    - LONG (value > 0)：目标 = +position_pct * strength * balance
    - SHORT (value < 0)：目标 = -position_pct * strength * balance
    """

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        signal_value = row.get("signal_value", 0.0)
        signal_strength = row.get("signal_strength", 0.0)
        signal_reason = row.get("signal_reason", "")

        if signal_value == 0:
            return

        market = ctx.channel.market
        bar_key = "1m" if "1m" in market.bars else next(iter(market.bars), None)
        if bar_key is None:
            return
        df = market.bars.get(bar_key)
        if df is None or len(df) == 0:
            return
        price = Decimal(str(df["close"].iloc[-1]))

        acc = ctx.channel.sub_account
        if acc is None:
            logger.warning("无子账号，跳过仓位计算")
            return

        pos = acc.position
        pos.update_unrealized_pnl(price)

        allocated = Decimal(str(acc.allocated_balance))
        strength = Decimal(str(signal_strength))
        leverage = Decimal(str(getattr(acc.leverage_config, "leverage", 1) or 1))
        notional = allocated * strength * leverage
        target_qty = notional / price

        pos = acc.position
        if pos.side == "BUY":
            current_qty = Decimal(str(pos.qty))
        elif pos.side == "SELL":
            current_qty = -Decimal(str(pos.qty))
        else:
            current_qty = Decimal("0")

        target_signed = target_qty if signal_value > 0 else -target_qty

        delta = target_signed - current_qty
        if current_qty > 0 and delta < -current_qty:
            delta = -current_qty
        elif current_qty < 0 and delta > -current_qty:
            delta = -current_qty
        if abs(delta) < Decimal("0.000001"):
            return

        order_side = "BUY" if delta > 0 else "SELL"
        order_qty = abs(delta)
        order_notional = order_qty * price
        margin = order_notional / leverage if leverage > 0 else order_notional

        await ctx.pipeline.write(Command(
            CommandType.CREATE_ORDER, ctx.channel.symbol.symbol,
            {
                "side": order_side,
                "amount": float(order_qty),
                "notional": float(order_notional),
                "leverage": int(leverage),
                "margin": float(margin),
                "reason": signal_reason,
                "close_price": float(price),
            },
        ))
