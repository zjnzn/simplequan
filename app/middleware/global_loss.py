from __future__ import annotations

import logging

from src.risk.base import RiskResult

logger = logging.getLogger(__name__)


class GlobalLossMiddleware:
    """全局止损检查。account_mgr.check() 返回 False 时拒绝。"""

    name = "global_loss"

    async def check(self, payload, ctx) -> RiskResult:
        account_mgr = ctx.services.account_mgr
        if account_mgr is None or not hasattr(account_mgr, "check"):
            return RiskResult.approve()

        if not await account_mgr.check(payload):
            logger.warning("全局止损拒绝")
            return RiskResult.reject("触发全局日亏限额")

        return RiskResult.approve()
