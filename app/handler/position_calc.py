import logging
from dataclasses import dataclass
from decimal import Decimal


from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


@dataclass
class TargetPosition:
    symbol: str
    side: str   # BUY / SELL
    qty: Decimal
    reason: str


class PositionCalcHandler(Handler):
    """入站：Signal → 目标仓位差值 → 下单。

    单一职责：仅做仓位计算，不做信号过滤（过滤交由 Risk 层）。
    信号强度驱动仓位大小：
    - LONG (value > 0)：目标 = +position_pct * strength * balance
    - SHORT (value < 0)：目标 = -position_pct * strength * balance
    """

    handles = frozenset({EventType.KLINE})

    async def channel_read(self, ctx: Context, event: Event) -> None:
        signal = event.payload
        if not hasattr(signal, "value"):
            await ctx.fire_channel_read(event)
            return
        if signal.value == 0:
            return

        market = ctx.channel.market
        bar_key = "1m" if "1m" in market.bars else next(iter(market.bars), None)
        if bar_key is None:
            return
        bars = market.bars.get(bar_key)
        if bars is None or len(bars) == 0:
            return
        price = bars[-1].close

        acc = ctx.channel.sub_account
        if acc is None:
            logger.warning("无子账号，跳过仓位计算")
            return

        # 每根 K 线到达时更新未实现盈亏
        pos = acc.position
        pos.update_unrealized_pnl(Decimal(str(price)))

        allocated = Decimal(str(acc.allocated_balance))
        strength = Decimal(str(signal.strength))
        leverage = Decimal(str(getattr(acc.leverage_config, "leverage", 1) or 1))
        notional = allocated * strength * leverage
        target_qty = notional / price

        # 当前持仓
        pos = acc.position
        if pos.side == "BUY":
            current_qty = Decimal(str(pos.qty))
        elif pos.side == "SELL":
            current_qty = -Decimal(str(pos.qty))
        else:
            current_qty = Decimal("0")

        # 目标持仓（正=多，负=空）
        target_signed = target_qty if signal.value > 0 else -target_qty

        delta = target_signed - current_qty
        # 方向反转时只平仓不翻仓：翻仓需要第二个信号来反向开仓
        if current_qty > 0 and delta < -current_qty:
            delta = -current_qty
        elif current_qty < 0 and delta > -current_qty:
            delta = -current_qty
        if abs(delta) < Decimal("0.000001"):
            return

        order_side = "BUY" if delta > 0 else "SELL"
        order_qty = abs(delta)
        order_notional = order_qty * Decimal(str(price))
        margin = order_notional / leverage if leverage > 0 else order_notional

        await ctx.pipeline.write(Command(
            CommandType.CREATE_ORDER, ctx.channel.symbol.symbol,
            {
                "side": order_side,
                "amount": float(order_qty),
                "notional": float(order_notional),
                "leverage": int(leverage),
                "margin": float(margin),
                "reason": signal.reason,
                "close_price": float(price),
            },
        ))
