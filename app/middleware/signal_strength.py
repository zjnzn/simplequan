"""信号强度过滤 —— 弱信号直接拒绝，不计算仓位。"""
from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class SignalStrengthMiddleware:
    """信号强度阈值检查。|signal| < min_strength 时拒绝。"""

    name = "signal_strength"

    def __init__(self, min_strength: float = 0.03) -> None:
        self._default_min = min_strength

    async def check(self, payload, ctx) -> RiskResult:
        signal = payload
        if not hasattr(signal, "value"):
            return RiskResult.approve()

        strength = signal.strength if hasattr(signal, "strength") else abs(signal.value)
        if strength < self._default_min:
            logger.debug("弱信号过滤: value=%.4f strength=%.4f < %.2f",
                        getattr(signal, "value", 0), strength, self._default_min)
            return RiskResult.reject(f"弱信号: strength={strength:.4f}")
        return RiskResult.approve()
