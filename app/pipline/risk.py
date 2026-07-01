"""RiskPipeline —— 风控中间件责任链。

类似 ChannelPipeline，负责组装和执行风控中间件。
按序执行，短路拒绝，异常放行。
"""
from __future__ import annotations

import logging
from typing import Any

from app.middleware.amount_check import AmountCheckMiddleware
from app.middleware.daily_loss import DailyLossMiddleware
from app.middleware.drawdown import DrawdownMiddleware
from app.middleware.global_loss import GlobalLossMiddleware
from app.middleware.max_leverage import MaxLeverageMiddleware
from app.middleware.per_order_ratio import PerOrderRatioMiddleware
from core.domain.risk import RiskResult
from core.ports.middleware import RiskMiddleware

logger = logging.getLogger(__name__)


class RiskPipeline:
    """风控中间件责任链。"""

    def __init__(self, middlewares: list[RiskMiddleware] | None = None) -> None:
        self._middlewares: list[RiskMiddleware] = list(middlewares or [])

    def add_last(self, middleware: RiskMiddleware) -> RiskPipeline:
        """添加中间件到链尾。"""
        self._middlewares.append(middleware)
        return self

    def add_first(self, middleware: RiskMiddleware) -> RiskPipeline:
        """添加中间件到链头。"""
        self._middlewares.insert(0, middleware)
        return self

    async def check(self, payload: Any, ctx: Any) -> RiskResult:
        """按序执行中间件，短路拒绝，异常放行。"""
        for mw in self._middlewares:
            try:
                result = await mw.check(payload, ctx)
                if not result.passed:
                    return result
            except Exception:
                logger.warning("风控中间件 %s 异常，放行", mw.name, exc_info=True)
                continue
        return RiskResult.approve()

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        names = [mw.name for mw in self._middlewares]
        return f"RiskPipeline({names})"
