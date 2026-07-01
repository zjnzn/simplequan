from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class AmountCheckMiddleware:
    """下单数量检查。amount <= 0 时拒绝。"""

    name = "amount_check"

    async def check(self, payload, ctx) -> RiskResult:
        command_payload = payload.payload if hasattr(payload, "payload") else {}
        amount = float(command_payload.get("amount", 0))
        if amount <= 0:
            logger.warning("下单数量拒绝: amount=%.6f", amount)
            return RiskResult.reject(f"下单数量无效: {amount:.6f}")
        return RiskResult.approve()
