from __future__ import annotations

import logging

from src.risk.base import RiskResult

logger = logging.getLogger(__name__)


class PerOrderRatioMiddleware:
    """单笔订单占比检查。amount * price / allocated_balance > max_per_order_ratio 时拒绝。"""

    name = "per_order_ratio"

    def __init__(self, max_per_order_ratio: float = 0.1) -> None:
        self._default_max = max_per_order_ratio

    async def check(self, payload, ctx) -> RiskResult:
        if ctx.account.allocated_balance <= 0:
            return RiskResult.approve()

        command_payload = payload.payload if hasattr(payload, "payload") else {}
        amount = float(command_payload.get("amount", 0))
        price = float(command_payload.get("price", 0))

        if price <= 0:
            return RiskResult.approve()

        ratio = amount * price / ctx.account.allocated_balance

        risk_cfg = ctx.risk_config.get("risk_post", {})
        max_ratio = risk_cfg.get("max_per_order_ratio", self._default_max)

        if ratio > max_ratio:
            logger.warning("单笔占比超限: %.2f%% > %.2f%%", ratio * 100, max_ratio * 100)
            return RiskResult.reject(f"单笔占比超限: {ratio:.2%}, 限额={max_ratio:.2%}")

        return RiskResult.approve()
