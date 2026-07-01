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

    信号强度驱动仓位大小：
    - LONG (value > 0)：目标 = +position_pct * strength * balance
    - SHORT (value < 0)：目标 = -position_pct * strength * balance
    - HOLD (value == 0)：不下单

    差值 = 目标 - 当前持仓。差值为正→买入，为负→卖出，接近零→跳过。
    """

    handles = frozenset({EventType.KLINE})

    def __init__(self, position_pct: float = 0.3):
        self._position_pct = position_pct

    async def channel_read(self, ctx: Context, event: Event) -> None:
        signal = event.payload
        if not hasattr(signal, "value"):
            await ctx.fire_channel_read(event)
            return
        if signal.value == 0:
            return

        bar_key = "1m" if "1m" in (ctx.market.bars or {}) else next(iter(ctx.market.bars or {}), None)
        if bar_key is None:
            return
        bars = ctx.market.bars.get(bar_key)
        if bars is None or len(bars) == 0:
            return
        price = bars[-1].close

        acc = ctx.account
        # 信号强度调整仓位
        adjusted_pct = self._position_pct * signal.strength
        notional = Decimal(str(acc.allocated_balance)) * Decimal(str(adjusted_pct))
        target_qty = notional / price  # 目标绝对数量（始终为正）

        # 当前持仓：正=多头，负=空头，0=空仓
        if acc.position_side == "BUY":
            current_qty = Decimal(str(acc.position_qty))
        elif acc.position_side == "SELL":
            current_qty = -Decimal(str(acc.position_qty))
        else:
            current_qty = Decimal("0")

        # 信号方向 → 目标持仓（正=多，负=空）
        if signal.value > 0:
            target_signed = target_qty
        else:
            target_signed = -target_qty

        # 差值 = 目标 - 当前
        delta = target_signed - current_qty
        if abs(delta) < Decimal("0.000001"):
            logger.debug("仓位差值过小，跳过: 目标=%s 当前=%s 差值=%s", target_signed, current_qty, delta)
            return

        # 转换为下单指令
        order_side = "BUY" if delta > 0 else "SELL"
        order_qty = abs(delta)

        target = TargetPosition(
            symbol=ctx.pipeline.channel.symbol,
            side=order_side,
            qty=order_qty,
            reason=signal.reason,
        )
        logger.info(
            "仓位计算: %s %s 数量=%.6f 目标=%s 当前=%s 信号=%+.4f 原因=%s",
            target.side, target.symbol, float(target.qty),
            target_signed, current_qty, signal.value, target.reason,
        )
        await ctx.pipeline.write(Command(
            CommandType.CREATE_ORDER, target.symbol,
            {"side": target.side, "amount": float(target.qty), "reason": target.reason},
        ))
