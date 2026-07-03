"""仓位容忍度 —— 方向未变且调整量 < 目标仓位 N% 时跳过，减少无意义微调。"""
from __future__ import annotations

import logging

from core.domain.risk import RiskResult

logger = logging.getLogger(__name__)


class PositionToleranceMiddleware:
    """仓位容忍度检查。

    同向调整时，若 delta < 目标仓位 × tolerance，视为微调直接拒绝。
    避免信号小幅波动导致的频繁加减仓。
    """

    name = "position_tolerance"

    def __init__(self, tolerance: float = 0.15) -> None:
        self._tolerance = tolerance

    async def check(self, payload, ctx) -> RiskResult:
        sub = ctx.channel.sub_account
        pos = sub.position

        if pos.side == "" or pos.qty == 0:
            return RiskResult.approve()

        command_payload = payload.payload if hasattr(payload, "payload") else {}
        order_side = str(command_payload.get("side", ""))
        order_amount = float(command_payload.get("amount", 0))

        if order_side != pos.side:
            return RiskResult.approve()

        current_qty = float(pos.qty)
        target_qty = current_qty + order_amount
        ratio = order_amount / target_qty if target_qty > 0 else 1.0

        if ratio < self._tolerance:
            logger.debug(
                "仓位微调跳过: side=%s delta=%.6f target=%.6f ratio=%.2f%% < %.0f%%",
                order_side, order_amount, target_qty, ratio * 100, self._tolerance * 100,
            )
            return RiskResult.reject(
                f"仓位微调跳过: delta={order_amount:.6f} target={target_qty:.6f} ratio={ratio:.2%}"
            )

        return RiskResult.approve()
