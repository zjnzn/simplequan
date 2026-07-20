import logging
from decimal import Decimal

from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class PositionCalcHandler(Handler):
    """入站：row dict → 开仓/平仓。

    入场 (signal_type=="entry"): 空仓时全量开仓。
    离场 (signal_type=="exit"):  全平仓。
    """

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        signal_value = row.get("signal_value", 0.0)
        signal_reason = row.get("signal_reason", "")
        signal_type = row.get("signal_type", "entry")

        if signal_value == 0:
            return

        market = ctx.channel.market
        bar_key = next(iter(market.bars), None)
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

        if pos.side == "BUY":
            current_qty = Decimal(str(pos.qty))
            current_side = 1
        elif pos.side == "SELL":
            current_qty = Decimal(str(pos.qty))
            current_side = -1
        else:
            current_qty = Decimal("0")
            current_side = 0

        leverage = int(getattr(acc.leverage_config, "leverage", 1) or 1)

        if signal_type == "exit":
            if current_side == 0:
                return
            exit_fraction = float(row.get("exit_fraction", 1.0))
            order_side = "SELL" if current_side > 0 else "BUY"
            order_qty = current_qty * Decimal(str(exit_fraction))
            if order_qty <= Decimal("0.000001"):
                return
            order_notional = order_qty * price
            margin = Decimal("0")
        else:
            if current_side != 0:
                return
            allocated = Decimal(str(acc.allocated_balance))
            notional = allocated * Decimal(str(leverage))
            order_qty = notional / price
            if order_qty <= Decimal("0.000001"):
                return
            order_side = "BUY" if signal_value > 0 else "SELL"
            order_notional = order_qty * price
            margin = order_notional / leverage

        await ctx.pipeline.write(Command(
            CommandType.CREATE_ORDER, ctx.channel.symbol.symbol,
            {
                "side": order_side,
                "amount": float(order_qty),
                "notional": float(order_notional),
                "leverage": leverage,
                "margin": float(margin),
                "reason": signal_reason,
                "close_price": float(price),
            },
        ))
