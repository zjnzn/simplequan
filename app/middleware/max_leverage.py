from __future__ import annotations

import logging

from src.risk.base import RiskResult

logger = logging.getLogger(__name__)


class MaxLeverageMiddleware:
    """杠杆上限检查。leverage > max_leverage 时拒绝。"""

    name = "max_leverage"

    def __init__(self, max_leverage: int = 20) -> None:
        self._default_max = max_leverage

    async def check(self, payload, ctx) -> RiskResult:
        command_payload = payload.payload if hasattr(payload, "payload") else {}
        leverage = command_payload.get("leverage")
        if leverage is None:
            return RiskResult.approve()

        risk_cfg = ctx.risk_config.get("risk_post", {})
        max_lev = risk_cfg.get("max_leverage", self._default_max)

        if int(leverage) > int(max_lev):
            logger.warning("杠杆超限: %d > %d", int(leverage), int(max_lev))
            return RiskResult.reject(f"杠杆超限: {leverage} > {max_lev}")

        return RiskResult.approve()
