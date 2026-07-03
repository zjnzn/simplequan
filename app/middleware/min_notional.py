"""最小下单名义价值过滤 —— 下单名义价值 < 交易对 min_cost 时拒绝。"""
from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class MinNotionalMiddleware:
    """最小下单名义价值检查。

    从 channel.symbol.min_cost 读取当前交易对的最小下单名义价值，
    下单 notional（amount × close_price）低于该值时直接拒绝，
    避免触发交易所的下单最小金额限制。
    """

    name = "min_notional"

    async def check(self, payload, ctx) -> RiskResult:
        sym = ctx.channel.symbol
        min_cost = float(getattr(sym, "min_cost", 0.0) or 0.0)
        if min_cost <= 0:
            return RiskResult.approve()

        command_payload = payload.payload if hasattr(payload, "payload") else {}
        amount = float(command_payload.get("amount", 0))
        close_price = float(command_payload.get("close_price", 0))
        notional = command_payload.get("notional")
        if notional is not None:
            notional = float(notional)
        elif close_price > 0:
            notional = float(amount * close_price)
        else:
            # 既无显式 notional 也无有效 close_price，无法判断，放行
            return RiskResult.approve()

        if notional < min_cost:
            logger.debug(
                "最小名义价值拒绝: symbol=%s notional=%.4f < min_cost=%.4f",
                sym.symbol, notional, min_cost,
            )
            return RiskResult.reject(
                f"低于最小下单名义价值: notional={notional:.4f} < min_cost={min_cost:.4f}"
            )

        return RiskResult.approve()
