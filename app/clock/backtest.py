"""BacktestClock —— 回测时钟，加速回放。

sleep 仅 yield 一次事件循环（不真实等待），实现加速回放的同时避免独占 CPU。
回测时由外部逐根喂入历史 K 线，时间戳来自历史数据，时钟只负责不阻塞。
"""
from __future__ import annotations

import asyncio

from core.ports.clock import Clock


class BacktestClock(Clock):
    """回测时钟。sleep 仅 yield 一次（不真实等待），now_ms 返回回放时间戳。"""

    def __init__(self, start_ms: int = 0) -> None:
        self._now_ms: int = start_ms

    def now_ms(self) -> int:
        return self._now_ms

    def advance(self, ms: int) -> None:
        """推进回测时间（由回测驱动器调用）。"""
        self._now_ms += ms

    async def sleep(self, seconds: float) -> None:
        # 回测不真实等待，但 yield 一次让事件循环调度其它 task（订单回报等）
        await asyncio.sleep(0)
