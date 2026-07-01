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
        if ctx.account.allocated_balance <= 0:
            return RiskResult.approve()

        risk_cfg = ctx.risk_config.get("risk_pre", {})
        max_dd = risk_cfg.get("max_drawdown", self._default_max)

        drawdown = -ctx.account.daily_pnl / ctx.account.allocated_balance
        if drawdown >= max_dd:
            logger.warning("回撤拒绝: %.2f%% 限额=%.2f%%", drawdown * 100, max_dd * 100)
            return RiskResult.reject(f"回撤超限: {drawdown:.2%}, 限额={max_dd:.2%}")

        return RiskResult.approve()
