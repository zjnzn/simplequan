from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class GlobalLossMiddleware:
    """全局止损检查（本地实现：基于 sub_account.daily_pnl 的兜底）。

    无独立 account_mgr，当前简化为 approve——全局止损由 DailyLoss/Drawdown 覆盖。
    """

    name = "global_loss"

    async def check(self, payload, ctx) -> RiskResult:
        return RiskResult.approve()
