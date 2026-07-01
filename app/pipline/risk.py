from __future__ import annotations

import logging

from src.risk.base import RiskMiddleware, RiskResult

logger = logging.getLogger(__name__)


class RiskPipeline:
    """风控中间件责任链。按序执行，短路拒绝，异常放行。"""

    def __init__(self, middlewares: list[RiskMiddleware]) -> None:
        self._middlewares = list(middlewares)

    async def check(self, payload, ctx) -> RiskResult:
        for mw in self._middlewares:
            try:
                result = await mw.check(payload, ctx)
                if not result.passed:
                    return result
            except Exception:
                logger.warning("风控中间件 %s 异常，放行", mw.name, exc_info=True)
                continue
        return RiskResult.approve()
