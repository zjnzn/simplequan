from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class DailyLossMiddleware:
    """日亏损限额检查。daily_pnl <= -limit 时拒绝。"""

    name = "daily_loss"

    def __init__(self, daily_loss_limit: float = 500.0) -> None:
        self._default_limit = daily_loss_limit

    async def check(self, payload, ctx) -> RiskResult:
        sub = ctx.channel.sub_account
        limit = ctx.channel.config.risk_pre.daily_loss_limit or self._default_limit

        if sub.daily_pnl <= -limit:
            logger.warning("日亏拒绝: pnl=%.2f 限额=%.2f", sub.daily_pnl, -limit)
            return RiskResult.reject(f"日亏超限: pnl={sub.daily_pnl:.2f}, 限额={-limit:.2f}")

        return RiskResult.approve()
