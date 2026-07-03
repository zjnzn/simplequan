from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class PerOrderRatioMiddleware:
    """单笔订单占比检查。amount * price / allocated_balance > max_per_order_ratio 时拒绝。"""

    name = "per_order_ratio"

    def __init__(self, max_per_order_ratio: float = 0.1) -> None:
        self._default_max = max_per_order_ratio

    async def check(self, payload, ctx) -> RiskResult:
        sub = ctx.channel.sub_account
        if sub.allocated_balance <= 0:
            return RiskResult.approve()

        command_payload = payload.payload if hasattr(payload, "payload") else {}
        notional = float(command_payload.get("notional", 0))

        if notional <= 0:
            return RiskResult.approve()

        ratio = notional / float(sub.allocated_balance)

        max_ratio = ctx.channel.config.risk_post.max_per_order_ratio
        if max_ratio is None:
            max_ratio = self._default_max
        elif max_ratio <= 0:
            return RiskResult.approve()

        if ratio > max_ratio:
            logger.warning("单笔占比超限: %.2f%% > %.2f%%", ratio * 100, max_ratio * 100)
            return RiskResult.reject(f"单笔占比超限: {ratio:.2%}, 限额={max_ratio:.2%}")

        return RiskResult.approve()
