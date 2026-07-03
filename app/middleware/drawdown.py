from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class DrawdownMiddleware:
    """最大回撤检查。drawdown >= max_drawdown 时拒绝。"""

    name = "drawdown"

    def __init__(self, max_drawdown: float = 0.08) -> None:
        self._default_max = max_drawdown

    async def check(self, payload, ctx) -> RiskResult:
        sub = ctx.channel.sub_account
        if sub.allocated_balance <= 0:
            return RiskResult.approve()

        sub.maybe_reset_daily_pnl()
        max_dd = ctx.channel.config.risk_pre.max_drawdown
        if max_dd is None:
            max_dd = self._default_max
        elif max_dd <= 0:
            return RiskResult.approve()

        drawdown = -sub.daily_pnl / sub.allocated_balance
        if drawdown >= max_dd:
            logger.warning("回撤拒绝: %.2f%% 限额=%.2f%%", drawdown * 100, max_dd * 100)
            return RiskResult.reject(f"回撤超限: {drawdown:.2%}, 限额={max_dd:.2%}")

        return RiskResult.approve()
